"""大会定義シート（1 冊、大会ごとにタブ）: schema/fields.yaml + catalog/ → 行の並び、タブ → contest.yaml

大会タブの列: A 項目 / B 値 / C 前回の値（参考） / D 用途 / E キー / F 説明。普段見るのは A〜C。D〜F は折りたたみ。
  - 必須の項目は A 列の頭に「＊」。必須で空のセルは赤くなる（埋めると消える）。
  - 日程は 1 件につき「日付」「表示文」の 2 行。日付欄は 2026/07/04、期間は 2026/10/17〜10/21、「〜」付きは 2026/07/06〜 と書く。
  - 開催トラックはチェックボックス。回ごとの「実施トラック」は空なら開催トラック全部。
英語の値は別タブ <id>_en。国内大会は作らない。
横断タブ「トラック」「トラック_en」「ルール」は最初の 1 回だけ作る。
"""
import re
import yaml
from ..paths import CONTESTS

FIELDS = CONTESTS / "schema" / "fields.yaml"
CATALOG_TRACKS = CONTESTS / "catalog" / "tracks.yaml"
CATALOG_RULES = CONTESTS / "catalog" / "rules.yaml"
TIER = {"every": "毎回変える", "sometimes": "たまに変える", "fixed": "規則で決まる", "auto": "道具が書く"}

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

def _fmt_date(m: dict) -> str:
    if not m or not m.get("date"): return ""
    d = str(m["date"])[:10].replace("-", "/")
    if m.get("end"):
        e = str(m["end"])[:10].replace("-", "/")
        return f"{d}〜{e[5:] if e[:4] == d[:4] else e}"
    return d + ("〜" if m.get("open") else "")

def _cell(v, t):
    if v is None: return ""
    if t == "bool": return bool(v)
    if t == "list": return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    if t == "date": return str(v)[:10].replace("-", "/")
    return v

def R(label, value, prev, use, key, desc, typ=None, options=None, header=False, required=False, indent=0, note=""):
    return {"label": ("　" * indent) + ("＊" if required else "") + label, "value": value, "prev": prev, "use": use, "key": key,
            "desc": desc, "type": typ, "options": options, "header": header, "required": required, "note": note}

