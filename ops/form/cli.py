"""ops form init|create"""
import json, re, shutil, subprocess, sys
import yaml
from pathlib import Path
from ..paths import OPS, ops_contest_dir, load_secrets
from ..contests import load_contest, set_contest_field
from .build import build_spec, render_code_js, describe

GAS_DIR = OPS / "ops/form/gas"

def add_parser(sub):
    p = sub.add_parser("form", help="参加登録フォームの生成")
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("init", help="前回大会の form.yaml をコピーして contests/<id>/form.yaml を作る")
    a.add_argument("id"); a.add_argument("--from", dest="prev", required=True); a.set_defaults(func=cmd_init)
    c = s.add_parser("create", help="フォームと回答シートを作り、URL を contests の contest.yaml に書き戻す")
    c.add_argument("id")
    c.add_argument("--dry-run", action="store_true", help="Google に触らず、質問一覧と生成コードを表示する")
    c.add_argument("--manual", action="store_true", help="clasp run を使わず、push だけして手動実行の案内を出す")
    c.add_argument("--result", help="手動実行のログの RESULT {...} を貼ったファイル。読み取って contest.yaml に書き戻す")
    c.add_argument("--test", action="store_true", help="タイトルに [test] を付ける（あとで消す前提の試し作成）")
    c.add_argument("--via", choices=["webapp", "run"], default="webapp", help="実行方法。webapp=デプロイ済みウェブアプリを OAuth トークンで呼ぶ（既定） run=clasp run")
    c.add_argument("--no-push", action="store_true", help="push を省略（コードを変えていないとき）")
    c.set_defaults(func=cmd_create)

def cmd_init(a):
    src = OPS / "contests" / a.prev / "form.yaml"
    if not src.exists(): sys.exit(f"前回の form.yaml がありません: {src}")
    dst = ops_contest_dir(a.id) / "form.yaml"
    if dst.exists(): sys.exit(f"既にあります: {dst}")
    shutil.copy(src, dst); print(f"作成: {dst}\nタイトルと質問の並びを直してから `ops form create {a.id} --dry-run` で確認してください。")

CONFIG = OPS / "ops/config.yaml"   # 共有の Apps Script プロジェクト ID など（コミットする）

def _config() -> dict:
    return (yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}) if CONFIG.exists() else {}

def _save_config(**kv):
    d = _config(); d.update(kv); CONFIG.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")

def _all_specs(secrets: dict) -> dict:
    """form.yaml を持つ全大会の仕様。1 つのスクリプトにまとめて push する"""
    share = []
    sa = secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and Path(sa).exists(): share.append(json.loads(Path(sa).read_text())["client_email"])
    specs = {}
    for fy in sorted((OPS / "contests").glob("*/form.yaml")):
        cid = fy.parent.name
        specs[cid] = build_spec(cid, load_contest(cid), yaml.safe_load(fy.read_text(encoding="utf-8")), share)
    return specs

def _save_ops(cid: str, **kv):
    p = ops_contest_dir(cid) / "ops.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    d = d or {}; d.update(kv)
    p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")

def _access_token() -> str:
    """clasp のログイン（~/.clasprc.json）からアクセストークンを取り、期限切れなら refresh する"""
    import time, urllib.request, urllib.parse
    rc = Path.home() / ".clasprc.json"
    if not rc.exists(): sys.exit("clasp にログインしていません: clasp login --no-localhost --creds ~/.ops/clasp_client_secret.json")
    d = json.loads(rc.read_text()); t = d["tokens"]["default"]
    body = urllib.parse.urlencode({"client_id": t["client_id"], "client_secret": t["client_secret"], "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
            tok = json.load(r)
    except Exception as e:
        sys.exit("トークンの更新に失敗しました（7 日で失効します）。ログインし直してください:\n  clasp login --no-localhost --creds ~/.ops/clasp_client_secret.json\n" + str(e))
    t["access_token"] = tok["access_token"]; rc.write_text(json.dumps(d)); return tok["access_token"]

def _call_webapp(fn: str, **params) -> dict:
    import urllib.request, urllib.parse
    dep = _config().get("form_webapp_deployment")
    if not dep: sys.exit("ops/config.yaml に form_webapp_deployment がありません（docs/setup_google.md の『ウェブアプリのデプロイ』）")
    url = f"https://script.google.com/macros/s/{dep}/exec?" + urllib.parse.urlencode({"fn": fn, **params})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _access_token()})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    if not d.get("ok"): sys.exit("ウェブアプリがエラーを返しました: " + str(d))
    return d["result"]

