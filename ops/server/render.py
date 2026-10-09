"""contest.yaml + roles + teams.yaml → 大会サーバ用の設定一式（トラックごとの yml・接続確認用 yml・teams.yml・Makefile）

公開ディレクトリの規則: /var/www/html/aiwolf/<年>/<round.public_name>/<MainTruck{size} | MainTruck_freeform{size} | PreTruck…>/{json,log}
ポートの規則: ターン式 8000+人数、いつでも発話 8100+人数（接続確認用も同じ。接続確認と本戦は同時には動かさない）
"""
import copy, re, subprocess, sys
from pathlib import Path
import yaml
from ..paths import OPS, CONTESTS, contest_dir, ops_contest_dir

TPL = OPS / "ops/server/templates"
ROLE_KEYS = ["WEREWOLF", "POSSESSED", "SEER", "BODYGUARD", "VILLAGER", "MEDIUM"]

def track_dir(track: dict, pre: bool = False) -> str:
    base = "PreTruck" if pre else "MainTruck"
    return f"{base}_freeform{track['size']}" if track.get("mode") == "anytime" else f"{base}{track['size']}"

def port_of(track: dict) -> int:
    return (8100 if track.get("mode") == "anytime" else 8000) + int(track["size"])

def roles_block(size: int) -> dict:
    roles = yaml.safe_load((CONTESTS / "roles" / f"{size}.yaml").read_text(encoding="utf-8"))
    counts = {k: 0 for k in ROLE_KEYS}
    for r in roles: counts[r["role"]] = int(r["count"])
    return {int(size): counts}

def year_of(contest: dict) -> str:
    for r in contest.get("rounds", []):
        for m in r.get("milestones", []):
            if m.get("date"): return str(m["date"])[:4]
    return str(contest.get("venue", {}).get("start", ""))[:4]

def render_config(contest: dict, rnd: dict, track: dict, teams: list[str], pre: bool) -> dict:
    lang = contest.get("language", "ja"); rules = contest.get("rules", {})
    base = yaml.safe_load((TPL / f"base_{lang}.yml").read_text(encoding="utf-8"))
    c = copy.deepcopy(base); size = int(track["size"]); anytime = track.get("mode") == "anytime"
    year = year_of(contest); pub = f"/var/www/html/aiwolf/{year}/{rnd['public_name']}"
    tdir = track_dir(track, pre); public = f"{pub}/{tdir}"
    c["server"]["web_socket"]["port"] = port_of(track)
    c["server"]["timeout"]["action"] = f"{int(rules.get('response_timeout_sec', 60))}s"
    g = c["game"]; g["agent_count"] = size
    per_agent = int(rules.get("anytime_talks_per_day", 4)) if anytime else 4
    talk = g["talk"]
    if anytime:
        talk = {"duration": f"{int(rules.get('anytime_phase_min', 10))}m", **{k: v for k, v in talk.items() if k != "duration"}}
    else:
        talk.pop("duration", None)
    talk["max_count"] = {"per_agent": per_agent, "per_day": per_agent * size}
    g["talk"] = talk
    wolves = roles_block(size)[size]["WEREWOLF"]
    g["whisper"]["max_count"] = {"per_agent": 4 if wolves > 1 else 0, "per_day": 4 * wolves if wolves > 1 else 0}
    chars = int(rules.get("talk_chars", 125)); mention = int(rules.get("mention_chars") or chars)
    for sec in ("talk", "whisper"):
        g[sec]["max_length"]["base_length"] = chars; g[sec]["max_length"]["mention_length"] = mention
    c["logic"]["roles"] = roles_block(size)
    m = c["matching"]
    if pre:
        m.update({"self_match": True, "is_optimize": False, "team_count": size, "game_count": size, "output_path": "./log/match_optimizer.json"})
    else:
        m.update({"self_match": False, "is_optimize": True, "team_count": len(teams), "game_count": 0, "output_path": f"./log/match_optimizer_{track['id']}.json"})
    c["json_logger"]["output_dir"] = f"{public}/json"; c["game_logger"]["output_dir"] = f"{public}/log"
    for k in ("status_monitor", "live_metrics"): c.pop(k, None)
    if not pre:
        c["status_monitor"] = {"output_path": f"{public}/status.txt", "interval": 5, "server_log_path": f"./log_{track['id']}.log", "max_remaining_matches": 0}
        c["live_metrics"] = {"output_dir": public, "interval": 30, "sort_success": True, "dataset": f"{rnd['public_name']}_{tdir}"}
    return c

