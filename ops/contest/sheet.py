"""大会定義シート（1 冊、大会ごとにタブ）: schema/fields.yaml → 行の並び、タブ → contest.yaml

タブの列: A 項目（日本語） / B 値 / C 用途 / D キー / E 説明。普段見るのは A・B。C〜E は折りたたみ。
英語の値は別タブ <id>_en（A 項目 / B 英語の値 / C 日本語の値（参考） / D キー / E 説明）。国内大会は作らない。
"""
import re
import yaml
from ..paths import CONTESTS

FIELDS = CONTESTS / "schema" / "fields.yaml"
TIER = {"every": "【毎回】", "sometimes": "【たまに】", "fixed": "【規則】", "auto": "【自動】"}

def load_fields() -> dict:
    return yaml.safe_load(FIELDS.read_text(encoding="utf-8"))

def _get(d, dotted):
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

def _row(label, value, use, key, desc, q=None, header=False, indent=0):
    return {"label": ("　" * indent) + label, "value": value, "use": use, "key": key, "desc": desc, "type": (q or {}).get("type"), "options": (q or {}).get("options"), "header": header}

def build_rows(cid: str, prev: dict | None):
    """返り値: (日本語タブの行, 英語タブの行)。英語タブは *_en の項目だけ"""
    f = load_fields(); prev = prev or {}; ja, en = [], []
    def field(q, key, value, label=None, indent=0, en_pair=None, blank=False):
        v = "" if blank else _cell(value, q["type"])
        desc = TIER.get(q.get("tier", "every"), "") + ("（必須）" if q.get("required") else "") + " " + q["desc"]
        if q["type"] == "text_en":
            en.append(_row(label or q["label"], v, (en_pair or ""), key, desc, q, indent=indent))
        else:
            ja.append(_row(label or q["label"], v, q.get("use", ""), key, desc, q, indent=indent))
    ja.append(_row("■ 基本", "", "", "", "", header=True)); en.append(_row("■ 基本", "", "", "", "", header=True))
    for q in f["basic"]:
        if q["key"].startswith("rules."): continue
        blank = q.get("tier") == "auto" or q["type"] == "date"
        en_pair = _get(prev, q["key"].replace("_en", "")) if q["type"] == "text_en" else None
        field(q, q["key"], _get(prev, q["key"]), blank=blank, en_pair=en_pair)
    ja.append(_row("■ ルール", "", "", "", "", header=True))
    for q in f["basic"]:
        if q["key"].startswith("rules."): field(q, q["key"], _get(prev, q["key"]))
    cols = {k: f[k]["columns"] for k in ("tracks", "rounds", "milestones", "sponsors")}
    for i, t in enumerate(prev.get("tracks") or [{}], start=1):
        ja.append(_row(f"■ トラック {i}", "", "", "", "増やすときはこのブロック（識別子〜上限）をコピーして貼り、D 列の [n] を直す", header=True)); en.append(_row(f"■ トラック {i}", "", "", "", "", header=True))
        g = t.get("games_per_team") or [None, None]
        vals = {"id": t.get("id"), "name": t.get("name"), "name_en": t.get("name_en"), "size": t.get("size"), "mode": t.get("mode"), "games_min": g[0], "games_max": g[1]}
        for c in cols["tracks"]: field(c, f"tracks[{i}].{c['key']}", vals.get(c["key"]), indent=1, en_pair=t.get("name"))
    mk = f.get("milestone_keys", {})
    for i, r in enumerate(prev.get("rounds") or [{}], start=1):
        ja.append(_row(f"■ 回 {i}", "", "", "", "回が 1 つの大会でも 1 ブロック書く。増やすときはブロックをコピーして [n] を直す", header=True)); en.append(_row(f"■ 回 {i}", "", "", "", "", header=True))
        for c in cols["rounds"]:
            field(c, f"rounds[{i}].{c['key']}", _cell(r.get(c["key"]), c["type"]) if c["key"] != "tracks" else r.get("tracks"), indent=1, en_pair=r.get("name"))
        for j, m in enumerate(r.get("milestones") or [{}], start=1):
            ja.append(_row(f"　日程 {j}", "", "", "", "日程を増やすときは「日程 n」の 6 行をコピーして [n] を直す", header=True)); en.append(_row(f"　日程 {j}", "", "", "", "", header=True))
            for c in cols["milestones"]:
                if c["key"] == "round": continue
                lab = c["label"] + ("（" + "／".join(f"{k}={v}" for k, v in mk.items()) + "）" if c["key"] == "key" else "")
                field(c, f"rounds[{i}].milestones[{j}].{c['key']}", m.get(c["key"]), label=lab if c["key"] != "key" else c["label"], indent=2,
                      blank=(c["type"] == "date"), en_pair=m.get("name"))
    for i, s in enumerate(prev.get("sponsors") or [{}], start=1):
        ja.append(_row(f"■ スポンサー {i}", "", "", "", "無ければ値を空のまま。増やすときはブロックをコピー", header=True)); en.append(_row(f"■ スポンサー {i}", "", "", "", "", header=True))
        for c in cols["sponsors"]: field(c, f"sponsors[{i}].{c['key']}", s.get(c["key"]), indent=1, en_pair=s.get("name"))
    ja.append(_row("■ 追加項目（自由）", "", "", "", f["extra"]["desc"] + "。A 列に項目名、B 列に値、D 列にキーを書く", header=True))
    for i in range(1, 4): ja.append(_row("", "", "", f"extra.", "", {"type": "text"}, indent=1))
    return ja, en

