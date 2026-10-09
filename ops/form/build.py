"""form.yaml + questions_common.yaml + contest.yaml → フォームの仕様（dict）と Apps Script の Code.js"""
import json
import yaml
from pathlib import Path
from ..paths import OPS, ops_contest_dir

COMMON = OPS / "ops/form/questions_common.yaml"

def _lab(q: dict, key: str, en: bool) -> str | None:
    """ラベルは「英文 (日本語)」、注意書き（help）は「英文 / 空行 / 日本語」の併記にする。国内大会は日本語だけ。"""
    v = q.get(key)
    if not v: return None
    if isinstance(v, str): return v
    ja, e = v.get("ja"), v.get("en")
    if not en: return ja or e
    if e and ja: return f"{e}\n\n{ja}" if key == "help" else f"{e} ({ja})"
    return e or ja

def _choice(ja: str, en_: str | None, en: bool) -> str:
    if en and en_: return f"{en_} ({ja})" if ja else en_
    return ja or en_

def build_spec(cid: str, contest: dict, form_def: dict, share_with: list[str] | None = None) -> dict:
    en = (contest.get("language") == "en")
    common = {q["id"]: q for q in yaml.safe_load(COMMON.read_text(encoding="utf-8"))["questions"]}
    title = form_def["title"]
    title = (title.get("en") if en else title.get("ja")) or title.get("ja") or title.get("en")
    questions = []
    for q in form_def["questions"]:
        q = dict(common[q]) if isinstance(q, str) else dict(q)
        t = q["type"]
        spec = {"id": q["id"], "type": t, "label": _lab(q, "label", en), "help": _lab(q, "help", en), "required": bool(q.get("required"))}
        if t == "tracks":
            spec["type"] = "checkbox"
            spec["options"] = [_choice(tr["name"], tr.get("name_en"), en) for tr in contest["tracks"]]
        elif t == "rounds":
            rounds = contest.get("rounds", [])
            if len(rounds) < 2: continue   # 回が 1 つなら聞かない
            names = [(r.get("name") or r["id"], r.get("name_en")) for r in rounds]
            short = lambda s: s.split("（")[0].split(" (")[0]
            all_ja = "＋".join(short(n[0]) for n in names); all_en = " + ".join(short(n[1] or n[0]) for n in names)
            opts = [_choice(all_ja, all_en, en)]
            for ja, e in names[1:]:
                opts.append(_choice(f"{short(ja)}のみ", f"{short(e or ja)} only", en))
            spec["type"] = "radio"; spec["options"] = opts
        elif q.get("options"):
            spec["options"] = [_choice(o.get("ja") if isinstance(o, dict) else o, o.get("en") if isinstance(o, dict) else None, en) for o in q["options"]]
        questions.append({k: v for k, v in spec.items() if v not in (None, False, [])})
    out = {"contest": cid, "title": title, "questions": questions}
    if share_with: out["share_with"] = share_with
    return out

def render_code_js(specs: dict) -> str:
    """specs: {大会 id: spec}。大会ごとに createForm_<id>() を用意する（エディタからも clasp run からも呼べる）"""
    out = ["// ops form create が生成したファイル。手で直さない（直すなら form.yaml / questions_common.yaml）。",
           "const SPECS = " + json.dumps(specs, ensure_ascii=False, indent=2) + ";"]
    for cid in specs:
        out.append(f"function createForm_{cid}() {{ return createFormFor('{cid}'); }}")
    return "\n".join(out) + "\n"

def describe(spec: dict) -> str:
    lines = [f"タイトル: {spec['title']}"]
    for i, q in enumerate(spec["questions"], 1):
        req = "必須" if q.get("required") else "任意"
        lines.append(f"{i:2}. [{q['type']}, {req}] {q['label']}")
        if q.get("help"): lines.append("      " + q["help"].splitlines()[0] + (" …" if "\n" in q["help"] else ""))
        for o in q.get("options", []): lines.append(f"      ○ {o}")
    return "\n".join(lines)
