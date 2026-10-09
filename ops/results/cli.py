"""ops results config|fetch|build|site
決着ログ → 勝率・ゲーム指標・ジャッジ → contests の results.yaml → サイト、をつなぐ。
重い処理（ジャッジの実行）は含めない。各リポジトリの README に従って回し、その出力パスを設定に書く。
"""
import subprocess, sys, os
import yaml
from pathlib import Path
from ..paths import OPS, contest_dir, ops_contest_dir
from ..contests import load_contest
from ..server.render import track_dir, year_of

SITE = Path(os.environ.get("AIWOLF_SITE", OPS.parent / "aiwolf-nlp")).resolve()
LOGS = Path(os.environ.get("AIWOLF_LOGS", Path.home() / "work" / "aiwolf-logs"))
SCORE = Path(os.environ.get("AIWOLF_SCORE", Path.home() / "aiwolf-nlp-calculate-score"))
LOG_HOST = "https://133.167.32.100/aiwolf"

def add_parser(sub):
    p = sub.add_parser("results", help="結果（勝率・指標・評価）を集めて contests の results.yaml を作り、サイトに反映する")
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("config", help="サイトの scripts/results/contests/<id>.yaml（集計元の設定）を contest.yaml から生成する")
    c.add_argument("id"); c.set_defaults(func=cmd_config)
    f = s.add_parser("fetch", help="大会サーバの決着ログ（log/success）を手元に取得する")
    f.add_argument("id"); f.add_argument("--host", default="aiwolf"); f.set_defaults(func=cmd_fetch)
    b = s.add_parser("build", help="サイトの build_contest_yaml.py を実行して contests の results.yaml を書く")
    b.add_argument("id"); b.set_defaults(func=cmd_build)
    t = s.add_parser("site", help="サイト側で contests の submodule を進めてコミットする（push はしない）")
    t.add_argument("id"); t.set_defaults(func=cmd_site)

def _track_entries(cid, contest):
    year = year_of(contest); multi = len(contest["rounds"]) > 1; out = []
    for r in contest["rounds"]:
        for t in contest["tracks"]:
            if t["id"] not in r.get("tracks", [x["id"] for x in contest["tracks"]]): continue
            tid = f"{r['id']}_{t['id']}" if multi else t["id"]
            short = lambda s: (s or "").split("（")[0].split(" (")[0]
            name = (f"{short(r.get('name'))} " if multi else "") + t["name"]
            name_en = (f"{short(r.get('name_en') or r.get('name'))}, " if multi else "") + (t.get("name_en") or t["name"])
            pub = f"{r['public_name']}/{track_dir(t)}"
            out.append({"id": tid, "name": name, "name_en": name_en, "round": r["id"], "track": t["id"], "public": pub,
                        "logs_url": f"{LOG_HOST}/{year}/{pub}/log/success/",
                        "log_dir": str(LOGS / cid / tid),
                        "team_summary_csv": str(SCORE / "data/output" / f"{r['public_name']}_{track_dir(t)}" / "team_summary.csv"),
                        "server_path": f"/var/www/html/aiwolf/{year}/{pub}/log/success/"})
    return out

def cmd_config(a):
    contest = load_contest(a.id); cfg = SITE / "scripts/results/contests" / f"{a.id}.yaml"
    if cfg.exists():
        print(f"既にあります（上書きしません）: {cfg}"); return
    tracks = []
    for e in _track_entries(a.id, contest):
        tracks.append({"id": e["id"], "name": e["name"], "name_en": e["name_en"], "logs_url": e["logs_url"], "log_dir": e["log_dir"],
                       "team_summary_csv": e["team_summary_csv"], "judge_csvs": [], "judge_models": [], "judge_source": None,
                       "human_totalling_csv": None, "human_source": None})
    doc = {"slug": a.id, "contest": contest["name"], "contest_en": contest.get("name_en", contest["name"]),
           "announced": None, "announced_en": None, "availability": {"human_eval": "pending", "llm_judge": "pending"},
           "human_eval_short": None, "human_eval_short_en": None, "team_names": {}, "awards": [], "tracks": tracks}
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("# ops results config が contest.yaml から生成。ジャッジ・人手評価の出力パスを埋めてから ops results build を実行する。\n"
                   + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"生成: {cfg}\n  judge_csvs / judge_models / human_totalling_csv を埋め、availability を ok にしてから build してください。")

def cmd_fetch(a):
    contest = load_contest(a.id)
    for e in _track_entries(a.id, contest):
        Path(e["log_dir"]).mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["rsync", "-a", "--include", "*.log", "--exclude", "*", f"{a.host}:{e['server_path']}", e["log_dir"] + "/"], capture_output=True, text=True)
        n = len(list(Path(e["log_dir"]).glob("*.log")))
        print(f"  {e['id']:14} {n:4} logs  ← {e['server_path']}" + ("" if r.returncode == 0 else f"  (rsync: {r.stderr.strip()[:80]})"))

def cmd_build(a):
    cfg = SITE / "scripts/results/contests" / f"{a.id}.yaml"
    if not cfg.exists(): sys.exit(f"設定がありません: {cfg}（ops results config {a.id}）")
    r = subprocess.run([sys.executable, str(SITE / "scripts/results/build_contest_yaml.py"), str(cfg)], cwd=SITE)
    if r.returncode != 0: sys.exit("build_contest_yaml.py が失敗しました")
    print(f"results.yaml を書きました: {SITE}/external/aiwolf-nlp-contests/contests/{a.id}/results.yaml\n次: ops results site {a.id}")

def cmd_site(a):
    sub = SITE / "external/aiwolf-nlp-contests"
    subprocess.run(["git", "-C", str(sub), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(sub), "commit", "-q", "-m", f"results: {a.id}"], check=False)
    subprocess.run(["git", "-C", str(sub), "push", "-q"], check=False)
    subprocess.run(["bash", str(SITE / "scripts/contest/sync.sh")], cwd=SITE, check=True)