def build_rows(cid: str, prev: dict | None, full: bool = False):
    """返り値: (日本語タブの行, 英語タブの行)"""
    f = load_fields(); prev = prev or {}; tracks, profiles = load_catalog(); ja, en = [], []
    def F(q, key, value, label=None, indent=0, blank=False, en_ref=None):
        v = "" if (blank and not full) else _cell(value, q["type"])
        pv = _cell(value, q["type"]); desc = f"[{TIER.get(q.get('tier', 'every'), '')}] {q['desc']}"
        opts = q.get("options")
        if q["key"] == "rules_profile": opts = list(profiles.keys())
        if q["type"] == "text_en":
            en.append(R(label or q["label"], v, en_ref or "", "", key, desc, "text", None, required=bool(q.get("required")), indent=indent))
        else:
            ja.append(R(label or q["label"], v, pv, q.get("use", ""), key, desc, q["type"], opts, required=bool(q.get("required")), indent=indent))
    H = lambda rows, text, note="": rows.append(R(text, "", "", "", "", note, header=True))
    H(ja, "■ 基本", "＊は必須。赤いセルは必須なのに空。C 列は前回の値（参考）"); H(en, "■ 基本（英語）", "英語ページで使う値。空なら日本語の値で代用される")
    for q in f["basic"]:
        blank = q.get("tier") == "auto" or q["type"] == "date"
        value = _get(prev, q["key"])
        if q["key"] == "rules_profile" and value is None:
            value = prev.get("rules_profile") or ("international" if prev.get("language") == "en" else "domestic")
        F(q, q["key"], value, blank=blank, en_ref=_get(prev, q["key"].replace("_en", "")) if q["type"] == "text_en" else None)
    # 開催トラック（チェックボックス）
    H(ja, "■ 開催トラック", "この大会で実施するトラックにチェック。トラック自体の追加は「トラック」タブ"); H(en, "■ 開催トラック", "")
    used = {t["id"] for t in prev.get("tracks", [])}
    for t in tracks:
        ja.append(R(f"{t['name']}（{t['id']}）", t["id"] in used, t["id"] in used, "サイト,フォーム,サーバ", f"tracks_enabled.{t['id']}", f"[毎回変える] 人数 {t['size']}、方式 {t['mode']}。試合数の既定は「トラック」タブ", "bool", indent=1))
    # 回と日程
    rcols = {c["key"]: c for c in f["rounds"]["columns"]}; mk = f.get("milestone_keys", {})
    for i, r in enumerate(prev.get("rounds") or [{}], start=1):
        H(ja, f"■ 回 {i}", "回が 1 つの大会でも 1 ブロック。増やすときは「回 n」から次の見出しの前までをコピーして E 列の [n] を直す"); H(en, f"■ 回 {i}（英語）", "")
        for k in ("id", "name", "name_en", "public_name", "tracks"):
            c = dict(rcols[k])
            if k == "tracks": c["desc"] = "空なら開催トラック全部。この回だけ絞るときに id をカンマ区切りで"; c["required"] = False
            F(c, f"rounds[{i}].{k}", r.get(k), indent=1, en_ref=r.get("name"))
        H(ja, f"■ 回 {i} の日程", "1 件 2 行（日付・表示文）。日付は 2026/07/04、期間は 2026/10/17〜10/21、本戦開始のような「〜」付きは 2026/07/06〜。増やすときは 2 行をコピーして E 列の [種類] を直す（種類: " + "、".join(mk) + "）"); H(en, f"■ 回 {i} の日程（英語の表示文）", "")
        for j, m in enumerate(r.get("milestones") or [], start=1):
            kind = m.get("key", f"other{j}"); kl = mk.get(kind, kind)
            ja.append(R(f"{kl} 日付", "" if not full else _fmt_date(m), _fmt_date(m), "サイト", f"rounds[{i}].milestones[{kind}].date", "[毎回変える] 例: 2026/07/04、2026/07/06〜、2026/10/17〜10/21", "text", required=True, indent=1))
            ja.append(R(f"{kl} 表示文", m.get("name", ""), m.get("name", ""), "サイト", f"rounds[{i}].milestones[{kind}].name", "[たまに変える] サイトの日程に出る文", "text", required=True, indent=1))
            en.append(R(f"{kl} 表示文（英語）", m.get("name_en", ""), m.get("name", ""), "", f"rounds[{i}].milestones[{kind}].name_en", "英語ページの日程に出る文", "text", indent=1))
    # スポンサー
    H(ja, "■ スポンサー", "無ければ空のまま。増やすときは 2 行をコピーして E 列の [n] を直す"); H(en, "■ スポンサー（英語）", "")
    for i, s in enumerate(prev.get("sponsors") or [{}], start=1):
        ja.append(R(f"スポンサー {i} 名前", s.get("name", ""), s.get("name", ""), "サイト", f"sponsors[{i}].name", "[毎回変える]", "text", indent=1))
        ja.append(R(f"スポンサー {i} URL", s.get("url", ""), s.get("url", ""), "サイト", f"sponsors[{i}].url", "[毎回変える]", "url", indent=1))
        en.append(R(f"スポンサー {i} 名前（英語）", s.get("name_en", ""), s.get("name", ""), "", f"sponsors[{i}].name_en", "", "text", indent=1))
    H(ja, "■ 追加項目（自由）", f["extra"]["desc"] + "。A 列に項目名、B 列に値、E 列にキー（extra.名前）")
    for i in range(1, 4): ja.append(R("", "", "", "", "extra.", "", "text", indent=1))
    return ja, en

