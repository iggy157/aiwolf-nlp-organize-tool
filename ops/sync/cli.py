"""ops sync <id> [--once] [--interval 秒] [--no-notify]
回答シート → contests の公開 teams.yaml（チーム名・トラック・回・公開可の表記）と、担当者への DM 通知。
連絡先はファイルに書かない（通知文の中だけ）。既読の管理は ~/.ops/state/<id>.json。
"""
import json, sys, time, datetime
import yaml
from pathlib import Path
from ..paths import OPS, ops_contest_dir, contest_dir
from ..contests import load_contest
from ..gsheets import read_rows
from ..form.build import build_spec
from .. import slack

STATE = Path.home() / ".ops" / "state"

def add_parser(sub):
    p = sub.add_parser("sync", help="回答シートを読んでチーム一覧を更新し、新規登録を通知する")
    p.add_argument("id")
    p.add_argument("--once", action="store_true", help="1 回だけ（既定は --interval ごとに繰り返す）")
    p.add_argument("--interval", type=int, default=300, help="繰り返しの間隔 [秒]。既定 300")
    p.add_argument("--no-notify", action="store_true", help="Slack に通知しない")
    p.set_defaults(func=cmd_sync)

def _columns(cid: str, contest: dict, header: list[str]) -> dict:
    """質問 id → シートの列名。フォーム生成と同じ仕様からラベルを引いて見出しと突き合わせる"""
    fy = ops_contest_dir(cid) / "form.yaml"
    spec = build_spec(cid, contest, yaml.safe_load(fy.read_text(encoding="utf-8")))
    cols = {}
    for q in spec["questions"]:
        hit = next((h for h in header if h.strip() == q["label"].strip()), None) or next((h for h in header if h.strip().startswith(q["label"].strip()[:20])), None)
        if hit: cols[q["id"]] = hit
    return cols, spec

def _ids_from_options(value: str, spec_q: dict, items: list[dict]) -> list[str]:
    """チェックボックス/ラジオの回答文字列を、contest.yaml の id に戻す"""
    out = []
    for opt, it in zip(spec_q.get("options", []), items):
        if opt in value: out.append(it["id"])
    return out

def _round_ids(value: str, contest: dict) -> list[str]:
    rounds = contest.get("rounds", [])
    if len(rounds) < 2: return [r["id"] for r in rounds]
    short = lambda s: (s or "").split("（")[0].split(" (")[0]
    if "＋" in value or " + " in value: return [r["id"] for r in rounds]
    for r in rounds:
        if short(r.get("name")) and short(r.get("name")) in value: return [r["id"]]
        if r.get("name_en") and short(r["name_en"]) in value: return [r["id"]]
    return []

def sync_once(cid: str, notify: bool) -> int:
    contest = load_contest(cid)
    ops_yaml = ops_contest_dir(cid) / "ops.yaml"
    sheet_id = (yaml.safe_load(ops_yaml.read_text(encoding="utf-8")) or {}).get("sheet_id") if ops_yaml.exists() else None
    if not sheet_id: sys.exit(f"回答シートの ID がありません（ops contests/{cid}/ops.yaml の sheet_id）。先に ops form create を。")
    header, rows = read_rows(sheet_id)
    cols, spec = _columns(cid, contest, header)
    need = [k for k in ("team", "tracks") if k not in cols]
    if need: sys.exit(f"シートの見出しに対応する列が見つかりません: {need}\n見出し: {header}")
    specq = {q["id"]: q for q in spec["questions"]}
    STATE.mkdir(parents=True, exist_ok=True); st_path = STATE / f"{cid}.json"
    seen = json.loads(st_path.read_text()) if st_path.exists() else {}
    # 公開 teams.yaml（既存を読み、チーム名で更新）
    teams_path = contest_dir(cid) / "teams.yaml"
    teams = (yaml.safe_load(teams_path.read_text(encoding="utf-8")) or {}).get("teams", []) if teams_path.exists() else []
    by_name = {t["team"]: t for t in teams}
    new = 0
    for r in rows:
        ts = r.get(header[0], ""); team = r.get(cols["team"], "").strip()
        if not team: continue
        key = f"{ts}|{team}"
        if key in seen: continue
        tracks = _ids_from_options(r.get(cols["tracks"], ""), specq["tracks"], contest["tracks"])
        rounds = _round_ids(r.get(cols.get("rounds", ""), ""), contest) if "rounds" in cols else [x["id"] for x in contest.get("rounds", [])]
        public = r.get(cols.get("public_name", ""), "").strip() if "public_name" in cols else ""
        reg = ts.split(" ")[0].replace("/", "-") if ts else datetime.date.today().isoformat()   # シートの 2026/10/09 → 2026-10-09
        entry = {"team": team, "tracks": tracks, "rounds": rounds, "registered": reg}
        if public: entry["public_name"] = public
        status = "更新" if team in by_name else "新規"
        by_name[team] = {**by_name.get(team, {}), **entry}
        seen[key] = datetime.datetime.now().isoformat(timespec="seconds"); new += 1
        if notify:
            rep = r.get(cols.get("rep_name", ""), ""); email = r.get(cols.get("rep_email", ""), ""); org = r.get(cols.get("rep_org", ""), "")
            slack_emails = r.get(cols.get("slack_emails", ""), "").replace("\n", ", ")
            text = (f"[{contest.get('name', cid)}] {status}登録: *{team}*\n"
                    f"代表: {rep}（{org}） {email}\nトラック: {', '.join(tracks) or '-'} / 回: {', '.join(rounds) or '-'}\n"
                    f"Slack 招待: {slack_emails or '-'}\n公開表記: {public or '（チーム名のみ）'}")
            sent = slack.dm_owners(contest.get("owners") or ([contest["owner"]] if contest.get("owner") else []), text)
            print(f"  通知: {team} → {', '.join(sent) or '（送り先なし）'}")
        else:
            print(f"  {status}: {team} tracks={tracks} rounds={rounds}")
    if new:
        teams_path.write_text("# ops sync が回答シートから生成する公開用のチーム一覧（連絡先は含めない）\n" +
                              yaml.safe_dump({"teams": sorted(by_name.values(), key=lambda t: t["registered"])}, allow_unicode=True, sort_keys=False), encoding="utf-8")
        st_path.write_text(json.dumps(seen, ensure_ascii=False, indent=1))
    print(f"{cid}: 回答 {len(rows)} 件、新規・更新 {new} 件、チーム {len(by_name)}")
    return new

def cmd_sync(a):
    while True:
        sync_once(a.id, notify=not a.no_notify)
        if a.once: return 0
        time.sleep(a.interval)
