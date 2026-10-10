"""ops contest new|import  — 大会定義シート（Google スプレッドシート）で contest.yaml を作る"""
import difflib, json, sys, urllib.request
import yaml
from pathlib import Path
from ..paths import CONTESTS, contest_dir, ops_contest_dir, load_secrets
from ..contests import load_contest
from ..form.cli import _access_token, _config
from .sheet import build_rows, rows_to_spec, tabs_to_contest

def add_parser(sub):
    p = sub.add_parser("contest", help="大会定義シートの作成と、シートから contest.yaml の生成")
    s = p.add_subparsers(dest="cmd", required=True)
    n = s.add_parser("new", help="大会定義シートを作る（前回の値を入れておく）"); n.add_argument("id"); n.add_argument("--from", dest="prev"); n.add_argument("--test", action="store_true"); n.set_defaults(func=cmd_new)
    i = s.add_parser("import", help="大会定義シートを読んで contests/<id>/contest.yaml を書く（差分を表示）"); i.add_argument("id"); i.add_argument("--yes", action="store_true", help="確認せずに書く"); i.set_defaults(func=cmd_import)

def _post_webapp(payload: dict) -> dict:
    dep = _config().get("form_webapp_deployment")
    req = urllib.request.Request(f"https://script.google.com/macros/s/{dep}/exec", data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r: d = json.load(r)
    if not d.get("ok"): sys.exit("ウェブアプリがエラーを返しました: " + str(d))
    return d["result"]

def _ops_yaml(cid):
    p = ops_contest_dir(cid) / "ops.yaml"
    return p, ((yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {})

def cmd_new(a):
    prev = load_contest(a.prev) if a.prev else None
    share = []
    sa = load_secrets().get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and Path(sa).exists(): share.append(json.loads(Path(sa).read_text())["client_email"])
    ja, en = build_rows(a.id, prev)
    lang = (prev or {}).get("language", "ja")
    spec = rows_to_spec(a.id, ja, en, make_en=(lang == "en"), test=a.test)
    cfg = _config(); key = "definition_book_id_test" if a.test else "definition_book_id"
    spec["book_id"] = cfg.get(key); spec["share_with"] = share
    res = _post_webapp({"fn": "upsertTabs", "spec": spec})
    from ..form.cli import _save_config
    _save_config(**{key: res["book_id"]})
    p, d = _ops_yaml(a.id); d["definition_book_id"] = res["book_id"]; d["definition_tabs"] = res["tabs"]
    p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"大会定義シートにタブを作りました: {res['book_url']}\n  タブ: {', '.join(res['tabs'])}\n  B 列を埋めたら: ops contest import {a.id}")

def cmd_import(a):
    p, d = _ops_yaml(a.id); bid = d.get("definition_book_id")
    if not bid: sys.exit(f"大会定義シートがありません（ops contest new {a.id}）")
    from ..gsheets import _service
    svc = _service()
    titles = [s["properties"]["title"] for s in svc.spreadsheets().get(spreadsheetId=bid, fields="sheets.properties.title").execute()["sheets"]]
    want = [t for t in (a.id, a.id + "_en") if t in titles]
    if a.id not in want: sys.exit(f"タブ {a.id} がありません（あるタブ: {titles}）")
    res = svc.spreadsheets().values().batchGet(spreadsheetId=bid, ranges=[f"'{t}'!A:E" for t in want], valueRenderOption="FORMATTED_VALUE").execute()
    got = {t: vr.get("values", []) for t, vr in zip(want, res["valueRanges"])}
    contest = tabs_to_contest(a.id, got[a.id], got.get(a.id + "_en"))
    from .sheet import load_fields
    missing = [q["key"] for q in load_fields()["basic"] if q.get("required") and not _nested(contest, q["key"])]
    if missing: print("未記入の必須項目:", ", ".join(missing))
    new = "# 大会定義シートから ops contest import が生成。直すときはシートを直して import し直す。\n" + yaml.safe_dump(contest, allow_unicode=True, sort_keys=False, width=200)
    dst = contest_dir(a.id) / "contest.yaml"; dst.parent.mkdir(parents=True, exist_ok=True)
    old = dst.read_text(encoding="utf-8") if dst.exists() else ""
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "現在", "シート", lineterm=""))
    if not diff: print("変更なし"); return
    print("\n".join(diff[:120])); print(f"... ({len(diff)} 行の差分)" if len(diff) > 120 else "")
    if not a.yes:
        ans = input(f"{dst} に書きますか？ [y/N] ").strip().lower()
        if ans != "y": print("書きませんでした"); return
    dst.write_text(new, encoding="utf-8"); print(f"書きました: {dst}")

def _nested(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d
