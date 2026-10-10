"""ops contest new|import  — 大会定義シート（行 = 項目、列 = 大会）で contest.yaml を作る"""
import datetime, difflib, json, sys, urllib.request
import yaml
from pathlib import Path
from ..paths import CONTESTS, contest_dir, load_secrets
from ..contests import load_contest
from ..form.cli import _access_token, _config, _save_config
from .sheet import (TAB_JA, TAB_EN, template, fill, grid_tab, catalog_tabs, grid_columns, column_items, items_to_contest,
                    catalog_from_tabs, save_catalog, load_fields, load_catalog)

def add_parser(sub):
    p = sub.add_parser("contest", help="大会定義シート（列 = 大会）の作成と、シートから contest.yaml の生成")
    s = p.add_subparsers(dest="cmd", required=True)
    n = s.add_parser("new", help="シートに大会の列を足す（--from の大会の値を入れておく。省略時は自分の contest.yaml があればそれを写す）")
    n.add_argument("id"); n.add_argument("--from", dest="prev"); n.add_argument("--test", action="store_true")
    n.add_argument("--full", action="store_true", help="日付やフォーム URL も前回の値を入れる"); n.set_defaults(func=cmd_new)
    i = s.add_parser("import", help="シートの列を読んで contests/<id>/contest.yaml を書く（差分を表示）")
    i.add_argument("id", nargs="?"); i.add_argument("--all", action="store_true"); i.add_argument("--test", action="store_true")
    i.add_argument("--yes", action="store_true", help="確認せずに書く"); i.set_defaults(func=cmd_import)
    u = s.add_parser("url", help="大会定義シートの URL を表示"); u.add_argument("--test", action="store_true"); u.set_defaults(func=cmd_url)