def rows_to_spec(cid: str, ja, en, make_en: bool, test: bool):
    def tab(name, rows, en_mode):
        header = ["項目", "値（英語）" if en_mode else "値", "日本語の値（参考）" if en_mode else "用途", "キー", "説明"]
        out_rows, vals, bg = [], [], []
        for i, r in enumerate(rows, start=2):
            out_rows.append([r["label"], r["value"], r["use"], r["key"], r["desc"]])
            if r["header"]:
                bg.append({"row": i, "cols": 5, "color": "#dbe4f0", "bold": True}); continue
            if r["type"] == "enum" and r["options"]: vals.append({"row": i, "col": 2, "type": "list", "values": r["options"]})
            elif r["type"] == "date": vals.append({"row": i, "col": 2, "type": "date"})
            elif r["type"] == "bool": vals.append({"row": i, "col": 2, "type": "checkbox"})
            if "【毎回】" in r["desc"]: bg.append({"row": i, "cols": 2, "color": "#fff8c5"})
        return {"name": name, "header": header, "rows": out_rows, "widths": [260, 420, 150, 320, 520], "validations": vals, "bg": bg, "collapse": "C:E", "protect": "A:A,C:E"}
    tabs = [tab(cid, ja, False)]
    if make_en: tabs.append(tab(cid + "_en", en, True))
    return {"title": ("[test] " if test else "") + "大会定義", "tabs": tabs}

# ---------- シート → contest.yaml ----------
def _norm_date(v):
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(v).strip())
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else (str(v).strip() or None)

def _cast(v, t):
    if v is None or str(v).strip() == "": return None
    s = str(v).strip()
    if t == "int": return int(float(s))
    if t == "bool": return s.upper() == "TRUE"
    if t == "date": return _norm_date(s)
    if t == "list": return [x.strip() for x in re.split(r"[,、]", s) if x.strip()]
    return s

def _types(f):
    t = {q["key"]: q["type"] for q in f["basic"]}
    for sec in ("tracks", "rounds", "milestones", "sponsors"):
        for c in f[sec]["columns"]: t[f"{sec}.{c['key']}"] = c["type"]
    return t

def _set(d, path, value):
    """path 例: rounds[1].milestones[2].date → d['rounds'][0]['milestones'][1]['date']"""
    parts = re.findall(r"([A-Za-z_]+)(?:\[(\d+)\])?", path)
    cur = d
    for i, (name, idx) in enumerate(parts):
        last = i == len(parts) - 1
        if idx:
            lst = cur.setdefault(name, []); k = int(idx) - 1
            while len(lst) <= k: lst.append({})
            if last: lst[k] = value
            else: cur = lst[k]
        else:
            if last: cur[name] = value
            else: cur = cur.setdefault(name, {})

def tabs_to_contest(cid: str, ja_rows: list[list], en_rows: list[list] | None) -> dict:
    f = load_fields(); types = _types(f); out = {"id": cid}
    def eat(rows):
        for r in rows[1:]:
            r = (r + [""] * 5)[:5]; label, value, _, key, _ = r
            if not key or key.endswith(".") and not label: continue
            if key.startswith("extra."):
                if label.strip() and str(value).strip(): out.setdefault("extra", {})[key[6:] or label.strip()] = value
                continue
            base = re.sub(r"\[\d+\]", "", key)              # tracks[1].name → tracks.name
            t = types.get(base) or types.get(base.split(".")[-1]) or "text"
            v = _cast(value, t)
            if v is None: continue
            _set(out, key, v)
    eat(ja_rows)
    if en_rows: eat(en_rows)
    # tracks: games_min/max → games_per_team
    for t in out.get("tracks", []):
        if "games_min" in t: t["games_per_team"] = [t.pop("games_min"), t.pop("games_max", None) or t["games_per_team"][0] if False else t.pop("games_max", t.get("games_min"))]
    for r in out.get("rounds", []):
        r["milestones"] = [m for m in r.get("milestones", []) if m.get("date") or m.get("name")]
        for m in r["milestones"]:
            if m.get("open") is False: m.pop("open")
    out["tracks"] = [t for t in out.get("tracks", []) if t.get("id")]
    out["rounds"] = [r for r in out.get("rounds", []) if r.get("id")]
    if "sponsors" in out: out["sponsors"] = [s for s in out["sponsors"] if s.get("name")] or None
    if out.get("sponsors") is None: out.pop("sponsors", None)
    order = ["id", "kind", "name", "name_en", "language", "owners", "form_url", "paper_submission", "venue", "sponsors", "rules", "tracks", "rounds", "texts", "extra"]
    return {k: out[k] for k in order if k in out} | {k: v for k, v in out.items() if k not in order}
