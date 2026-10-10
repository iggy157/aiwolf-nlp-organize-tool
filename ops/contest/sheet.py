"""大会定義シート: schema/fields.yaml → シートの雛形（spec）、シート → contest.yaml"""
import datetime, re
import yaml
from ..paths import CONTESTS

FIELDS = CONTESTS / "schema" / "fields.yaml"
TIER = {"every": "【毎回】", "sometimes": "【たまに】", "fixed": "【規則】", "auto": "【自動】"}
COLOR = {"every": "#fff8c5", "sometimes": "#ffffff", "fixed": "#f1f3f4", "auto": "#f1f3f4"}
TAB = {"basic": "基本", "tracks": "トラック", "rounds": "回", "milestones": "日程", "sponsors": "スポンサー", "extra": "追加項目"}

def load_fields() -> dict:
    return yaml.safe_load(FIELDS.read_text(encoding="utf-8"))

def _get(d: dict, dotted: str):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def _cell(v, t):
    if v is None: return ""
    if t == "bool": return bool(v)
    if t == "list": return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    if t == "date": return str(v)[:10]
    return v

def build_spec(cid: str, prev: dict | None, share_with: list[str], test: bool = False) -> dict:
    f = load_fields(); prev = prev or {}
    tabs = []
    # 基本: 値 / キー / 説明
    rows, vals, bgs = [], [], []
    for i, q in enumerate(f["basic"], start=2):
        # 前回の値を入れておく。ただし日付と「自動」の項目は空にして、直し忘れを防ぐ
        prefill = "" if (q["tier"] == "auto" or q["type"] == "date") else _cell(_get(prev, q["key"]), q["type"])
        rows.append([prefill, q["key"], TIER[q["tier"]] + ("（必須）" if q.get("required") else "") + " " + q["desc"]])
        if q["type"] == "enum": vals.append({"row": i, "col": 1, "type": "list", "values": q["options"]})
        elif q["type"] == "date": vals.append({"row": i, "col": 1, "type": "date"})
        elif q["type"] == "bool": vals.append({"row": i, "col": 1, "type": "checkbox"})
        bgs.append({"row": i, "col": 1, "color": COLOR[q["tier"]]})
    tabs.append({"name": TAB["basic"], "header": ["値", "キー", "説明"], "rows": rows, "widths": [420, 220, 620], "validations": vals, "bg": bgs, "protect": "B:C"})
    def table(name, cols, data_rows):
        header = [c["key"] for c in cols]; desc = [("（必須）" if c.get("required") else "") + c["desc"] for c in cols]
        vals = []
        for j, c in enumerate(cols, start=1):
            if c["type"] == "enum": vals.append({"col": j, "type": "list", "values": c["options"]})
            elif c["type"] == "date": vals.append({"col": j, "type": "date"})
            elif c["type"] == "bool": vals.append({"col": j, "type": "checkbox"})
        # 2 行目に説明（灰色）、3 行目以降がデータ
        rows = [desc] + data_rows
        bg = [{"row": 2, "col": j, "color": "#f1f3f4"} for j in range(1, len(cols) + 1)]
        return {"name": name, "header": header, "rows": rows, "widths": [160] * len(cols), "validations": [dict(v, start=3) for v in vals], "bg": bg}
    f_tr = f["tracks"]["columns"]
    tabs.append(table(TAB["tracks"], f_tr, [[t.get("id"), t.get("name"), t.get("name_en", ""), t.get("size"), t.get("mode"), (t.get("games_per_team") or ["", ""])[0], (t.get("games_per_team") or ["", ""])[1]] for t in prev.get("tracks", [])]))
    f_r = f["rounds"]["columns"]
    tabs.append(table(TAB["rounds"], f_r, [[r.get("id"), r.get("name", ""), r.get("name_en", ""), r.get("public_name", ""), ", ".join(r.get("tracks", []))] for r in prev.get("rounds", [])]))
    f_m = f["milestones"]["columns"]
    ms = []
    for r in prev.get("rounds", []):
        for m in r.get("milestones", []):
            ms.append([r.get("id"), m.get("key", "other"), "", "", bool(m.get("open")), m.get("name", ""), m.get("name_en", "")])   # 日付は空で出す（前回の日付が残ると危ない）
    tabs.append(table(TAB["milestones"], f_m, ms))
    f_s = f["sponsors"]["columns"]
    tabs.append(table(TAB["sponsors"], f_s, [[s.get("name"), s.get("name_en", ""), s.get("url", "")] for s in prev.get("sponsors", []) or []]))
    tabs.append({"name": TAB["extra"], "header": ["値", "キー", "メモ"], "rows": [["", "", f["extra"]["desc"]]], "widths": [420, 220, 620], "validations": [], "bg": []})
    # 表の検証は 3 行目から
    for t in tabs:
        for v in t.get("validations", []):
            if "start" in v: v.pop("start"); v["row"] = None
    return {"title": ("[test] " if test else "") + f"大会定義: {cid}", "share_with": share_with, "tabs": tabs}

