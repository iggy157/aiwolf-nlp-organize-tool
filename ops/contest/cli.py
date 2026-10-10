"""ops contest layout|import|button|url — 大会定義シート（行 = 項目、列 = 大会）

新しい大会はシートの空いている列の 1 行目に id を書いて埋め、シートのメニュー「大会データ → 大会データを更新」を押す。
押すと contest-data の GitHub Actions がシートを読んで contest.yaml を書き、push する。ここにあるのはその周りの道具。
"""
import json, subprocess, sys, urllib.request
from pathlib import Path
import yaml
from ..paths import CONTESTS, OPS, load_secrets
from ..form.cli import _access_token, _config, _save_config
from .. import gitops
from .sheet import SI, TAB_JA, TAB_EN, build_tabs

BOUND_DIR = OPS / "ops" / "contest" / "gas_bound"

def add_parser(sub):
    p = sub.add_parser("contest", help="大会定義シート（列 = 大会）")
    s = p.add_subparsers(dest="cmd", required=True)
    l = s.add_parser("layout", help="シートの形（行・型・色）を作り直す。値はそのまま残る。fields.yaml の項目を変えたときに使う")
    l.add_argument("--from-files", action="store_true", help="シートでなく contest-data の contest.yaml から値を入れる（初回）"); l.set_defaults(func=cmd_layout)
    i = s.add_parser("import", help="シートを読んで contest.yaml を書く（ボタンと同じ処理を手元で。差分を見せて確認）")
    i.add_argument("ids", nargs="*"); i.add_argument("--yes", action="store_true"); i.add_argument("--push", action="store_true", help="書いたあと commit して push")
    i.set_defaults(func=cmd_import)
    b = s.add_parser("button", help="シートに「大会データ」メニュー（更新ボタン）を付ける／更新する"); b.set_defaults(func=cmd_button)
    u = s.add_parser("url", help="シートの URL"); u.set_defaults(func=cmd_url)

def _book():
    bid = yaml.safe_load((CONTESTS / "sheet.yaml").read_text(encoding="utf-8"))["book_id"]
    if not bid: sys.exit("contest-data の sheet.yaml に book_id がありません")
    return bid