def plan_game_count(cfg_path: Path, teams_yml: Path, track_key: str, lo: int, hi: int) -> int | None:
    """plan_game_count.py を使って総ゲーム数を決める。見つからなければ None"""
    r = subprocess.run([sys.executable, str(OPS / "ops/server/scripts/plan_game_count.py"), "--config", str(cfg_path), "--teams-yml", str(teams_yml),
                        "--track", track_key, "--min-per-team", str(lo), "--max-per-team", str(hi)], capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re.search(r"最小は G=(\d+)", out) or re.search(r"--game-count (\d+)", out)
    return int(m.group(1)) if m else None

def render(cid: str, contest: dict, round_id: str, teams: list[dict], out_dir: Path) -> dict:
    rnd = next((r for r in contest["rounds"] if r["id"] == round_id), None)
    if not rnd: sys.exit(f"回 {round_id} が contest.yaml にありません")
    if not rnd.get("public_name"): sys.exit(f"rounds[{round_id}].public_name（公開ディレクトリ名。例: INLG2）を contest.yaml に書いてください")
    out_dir.mkdir(parents=True, exist_ok=True); (out_dir / "log").mkdir(exist_ok=True)
    tracks = [t for t in contest["tracks"] if t["id"] in rnd.get("tracks", [t["id"] for t in contest["tracks"]])]
    teams_yml = {}
    for t in tracks:
        teams_yml[f"track_{t['id']}"] = [x["team"] for x in teams if t["id"] in x.get("tracks", []) and round_id in x.get("rounds", [round_id])]
    (out_dir / "teams.yml").write_text(yaml.safe_dump(teams_yml, allow_unicode=True, sort_keys=False), encoding="utf-8")
    summary = {}
    rules_mk = []
    for t in tracks:
        names = teams_yml[f"track_{t['id']}"]
        for pre in (False, True):
            cfg = render_config(contest, rnd, t, names, pre)
            p = out_dir / f"{t['id']}{'_pre' if pre else ''}.yml"
            p.write_text("# ops server render が生成（元: ops/server/templates/base_%s.yml）。手で直すなら contest.yaml / 雛形を。\n" % contest.get("language", "ja")
                         + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        lo, hi = (t.get("games_per_team") or [None, None])
        games = None
        if lo and names:
            games = plan_game_count(out_dir / f"{t['id']}.yml", out_dir / "teams.yml", f"track_{t['id']}", lo, hi)
        if games:
            p = out_dir / f"{t['id']}.yml"; s = p.read_text(encoding="utf-8")
            s = re.sub(r"^(\s*game_count:) 0$", rf"\1 {games}", s, count=1, flags=re.M); p.write_text(s, encoding="utf-8")
        summary[t["id"]] = {"teams": len(names), "games": games, "port": port_of(t), "dir": track_dir(t)}
        rules_mk.append((TPL / "track.mk.tmpl").read_text(encoding="utf-8").replace("{{T}}", t["id"]).replace("{{LABEL}}", t.get("name", t["id"]))
                        .replace("{{PORT}}", str(port_of(t))).replace("{{TEAMS}}", str(len(names))).replace("{{GAMES}}", str(games or "?"))
                        .replace("{{MIN}}", str(lo or 1)).replace("{{MAX}}", str(hi or lo or 1)))
    mk = (TPL / "Makefile.tmpl").read_text(encoding="utf-8").replace("{{CID}}", cid).replace("{{ROUND}}", round_id).replace("{{TRACKS}}", " ".join(t["id"] for t in tracks)).replace("{{TRACK_RULES}}", "\n".join(rules_mk))
    (out_dir / "Makefile").write_text(mk, encoding="utf-8")
    for s in ("plan_game_count.py", "generate_match_optimizer.py", "monitor_status.py"):
        (out_dir / s).write_bytes((OPS / "ops/server/scripts" / s).read_bytes())
    return summary