def _write_back(cid: str, result: dict):
    set_contest_field(cid, "form_url", result["form_url"])
    _save_ops(cid, form_id=result["form_id"], form_edit_url=result["form_edit_url"], sheet_id=result["sheet_id"], sheet_url=result["sheet_url"])
    print("書き戻し:")
    print(f"  contests/{cid}/contest.yaml  form_url: {result['form_url']}")
    print(f"  ops contests/{cid}/ops.yaml  sheet_id / form_edit_url / sheet_url")

def cmd_create(a):
    cid = a.id
    contest = load_contest(cid)
    fy = ops_contest_dir(cid) / "form.yaml"
    if not fy.exists(): sys.exit(f"form.yaml がありません: {fy}\n`ops form init {cid} --from <前回>` で作ってください。")
    secrets = load_secrets()
    specs = _all_specs(secrets)
    if a.test:
        for sp in specs.values(): sp["title"] = "[test] " + sp["title"]
    spec = specs[cid]
    print(describe(spec)); print()
    if a.result:
        m = re.search(r"\{.*\}", Path(a.result).read_text(encoding="utf-8"), re.S)
        if not m: sys.exit("RESULT の JSON が見つかりません")
        _write_back(cid, json.loads(m.group(0))); return
    if a.dry_run:
        print("--- 生成される Code.js ---"); print(render_code_js(specs)); print("(dry-run: Google には触っていません)"); return
    (GAS_DIR / "Code.js").write_text(render_code_js(specs), encoding="utf-8")
    sid = _config().get("form_script_id")
    clasp_json = GAS_DIR / ".clasp.json"
    if not sid:
        if clasp_json.exists(): clasp_json.unlink()
        r = subprocess.run(["clasp", "create", "--type", "standalone", "--title", "aiwolf-nlp-ops form"], cwd=GAS_DIR, capture_output=True, text=True)
        if r.returncode != 0: sys.exit("clasp create に失敗:\n" + r.stdout + r.stderr)
        sid = json.loads(clasp_json.read_text())["scriptId"]; _save_config(form_script_id=sid)
        print(f"Apps Script プロジェクトを作成: aiwolf-nlp-ops form ({sid})")
    else:
        clasp_json.write_text(json.dumps({"scriptId": sid, "rootDir": "."}), encoding="utf-8")
    if not a.no_push:
        r = subprocess.run(["clasp", "push", "--force"], cwd=GAS_DIR, capture_output=True, text=True)
        if r.returncode != 0: sys.exit("clasp push に失敗:\n" + r.stdout + r.stderr)
        print(f"clasp push 完了（{', '.join(specs)} の {len(specs)} 大会分）")
        if a.via == "webapp":
            # ウェブアプリは版を固定して配信されるので、push のたびに新しい版をデプロイして同じデプロイ ID を更新する
            dep = _config().get("form_webapp_deployment")
            if dep:
                r = subprocess.run(["clasp", "deploy", "-i", dep, "-d", "webapp"], cwd=GAS_DIR, capture_output=True, text=True)
                if r.returncode != 0: sys.exit("clasp deploy に失敗:\n" + r.stdout + r.stderr)
    fn = f"createForm_{cid}"
    if a.manual:
        print(f"手動実行: https://script.google.com/d/{sid}/edit を開き、関数 {fn} を実行（初回は権限の承認）。")
        print(f"実行ログの RESULT {{...}} をファイルに貼って `ops form create {cid} --result <file>` で書き戻します。")
        return
    if a.via == "webapp":
        result = _call_webapp("createForm", cid=cid)
        _write_back(cid, result); return
    r = subprocess.run(["clasp", "run", fn], cwd=GAS_DIR, capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re.search(r"\{.*\}", out, re.S)
    if r.returncode != 0 or not m:
        print(out)
        sys.exit("clasp run に失敗しました。--via webapp（既定）を使ってください。")
    raw = m.group(0)
    _write_back(cid, json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw))