def _post_webapp(payload: dict) -> dict:
    dep = _config().get("form_webapp_deployment")
    req = urllib.request.Request(f"https://script.google.com/macros/s/{dep}/exec", data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r: d = json.load(r)
    if not d.get("ok"): sys.exit("ウェブアプリがエラーを返しました: " + str(d))
    return d["result"]

def read_grids(book_id: str) -> dict[str, list[list]]:
    from ..gsheets import _service
    svc = _service()
    titles = [s["properties"]["title"] for s in svc.spreadsheets().get(spreadsheetId=book_id, fields="sheets.properties.title").execute()["sheets"]]
    want = [t for t in (TAB_JA, TAB_EN, "トラック", "トラック_en", "ルール") if t in titles]
    res = svc.spreadsheets().values().batchGet(spreadsheetId=book_id, ranges=[f"'{t}'" for t in want], valueRenderOption="FORMATTED_VALUE").execute()
    return {t: vr.get("values", []) for t, vr in zip(want, res["valueRanges"])}

def cmd_layout(a):
    book = _book(); gitops.pull()
    grids = read_grids(book)
    catalog = SI.catalog_from_tabs(grids.get("トラック"), grids.get("トラック_en"), grids.get("ルール"))
    if a.from_files:
        contests = {}
        for p in sorted((CONTESTS / "contests").glob("*/contest.yaml")):
            if p.parent.name.startswith("_"): continue
            contests[p.parent.name] = yaml.safe_load(p.read_text(encoding="utf-8"))
        contests = dict(sorted(contests.items(), key=lambda kv: str((kv[1].get("venue") or {}).get("start") or "9999")))
    else:
        ja, en = grids.get(TAB_JA, []), grids.get(TAB_EN, [])
        contests = {cid: SI.items_to_contest(cid, SI.column_items(ja, cid), SI.column_items(en, cid), catalog) for cid in SI.grid_columns(ja)}
    tabs = build_tabs(contests, grids.get(TAB_JA), grids.get(TAB_EN), from_sheet=not a.from_files)
    share = []
    sa = load_secrets().get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and Path(sa).exists(): share.append(json.loads(Path(sa).read_text())["client_email"])
    res = _post_webapp({"fn": "upsertGrid", "spec": {"book_id": book, "tabs": tabs, "share_with": share, "public": True}})
    print(f"シートの形を作り直しました: {res['book_url']}\n  大会の列: {', '.join(contests) or '（なし）'}")

def cmd_import(a):
    book = _book(); gitops.pull()
    res = SI.import_grids(read_grids(book), write=False, only=a.ids or None)
    for w in res["warnings"]: print("⚠", w)
    if not res["diffs"]: print("変更なし"); return
    for cid, d in res["diffs"].items(): print(f"===== {cid}\n{d}")
    if not a.yes and input("書きますか？ [y/N] ").strip().lower() != "y": print("書きませんでした"); return
    res = SI.import_grids(read_grids(book), write=True, only=a.ids or None)
    print("書きました:", ", ".join(res["changed"]))
    if a.push and gitops.commit_push(["contests", "catalog"], f"data: 大会定義シートから更新（{','.join(res['changed'])}）"):
        print("push しました")

def cmd_url(a):
    print(f"https://docs.google.com/spreadsheets/d/{_book()}/edit")

def _contest_data_repo() -> str:
    url = subprocess.run(["git", "-C", str(CONTESTS), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    import re
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m: sys.exit(f"contest-data の origin が GitHub ではありません: {url}")
    return m.group(1)

def cmd_button(a):
    """シートに紐づいた Apps Script（メニュー「大会データ」）を作る／更新する"""
    book = _book(); repo = _contest_data_repo()
    branch = subprocess.run(["git", "-C", str(CONTESTS), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip() or "master"
    BOUND_DIR.mkdir(parents=True, exist_ok=True)
    src = (Path(__file__).parent / "bound.js").read_text(encoding="utf-8")
    (BOUND_DIR / "Code.js").write_text(src.replace("__REPO__", repo).replace("__REF__", branch), encoding="utf-8")
    (BOUND_DIR / "appsscript.json").write_text(json.dumps({
        "timeZone": "Asia/Tokyo", "runtimeVersion": "V8", "exceptionLogging": "STACKDRIVER",
        "oauthScopes": ["https://www.googleapis.com/auth/spreadsheets.currentonly", "https://www.googleapis.com/auth/script.external_request",
                        "https://www.googleapis.com/auth/script.container.ui", "https://www.googleapis.com/auth/userinfo.email"]}, indent=2), encoding="utf-8")
    cj = BOUND_DIR / ".clasp.json"
    sid = _config().get("definition_bound_script_id")
    if not sid:
        # clasp create --parentId は親を無視して新しいシートを作ることがあるので、Apps Script API で直接作る
        req = urllib.request.Request("https://script.googleapis.com/v1/projects", data=json.dumps({"title": "大会定義 ボタン", "parentId": book}).encode(),
                                     headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r: proj = json.load(r)
        if proj.get("parentId") != book: sys.exit(f"シートに紐づけられませんでした: {proj}")
        sid = proj["scriptId"]; _save_config(definition_bound_script_id=sid)
    cj.write_text(json.dumps({"scriptId": sid, "rootDir": "."}), encoding="utf-8")
    r = subprocess.run(["clasp", "push", "--force"], cwd=BOUND_DIR, capture_output=True, text=True)
    if r.returncode != 0: sys.exit("clasp push が失敗しました:\n" + r.stdout + r.stderr)
    print(f"シートに「大会データ」メニューを付けました（リポジトリ {repo}、ブランチ {branch}）。\n"
          f"  シートを開き直すとメニューが出ます。初回はトークンの設定と承認を求められます（README の『更新ボタン』）。")