def _norm_date(v):
    v = str(v).strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", v)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else (v or None)

def _cast(v, t):
    if v is None or str(v).strip() == "": return None
    s = str(v).strip()
    if t == "int": return int(float(s))
    if t == "bool": return s.upper() == "TRUE"
    if t == "date": return _norm_date(s)
    if t == "list": return [x.strip() for x in re.split(r"[,、]", s) if x.strip()]
    return s

def sheet_to_contest(cid: str, tabs: dict[str, list[list]]) -> dict:
    """tabs: {シート名: 2 次元配列（1 行目が見出し）} → contest.yaml の dict"""
    f = load_fields(); out = {"id": cid}
    basic = {r[1]: (r[0] if len(r) > 0 else "") for r in tabs.get(TAB["basic"], [])[1:] if len(r) > 1 and r[1]}
    types = {q["key"]: q["type"] for q in f["basic"]}
    for q in f["basic"]:
        v = _cast(basic.get(q["key"]), q["type"])
        if v is None and not q.get("required"): continue
        d = out
        parts = q["key"].split(".")
        for k in parts[:-1]: d = d.setdefault(k, {})
        d[parts[-1]] = v
    def rows_of(tab, cols):
        data = tabs.get(TAB[tab], [])
        if len(data) < 3: return []
        header = data[0]; out_rows = []
        for r in data[2:]:
            if not any(str(c).strip() for c in r): continue
            row = {}
            for j, c in enumerate(cols):
                v = _cast(r[j] if j < len(r) else None, c["type"])
                if v is not None: row[c["key"]] = v
            out_rows.append(row)
        return out_rows
    tracks = []
    for r in rows_of("tracks", f["tracks"]["columns"]):
        t = {k: r[k] for k in ("id", "name", "name_en", "size", "mode") if k in r}
        if r.get("games_min"): t["games_per_team"] = [r["games_min"], r.get("games_max") or r["games_min"]]
        tracks.append(t)
    out["tracks"] = tracks
    ms = rows_of("milestones", f["milestones"]["columns"])
    rounds = []
    for r in rows_of("rounds", f["rounds"]["columns"]):
        rd = {k: r[k] for k in ("id", "public_name", "name", "name_en", "tracks") if k in r}
        rd["milestones"] = [{k: m[k] for k in ("key", "date", "end", "open", "name", "name_en") if k in m and m[k] not in (None, False)} for m in ms if m.get("round") == r.get("id")]
        rounds.append(rd)
    out["rounds"] = rounds
    sp = rows_of("sponsors", f["sponsors"]["columns"])
    if sp: out["sponsors"] = sp
    ex = {r[1]: r[0] for r in tabs.get(TAB["extra"], [])[1:] if len(r) > 1 and r[1] and str(r[0]).strip()}
    if ex: out["extra"] = ex
    order = ["id", "kind", "name", "name_en", "language", "owners", "form_url", "paper_submission", "venue", "sponsors", "rules", "tracks", "rounds", "texts", "extra"]
    return {k: out[k] for k in order if k in out} | {k: v for k, v in out.items() if k not in order}