def _post_webapp(payload: dict) -> dict:
    dep = _config().get("form_webapp_deployment")
    req = urllib.request.Request(f"https://script.google.com/macros/s/{dep}/exec", data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r: d = json.load(r)
    if not d.get("ok"): sys.exit("ウェブアプリがエラーを返しました: " + str(d))
    return d["result"]

def _book_key(a): return "definition_book_id_test" if a.test else "definition_book_id"

def _read_tabs(book_id: str, names: list[str]) -> dict[str, list[list]]:
    from ..gsheets import _service
    svc = _service()
    titles = [s["properties"]["title"] for s in svc.spreadsheets().get(spreadsheetId=book_id, fields="sheets.properties.title").execute()["sheets"]]
    want = [t for t in names if t in titles]
    if not want: return {}
    res = svc.spreadsheets().values().batchGet(spreadsheetId=book_id, ranges=[f"'{t}'" for t in want], valueRenderOption="FORMATTED_VALUE").execute()
    return {t: vr.get("values", []) for t, vr in zip(want, res["valueRanges"])}

def _tab_titles(book_id: str | None) -> list[str]:
    if not book_id: return []
    from ..gsheets import _service
    return [s["properties"]["title"] for s in _service().spreadsheets().get(spreadsheetId=book_id, fields="sheets.properties.title").execute()["sheets"]]

def _current(book_id: str | None):
    """シートの今の中身を (大会 id → contest 辞書, catalog) に戻す。シートが無ければ空"""
    if not book_id: return {}, load_catalog()
    got = _read_tabs(book_id, [TAB_JA, TAB_EN, "トラック", "トラック_en", "ルール"])
    catalog = catalog_from_tabs(got.get("トラック"), got.get("トラック_en"), got.get("ルール"))
    ja, en = got.get(TAB_JA, []), got.get(TAB_EN, [])
    contests = {cid: items_to_contest(cid, column_items(ja, cid), column_items(en, cid), catalog) for cid in grid_columns(ja)}
    return contests, catalog

def _past_ids(contests: dict, today=None) -> list[str]:
    today = today or datetime.date.today(); out = []
    for cid, c in contests.items():
        e = (c.get("venue") or {}).get("end")
        try:
            if e and datetime.date.fromisoformat(str(e)[:10]) < today: out.append(cid)
        except ValueError: pass
    return out

def cmd_new(a):
    cfg = _config(); book_id = cfg.get(_book_key(a))
    contests, catalog = _current(book_id)
    if a.id in contests: sys.exit(f"列 {a.id} は既にあります。直すときはシートを直して import してください")
    if a.prev: prev, full = load_contest(a.prev), a.full
    elif (contest_dir(a.id) / "contest.yaml").exists(): prev, full = load_contest(a.id), True        # 既存の大会を写す
    else: prev, full = (list(contests.values())[-1] if contests else {}), a.full
    n_rounds = max(2, *(len(c.get("rounds", [])) for c in list(contests.values()) + [prev]))
    n_sp = max(3, *(len(c.get("sponsors") or []) for c in list(contests.values()) + [prev]))
    ja_rows, en_rows = template(n_rounds, n_sp)
    fill(ja_rows, contests, a.id, prev, full); fill(en_rows, contests, a.id, prev, full)
    col_ids = list(contests.keys()) + [a.id]; past = _past_ids(contests)
    tabs = catalog_tabs() + [grid_tab(TAB_JA, ja_rows, col_ids, False, past_ids=past), grid_tab(TAB_EN, en_rows, col_ids, True, past_ids=past)]
    share = []
    sa = load_secrets().get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and Path(sa).exists(): share.append(json.loads(Path(sa).read_text())["client_email"])
    res = _post_webapp({"fn": "upsertGrid", "spec": {"book_id": book_id, "title": ("[test] " if a.test else "") + "大会定義", "tabs": tabs, "share_with": share, "public": True,
                                                   "drop_tabs": [t for t in _tab_titles(book_id) if t not in (TAB_JA, TAB_EN, "トラック", "トラック_en", "ルール")]}})
    _save_config(**{_book_key(a): res["book_id"]})
    print(f"大会定義シートに列 {a.id} を足しました: {res['book_url']}\n  列: {', '.join(col_ids)}\n  埋めたら: ops contest import {a.id}")

def cmd_url(a):
    bid = _config().get(_book_key(a)); print(f"https://docs.google.com/spreadsheets/d/{bid}/edit" if bid else "まだありません（ops contest new <id>）")

def _nested(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def cmd_import(a):
    book_id = _config().get(_book_key(a))
    if not book_id: sys.exit("大会定義シートがありません（ops contest new <id>）")
    contests, catalog = _current(book_id)
    save_catalog(*catalog)
    ids = list(contests.keys()) if a.all else [a.id]
    if not a.all and not a.id: sys.exit("大会 id か --all を指定してください")
    for cid in ids:
        if cid not in contests: print(f"列 {cid} がありません（ある列: {list(contests.keys())}）"); continue
        contest = contests[cid]
        missing = [q["key"] for q in load_fields()["basic"] if q.get("required") and not _nested(contest, q["key"])]
        if missing: print(f"[{cid}] 未記入の必須項目:", ", ".join(missing))
        new = "# 大会定義シートから ops contest import が生成。直すときはシートを直して import し直す。\n" + yaml.safe_dump(contest, allow_unicode=True, sort_keys=False, width=200)
        dst = contest_dir(cid) / "contest.yaml"; dst.parent.mkdir(parents=True, exist_ok=True)
        old = dst.read_text(encoding="utf-8") if dst.exists() else ""
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "現在", "シート", lineterm=""))
        if not diff: print(f"[{cid}] 変更なし"); continue
        print("\n".join(diff[:120])); print(f"... ({len(diff)} 行の差分)" if len(diff) > 120 else "")
        if not a.yes:
            if input(f"{dst} に書きますか？ [y/N] ").strip().lower() != "y": print("書きませんでした"); continue
        dst.write_text(new, encoding="utf-8"); print(f"書きました: {dst}")
