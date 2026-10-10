"""大会定義シート（1 冊、大会ごとにタブ）: schema/fields.yaml → 行の並び、タブ → contest.yaml

タブの列: A 項目（日本語） / B 値 / C 用途 / D キー / E 説明。普段見るのは A・B。C〜E は折りたたみ。
英語の値は別タブ <id>_en（A 項目 / B 英語の値 / C 日本語の値（参考） / D キー / E 説明）。国内大会は作らない。
"""
import re
import yaml
from ..paths import CONTESTS

FIELDS = CONTESTS / "schema" / "fields.yaml"
CATALOG_TRACKS = CONTESTS / "catalog" / "tracks.yaml"
CATALOG_RULES = CONTESTS / "catalog" / "rules.yaml"
TIER = {"every": "【毎回】", "sometimes": "【たまに】", "fixed": "【規則】", "auto": "【自動】"}

def load_fields() -> dict:
    return yaml.safe_load(FIELDS.read_text(encoding="utf-8"))

def load_catalog() -> tuple[list[dict], dict]:
    tracks = yaml.safe_load(CATALOG_TRACKS.read_text(encoding="utf-8"))["tracks"]
    profiles = yaml.safe_load(CATALOG_RULES.read_text(encoding="utf-8"))["profiles"]
    return tracks, profiles

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

def build_rows(cid: str, prev: dict | None, full: bool = False):
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
        blank = (not full) and (q.get("tier") == "auto" or q["type"] == "date")
        en_pair = _get(prev, q["key"].replace("_en", "")) if q["type"] == "text_en" else None
        value = _get(prev, q["key"])
        if q["key"] == "rules_profile" and value is None:
            value = prev.get("rules_profile") or ("international" if prev.get("kind") == "international" or prev.get("language") == "en" else "domestic")
        field(q, q["key"], value, blank=blank, en_pair=en_pair)
    cols = {k: f[k]["columns"] for k in ("rounds", "milestones", "sponsors")}
    mk = f.get("milestone_keys", {})
    for i, r in enumerate(prev.get("rounds") or [{}], start=1):
        ja.append(_row(f"■ 回 {i}", "", "", "", "回が 1 つの大会でも 1 ブロック書く。増やすときはブロックをコピーして [n] を直す", header=True)); en.append(_row(f"■ 回 {i}", "", "", "", "", header=True))
        for c in cols["rounds"]:
            if c["key"] == "tracks":
                ids = ", ".join(t["id"] for t in load_catalog()[0])
                c = dict(c, desc=c["desc"] + f"。「トラック」タブにある id: {ids}")
            field(c, f"rounds[{i}].{c['key']}", _cell(r.get(c["key"]), c["type"]) if c["key"] != "tracks" else r.get("tracks"), indent=1, en_pair=r.get("name"))
        for j, m in enumerate(r.get("milestones") or [{}], start=1):
            ja.append(_row(f"　日程 {j}", "", "", "", "日程を増やすときは「日程 n」の 6 行をコピーして [n] を直す", header=True)); en.append(_row(f"　日程 {j}", "", "", "", "", header=True))
            for c in cols["milestones"]:
                if c["key"] == "round": continue
                field(c, f"rounds[{i}].milestones[{j}].{c['key']}", m.get(c["key"]), indent=2, blank=((not full) and c["type"] == "date"), en_pair=m.get("name"))
    for i, s in enumerate(prev.get("sponsors") or [{}], start=1):
        ja.append(_row(f"■ スポンサー {i}", "", "", "", "無ければ値を空のまま。増やすときはブロックをコピー", header=True)); en.append(_row(f"■ スポンサー {i}", "", "", "", "", header=True))
        for c in cols["sponsors"]: field(c, f"sponsors[{i}].{c['key']}", s.get(c["key"]), indent=1, en_pair=s.get("name"))
    ja.append(_row("■ 追加項目（自由）", "", "", "", f["extra"]["desc"] + "。A 列に項目名、B 列に値、D 列にキーを書く", header=True))
    for i in range(1, 4): ja.append(_row("", "", "", f"extra.", "", {"type": "text"}, indent=1))
    return ja, en

