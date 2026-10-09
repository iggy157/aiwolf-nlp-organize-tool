"""ops server render|deploy|make"""
import subprocess, sys, shlex
import yaml
from pathlib import Path
from ..paths import OPS, contest_dir, ops_contest_dir
from ..contests import load_contest
from .render import render

def add_parser(sub):
    p = sub.add_parser("server", help="大会サーバの設定一式の生成・配置・操作")
    s = p.add_subparsers(dest="cmd", required=True)
    r = s.add_parser("render", help="contest.yaml と teams.yaml から回ごとの設定一式を ops/contests/<id>/server/<round>/ に生成")
    r.add_argument("id"); r.add_argument("round"); r.add_argument("--teams", help="チーム一覧 YAML（既定: contests の teams.yaml）"); r.set_defaults(func=cmd_render)
    d = s.add_parser("deploy", help="生成した設定一式を大会サーバへ rsync し、公開ディレクトリとサーババイナリを用意する")
    d.add_argument("id"); d.add_argument("round"); d.add_argument("--host", default="aiwolf"); d.add_argument("--dir", help="サーバ側の作業ディレクトリ（既定: ops.yaml の server_dirs[round] か ~/<id>-<round>）")
    d.add_argument("--binary-from", help="サーババイナリをコピーする既存ディレクトリ（既定: サーバ上の最新の大会ディレクトリを探す）"); d.set_defaults(func=cmd_deploy)
    m = s.add_parser("make", help="サーバ側の作業ディレクトリで make <target> を実行（例: check plan-all optimize-all run-turn5 status-turn5 stop-turn5 live）")
    m.add_argument("id"); m.add_argument("round"); m.add_argument("target", nargs="+"); m.add_argument("--host", default="aiwolf"); m.set_defaults(func=cmd_make)

def _server_dir(cid, rnd, override=None):
    if override: return override
    p = ops_contest_dir(cid) / "ops.yaml"
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    return (d.get("server_dirs") or {}).get(rnd) or f"~/{cid}-{rnd}"

def cmd_render(a):
    contest = load_contest(a.id)
    tp = Path(a.teams) if a.teams else contest_dir(a.id) / "teams.yaml"
    if not tp.exists(): sys.exit(f"チーム一覧がありません: {tp}（ops sync で作られます。試すときは --teams で指定）")
    teams = (yaml.safe_load(tp.read_text(encoding="utf-8")) or {}).get("teams", [])
    out = ops_contest_dir(a.id) / "server" / a.round
    summary = render(a.id, contest, a.round, teams, out)
    print(f"生成: {out}")
    for t, s in summary.items(): print(f"  {t:10} port {s['port']}  teams {s['teams']:3}  games {s['games']}  → {s['dir']}")
    print("次: ops server deploy", a.id, a.round)

def cmd_deploy(a):
    src = ops_contest_dir(a.id) / "server" / a.round
    if not src.exists(): sys.exit(f"先に ops server render {a.id} {a.round} を実行してください")
    dest = _server_dir(a.id, a.round, a.dir)
    pubs = sorted({l.split(":",1)[1].strip().rsplit("/",1)[0] for f in src.glob("*.yml") for l in f.read_text(encoding="utf-8").splitlines() if l.strip().startswith("output_dir: /var/www")})
    bin_from = a.binary_from or "$(ls -dt ~/inlg* ~/jsai* ~/aiwolfdial* 2>/dev/null | head -1)"
    remote = f"""set -e; mkdir -p {dest}/log; cd {dest}
for d in {' '.join(shlex.quote(p) for p in pubs)}; do mkdir -p "$d/json" "$d/log"; done
if [ ! -x aiwolf-nlp-server-linux-amd64 ]; then src={bin_from}; cp "$src/aiwolf-nlp-server-linux-amd64" . && echo "binary: copied from $src"; fi
[ -d ~/aiwolf-nlp-calculate-score ] || echo "注意: ~/aiwolf-nlp-calculate-score がありません（配信を使うなら clone して uv sync）"
echo "deployed to {dest}"; ls"""
    subprocess.run(["rsync", "-a", "--exclude", "log/", f"{src}/", f"{a.host}:{dest}/"], check=True)
    subprocess.run(["ssh", a.host, remote], check=True)
    p = ops_contest_dir(a.id) / "ops.yaml"; d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    d.setdefault("server_dirs", {})[a.round] = dest; p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")

def cmd_make(a):
    dest = _server_dir(a.id, a.round)
    subprocess.run(["ssh", a.host, f"cd {dest} && make {' '.join(a.target)}"], check=False)