def catalog_tabs() -> list[dict]:
    f = load_fields(); tracks, profiles = load_catalog()
    tr = {"name": "トラック", "header": ["id", "名前", "人数", "方式", "チーム当たり試合数（下限）", "チーム当たり試合数（上限）", "説明"],
          "rows": [["（変えない識別子）", "日本語の表示名", "村の人数（役職は roles/<人数>.yaml）", "turn=ターン式 / anytime=いつでも発話", "既定値", "", "行を足せばトラックが増える。大会で使うかどうかは各大会タブの「開催トラック」"]]
                  + [[t["id"], t["name"], t["size"], t["mode"], (t.get("games_per_team") or ["", ""])[0], (t.get("games_per_team") or ["", ""])[1], ""] for t in tracks],
          "widths": [110, 240, 90, 120, 170, 170, 360], "validations": [{"col": 4, "type": "list", "values": ["turn", "anytime"]}], "bg": [{"row": 2, "cols": 7, "color": "#f1f3f4"}], "keep_existing": True}
    tre = {"name": "トラック_en", "header": ["id", "名前（英語）", "日本語の名前（参考）"],
           "rows": [["（トラックタブと同じ id）", "英語ページで使う表示名", ""]] + [[t["id"], t.get("name_en", ""), t["name"]] for t in tracks],
           "widths": [110, 300, 240], "validations": [], "bg": [{"row": 2, "cols": 3, "color": "#f1f3f4"}], "keep_existing": True}
    names = list(profiles.keys())
    rows = [[k["label"]] + [("" if profiles[n].get(k["key"]) is None else profiles[n][k["key"]]) for n in names] + [k["key"], k["desc"]] for k in f["rules"]["keys"]]
    ru = {"name": "ルール", "header": ["項目"] + names + ["キー", "説明"], "rows": rows, "widths": [260] + [140] * len(names) + [220, 320], "validations": [], "bg": [], "keep_existing": True}
    return [tr, tre, ru]

def rows_to_spec(cid: str, ja, en, make_en: bool, test: bool):
    def tab(name, rows, en_mode):
        header = ["項目", "値（英語）" if en_mode else "値", "日本語の値（参考）" if en_mode else "前回の値（参考）", "用途", "キー", "説明"]
        out, vals, bg, req = [], [], [], []
        for i, r in enumerate(rows, start=2):
            out.append([r["label"], r["value"], r["prev"], r["use"], r["key"], r["desc"]])
            if r["header"]: bg.append({"row": i, "cols": 6, "color": "#dbe4f0", "bold": True}); continue
            if r["type"] == "enum" and r["options"]: vals.append({"row": i, "col": 2, "type": "list", "values": r["options"]})
            elif r["type"] == "bool": vals.append({"row": i, "col": 2, "type": "checkbox"})
            if r["required"]: req.append(i)
        return {"name": name, "header": header, "rows": out, "widths": [300, 400, 300, 130, 300, 480], "validations": vals, "bg": bg,
                "required_rows": req, "collapse": "D:F", "protect": "A:A,C:F"}
    tabs = catalog_tabs() + [tab(cid, ja, False)]
    if make_en: tabs.append(tab(cid + "_en", en, True))
    return {"title": ("[test] " if test else "") + "大会定義", "tabs": tabs}

# ---------- シート → contest.yaml ----------
def _parse_date_cell(s: str) -> dict | None:
    """2026/07/04 → date / 2026/07/06〜 → open / 2026/10/17〜10/21 または 〜2026/10/21 → date,end"""
    s = str(s).strip().replace("～", "〜").replace("-", "/")
    if not s: return None
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})\s*(〜\s*(?:(\d{4})/)?(\d{1,2})/(\d{1,2})|〜)?$", s)
    if not m: return {"date": s}
    d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"; out = {"date": d}
    if m.group(4) == "〜" or (m.group(4) and m.group(4).strip() == "〜"): out["open"] = True
    elif m.group(4):
        y = m.group(5) or m.group(1); out["end"] = f"{y}-{int(m.group(6)):02d}-{int(m.group(7)):02d}"
    return out

def _cast(v, t):
    if v is None or str(v).strip() == "": return None
    s = str(v).strip()
    if t == "int": return int(float(s))
    if t == "bool": return s.upper() == "TRUE"
    if t == "date": return (_parse_date_cell(s) or {}).get("date")
    if t == "list": return [x.strip() for x in re.split(r"[,、]", s) if x.strip()]
    return s