def catalog_tabs() -> list[dict]:
    """横断タブ: トラック / トラック_en / ルール。既にあれば上書きしない（keep_existing）"""
    f = load_fields(); tracks, profiles = load_catalog()
    tr = {"name": "トラック", "header": ["id", "名前", "人数", "方式", "チーム当たり試合数（下限）", "チーム当たり試合数（上限）", "説明"],
          "rows": [["（変えない識別子）", "日本語の表示名", "村の人数（役職は roles/<人数>.yaml）", "turn=ターン式 / anytime=いつでも発話", "既定値。大会側で上書き可", "", "行を足せばトラックが増える"]]
                  + [[t["id"], t["name"], t["size"], t["mode"], (t.get("games_per_team") or ["", ""])[0], (t.get("games_per_team") or ["", ""])[1], ""] for t in tracks],
          "widths": [110, 240, 90, 120, 170, 170, 300], "validations": [{"col": 4, "row": None, "type": "list", "values": ["turn", "anytime"]}],
          "bg": [{"row": 2, "cols": 7, "color": "#f1f3f4"}], "keep_existing": True}
    tre = {"name": "トラック_en", "header": ["id", "名前（英語）", "日本語の名前（参考）"],
           "rows": [["（トラックタブと同じ id）", "英語ページで使う表示名", ""]] + [[t["id"], t.get("name_en", ""), t["name"]] for t in tracks],
           "widths": [110, 300, 240], "validations": [], "bg": [{"row": 2, "cols": 3, "color": "#f1f3f4"}], "keep_existing": True}
    names = list(profiles.keys())
    rows = [[k["label"]] + [("" if profiles[n].get(k["key"]) is None else profiles[n][k["key"]]) for n in names] + [k["key"], k["desc"]] for k in f["rules"]["keys"]]
    ru = {"name": "ルール", "header": ["項目"] + names + ["キー", "説明"], "rows": rows, "widths": [260] + [140] * len(names) + [220, 320], "validations": [],
          "bg": [], "collapse": None, "keep_existing": True,
          "note": "列を足せばルールセットが増える（列名が大会タブの「ルールセット」の選択肢になる）"}
    return [tr, tre, ru]

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
    tabs = catalog_tabs() + [tab(cid, ja, False)]
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

def catalog_from_tabs(tracks_rows, tracks_en_rows, rules_rows) -> tuple[list[dict], dict]:
    """横断タブ → (tracks, profiles)。タブが無ければファイルの値"""
    tracks, profiles = load_catalog()
    if tracks_rows and len(tracks_rows) > 2:
        en_map = {r[0]: (r[1] if len(r) > 1 else "") for r in (tracks_en_rows or [])[2:] if r and r[0]}
        tracks = []
        for r in tracks_rows[2:]:
            r = (r + [""] * 7)[:7]
            if not str(r[0]).strip(): continue
            t = {"id": r[0].strip(), "name": r[1], "name_en": en_map.get(r[0].strip(), ""), "size": int(float(r[2])), "mode": r[3]}
            if str(r[4]).strip(): t["games_per_team"] = [int(float(r[4])), int(float(r[5] or r[4]))]
            tracks.append(t)
    if rules_rows and len(rules_rows) > 1:
        header = rules_rows[0]; names = header[1:header.index("キー")] if "キー" in header else header[1:-2]
        profiles = {n: {} for n in names}
        for r in rules_rows[1:]:
            r = (r + [""] * len(header))[:len(header)]
            key = r[header.index("キー")] if "キー" in header else r[-2]
            if not key: continue
            for j, n in enumerate(names, start=1):
                profiles[n][key] = int(float(r[j])) if str(r[j]).strip() else None
    return tracks, profiles

def save_catalog(tracks, profiles):
    CATALOG_TRACKS.write_text(CATALOG_TRACKS.read_text(encoding="utf-8").split("tracks:")[0] + yaml.safe_dump({"tracks": tracks}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    CATALOG_RULES.write_text(CATALOG_RULES.read_text(encoding="utf-8").split("profiles:")[0] + yaml.safe_dump({"profiles": profiles}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")

def tabs_to_contest(cid: str, ja_rows: list[list], en_rows: list[list] | None, catalog=None) -> dict:
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
    # 横断タブ（トラック・ルール）を大会側に展開する。消費側（サイト・サーバ）は tracks / rules を直接読む
    tracks, profiles = catalog or load_catalog()
    used = []
    for r in out.get("rounds", []):
        for tid in r.get("tracks", []) or []:
            if tid not in used: used.append(tid)
    by_id = {t["id"]: t for t in tracks}
    out["tracks"] = [dict(by_id[t]) for t in [x["id"] for x in tracks] if t in used]
    unknown = [t for t in used if t not in by_id]
    if unknown: print("「トラック」タブに無い id:", ", ".join(unknown))
    prof = out.get("rules_profile")
    if prof in profiles: out["rules"] = {k: v for k, v in profiles[prof].items()}
    for r in out.get("rounds", []):
        r["milestones"] = [m for m in r.get("milestones", []) if m.get("date") or m.get("name")]
        for m in r["milestones"]:
            if m.get("open") is False: m.pop("open")
    out["tracks"] = [t for t in out.get("tracks", []) if t.get("id")]
    out["rounds"] = [r for r in out.get("rounds", []) if r.get("id")]
    if "sponsors" in out: out["sponsors"] = [s for s in out["sponsors"] if s.get("name")] or None
    if out.get("sponsors") is None: out.pop("sponsors", None)
    order = ["id", "kind", "name", "name_en", "language", "owners", "form_url", "paper_submission", "venue", "sponsors", "rules_profile", "rules", "tracks", "rounds", "texts", "extra"]
    return {k: out[k] for k in order if k in out} | {k: v for k, v in out.items() if k not in order}