def _set(d, path, value):
    parts = re.findall(r"([A-Za-z_]+)(?:\[([^\]]+)\])?", path)
    cur = d
    for i, (name, idx) in enumerate(parts):
        last = i == len(parts) - 1
        if idx and idx.isdigit():
            lst = cur.setdefault(name, []); k = int(idx) - 1
            while len(lst) <= k: lst.append({})
            if last: lst[k] = value
            else: cur = lst[k]
        elif idx:                                   # milestones[registration] → 辞書（あとでリストに）
            dct = cur.setdefault(name, {}); 
            if last: dct[idx] = value
            else: cur = dct.setdefault(idx, {})
        else:
            if last: cur[name] = value
            else: cur = cur.setdefault(name, {})

def catalog_from_tabs(tracks_rows, tracks_en_rows, rules_rows) -> tuple[list[dict], dict]:
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
        header = rules_rows[0]; ki = header.index("キー") if "キー" in header else len(header) - 2; names = header[1:ki]
        profiles = {n: {} for n in names}
        for r in rules_rows[1:]:
            r = (r + [""] * len(header))[:len(header)]
            if not r[ki]: continue
            for j, n in enumerate(names, start=1): profiles[n][r[ki]] = int(float(r[j])) if str(r[j]).strip() else None
    return tracks, profiles

def save_catalog(tracks, profiles):
    CATALOG_TRACKS.write_text(CATALOG_TRACKS.read_text(encoding="utf-8").split("tracks:")[0] + yaml.safe_dump({"tracks": tracks}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    CATALOG_RULES.write_text(CATALOG_RULES.read_text(encoding="utf-8").split("profiles:")[0] + yaml.safe_dump({"profiles": profiles}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")

def tabs_to_contest(cid: str, ja_rows, en_rows, catalog=None) -> dict:
    f = load_fields(); types = {q["key"]: q["type"] for q in f["basic"]}
    for c in f["rounds"]["columns"]: types["rounds." + c["key"]] = c["type"]
    out = {"id": cid}
    def eat(rows):
        for r in rows[1:]:
            r = (list(r) + [""] * 6)[:6]; label, value, _prev, _use, key, _desc = r
            if not key or (key.endswith(".") and not label.strip()): continue
            if key.startswith("extra."):
                if label.strip() and str(value).strip(): out.setdefault("extra", {})[key[6:] or label.strip()] = value
                continue
            if key.startswith("tracks_enabled."):
                if str(value).upper() == "TRUE": out.setdefault("_enabled", []).append(key.split(".", 1)[1])
                continue
            if key.endswith(".date") and "milestones[" in key:
                d = _parse_date_cell(value)
                if d:
                    base = key[: -len(".date")]
                    for k2, v2 in d.items(): _set(out, f"{base}.{k2}", v2)
                continue
            base = re.sub(r"\[[^\]]+\]", "", key)
            t = types.get(base) or types.get(base.split(".")[-1]) or "text"
            v = _cast(value, t)
            if v is None: continue
            _set(out, key, v)
    eat(ja_rows)
    if en_rows: eat(en_rows)
    tracks, profiles = catalog or load_catalog()
    enabled = out.pop("_enabled", [])
    order = [t["id"] for t in tracks]
    out["tracks"] = [dict(t) for t in tracks if t["id"] in enabled]
    prof = out.get("rules_profile")
    if prof in profiles: out["rules"] = dict(profiles[prof])
    rounds = []
    for r in out.get("rounds", []):
        if not r.get("id"): continue
        r["tracks"] = [t for t in (r.get("tracks") or enabled) if t in enabled]
        ms = r.get("milestones") or {}
        r["milestones"] = [{"key": k, **{kk: vv for kk, vv in m.items() if vv not in (None, False, "")}} for k, m in ms.items() if m.get("date") or m.get("name")]
        rounds.append(r)
    out["rounds"] = rounds
    if "sponsors" in out:
        out["sponsors"] = [s for s in out["sponsors"] if s.get("name")] or None
        if not out["sponsors"]: out.pop("sponsors")
    order_keys = ["id", "kind", "name", "name_en", "language", "owners", "form_url", "paper_submission", "venue", "sponsors", "rules_profile", "rules", "tracks", "rounds", "texts", "extra"]
    return {k: out[k] for k in order_keys if k in out} | {k: v for k, v in out.items() if k not in order_keys}
