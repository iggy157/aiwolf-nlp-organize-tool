"""大会定義シート: 行 = 項目、列 = 大会。schema/fields.yaml + catalog/ → 格子、格子の 1 列 → contest.yaml

タブ「大会」:    A 項目 / B キー / C 説明（B・C は折りたたみ）/ D 用途 / E 列以降が大会（1 行目が大会 id、古い順）
  - D1 のドロップダウンで用途（サイト／フォーム／サーバ／通知）を選ぶと、その用途の行に色が付き、他は薄くなる（条件付き書式）
タブ「大会_en」: 同じ列構成で、英語の項目だけ
タブ「トラック」「トラック_en」「ルール」: 大会横断（最初の 1 回だけ作る）
  - 必須の項目は A 列の頭に「＊」。必須なのに空のセルは赤くなる
  - 日程は種類ごとに「日付」「表示文」の 2 行。日付欄は 2026/07/04、期間は 2026/10/17〜10/21、「〜」付きは 2026/07/06〜
  - 開催トラックはチェックボックス。回ごとの「実施トラック」は空なら開催トラック全部
"""
import re
import datetime
import yaml
from ..paths import CONTESTS

FIELDS = CONTESTS / "schema" / "fields.yaml"
CATALOG_TRACKS = CONTESTS / "catalog" / "tracks.yaml"
CATALOG_RULES = CONTESTS / "catalog" / "rules.yaml"
TAB_JA, TAB_EN = "大会", "大会_en"
FIRST_COL = 5                      # E 列から大会（A 項目 / B キー / C 説明 / D 用途）
USES = ["全部", "サイト", "フォーム", "サーバ", "通知"]
TIER = {"every": "毎回変える", "sometimes": "たまに変える", "fixed": "規則で決まる", "auto": "道具が書く"}
MIN_ROUNDS, MIN_SPONSORS = 2, 3

def load_fields() -> dict:
    return yaml.safe_load(FIELDS.read_text(encoding="utf-8"))

def load_catalog() -> tuple[list[dict], dict]:
    tracks = yaml.safe_load(CATALOG_TRACKS.read_text(encoding="utf-8"))["tracks"]
    profiles = yaml.safe_load(CATALOG_RULES.read_text(encoding="utf-8"))["profiles"]
    return tracks, profiles

# ---------- 格子の雛形（行の並び） ----------
def _fmt_date(m: dict) -> str:
    if not m or not m.get("date"): return ""
    d = str(m["date"])[:10].replace("-", "/")
    if m.get("end"):
        e = str(m["end"])[:10].replace("-", "/")
        return f"{d}〜{e[5:] if e[:4] == d[:4] else e}"
    return d + ("〜" if m.get("open") else "")

def _cell(v, t):
    if v is None or v == "": return ""
    if t == "bool": return bool(v)
    if t == "list": return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    if t == "date": return str(v)[:10].replace("-", "/")
    return v

def R(label, key, desc="", typ="text", options=None, required=False, header=False, indent=0, blank_on_new=False, use=""):
    return {"label": ("　" * indent) + ("＊" if required else "") + label, "key": key, "desc": desc, "type": typ, "options": options,
            "required": required, "header": header, "blank_on_new": blank_on_new, "use": use}

def template(n_rounds: int = MIN_ROUNDS, n_sponsors: int = MIN_SPONSORS):
    """返り値: (日本語タブの行, 英語タブの行)。値は入っていない"""
    f = load_fields(); tracks, profiles = load_catalog(); mk = f.get("milestone_keys", {}); ja, en = [], []
    H = lambda rows, text, note="": rows.append(R(text, "", note, header=True))
    H(ja, "■ 基本", "＊は必須。赤いセルは必須なのに空。列が大会（1 行目が id）。新しい大会は右に足す"); H(en, "■ 基本（英語）", "英語ページで使う値。空なら日本語の値で代用される")
    for q in f["basic"]:
        desc = f"[{TIER.get(q.get('tier', 'every'), '')}] {q['desc']}"
        opts = list(profiles.keys()) if q["key"] == "rules_profile" else q.get("options")
        row = R(q["label"], q["key"], desc, q["type"], opts, bool(q.get("required")), blank_on_new=(q.get("tier") == "auto" or q["type"] == "date"), use=q.get("use", "サイト"))
        (en if q["type"] == "text_en" else ja).append(row)
    H(ja, "■ 開催トラック", "この大会で実施するトラックにチェック。トラック自体の追加は「トラック」タブ")
    for t in tracks:
        ja.append(R(f"{t['name']}（{t['id']}）", f"tracks_enabled.{t['id']}", f"[毎回変える] 人数 {t['size']}、方式 {t['mode']}。試合数の既定は「トラック」タブ", "bool", indent=1, use="サイト,フォーム,サーバ"))
    rc = {c["key"]: c for c in f["rounds"]["columns"]}
    for i in range(1, n_rounds + 1):
        req = i == 1
        H(ja, f"■ 回 {i}", "回が 1 つの大会は回 1 だけ埋める。3 回以上やる大会が出たら行ブロックを増やす"); H(en, f"■ 回 {i}（英語）")
        ja.append(R(rc["id"]["label"], f"rounds[{i}].id", "[規則で決まる] " + rc["id"]["desc"], "text", required=req, indent=1, use="サイト,サーバ,フォーム"))
        ja.append(R(rc["name"]["label"], f"rounds[{i}].name", "[たまに変える] " + rc["name"]["desc"], "text", indent=1, use="サイト,フォーム"))
        en.append(R(rc["name_en"]["label"], f"rounds[{i}].name_en", rc["name_en"]["desc"], "text", indent=1, use="サイト,フォーム"))
        ja.append(R(rc["public_name"]["label"], f"rounds[{i}].public_name", "[毎回変える] " + rc["public_name"]["desc"], "text", required=req, indent=1, use="サーバ"))
        ja.append(R(rc["tracks"]["label"], f"rounds[{i}].tracks", "[たまに変える] 空なら開催トラック全部。この回だけ絞るときに id をカンマ区切りで", "list", indent=1, use="サイト,サーバ,フォーム"))
        H(ja, f"■ 回 {i} の日程", "使う種類だけ埋める。日付は 2026/07/04、期間は 2026/10/17〜10/21、本戦開始のような「〜」付きは 2026/07/06〜"); H(en, f"■ 回 {i} の日程（英語の表示文）")
        for k, kl in mk.items():
            ja.append(R(f"{kl} 日付", f"rounds[{i}].milestones[{k}].date", "[毎回変える] 空ならこの日程は無し", "text", required=(req and k in ("registration", "main_start")), indent=1, blank_on_new=True, use="サイト,通知"))
            ja.append(R(f"{kl} 表示文", f"rounds[{i}].milestones[{k}].name", "[たまに変える] サイトの日程に出る文", "text", indent=1, use="サイト"))
            en.append(R(f"{kl} 表示文（英語）", f"rounds[{i}].milestones[{k}].name_en", "英語ページの日程に出る文", "text", indent=1, use="サイト"))
    H(ja, "■ スポンサー", "無ければ空のまま"); H(en, "■ スポンサー（英語）")
    for i in range(1, n_sponsors + 1):
        ja.append(R(f"スポンサー {i} 名前", f"sponsors[{i}].name", "[毎回変える]", "text", indent=1, blank_on_new=True, use="サイト"))
        ja.append(R(f"スポンサー {i} URL", f"sponsors[{i}].url", "[毎回変える]", "url", indent=1, blank_on_new=True, use="サイト"))
        en.append(R(f"スポンサー {i} 名前（英語）", f"sponsors[{i}].name_en", "", "text", indent=1, blank_on_new=True, use="サイト"))
    H(ja, "■ 追加項目（自由）", f["extra"]["desc"] + "。A 列に項目名、B 列にキー（extra.名前）")
    for i in range(1, 4): ja.append(R("", "extra.", "", "text", indent=1))
    return ja, en

# ---------- contest.yaml → セルの値 ----------
def _get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def lookup(c: dict, key: str, typ: str):
    """contest 辞書からキー（rounds[1].milestones[registration].date など）の値を取り出してセル用に整える"""
    if not key or key.endswith("."): return ""
    if key.startswith("tracks_enabled."): return key.split(".", 1)[1] in {t["id"] for t in c.get("tracks", [])}
    if key == "rules_profile" and not c.get("rules_profile"):
        return "international" if c.get("language") == "en" else "domestic"
    m = re.match(r"^(rounds|sponsors)\[(\d+)\]\.(.+)$", key)
    if m:
        lst = c.get(m.group(1)) or []; i = int(m.group(2)) - 1
        if i >= len(lst): return ""
        item = lst[i]; rest = m.group(3)
        m2 = re.match(r"^milestones\[([a-z_0-9]+)\]\.(\w+)$", rest)
        if m2:
            ms = [x for x in item.get("milestones", []) if x.get("key") == m2.group(1)]
            if not ms: return ""
            return _fmt_date(ms[0]) if m2.group(2) == "date" else _cell(ms[0].get(m2.group(2)), "text")
        return _cell(item.get(rest), typ)
    if key.startswith("extra."): return _cell((c.get("extra") or {}).get(key[6:]), "text")
    return _cell(_get(c, key), typ)

def fill(rows, contests: dict[str, dict], new_id: str | None = None, new_from: dict | None = None, full=False):
    """行の雛形に、列（大会）ごとの値を入れる。new_id を渡すと new_from の値（日付などは空）で列を足す"""
    for r in rows:
        r["values"] = {}
        for cid, c in contests.items(): r["values"][cid] = "" if r["header"] else lookup(c, r["key"], r["type"])
        if new_id:
            v = "" if r["header"] else lookup(new_from or {}, r["key"], r["type"])
            if r["blank_on_new"] and not full and r["type"] != "bool": v = ""
            r["values"][new_id] = v
    return rows

# ---------- 格子（2 次元配列）とタブ仕様 ----------
def grid_tab(name: str, rows, col_ids: list[str], en_mode: bool, today: datetime.date | None = None, past_ids: list[str] = ()):
    header = ["項目", "キー", "説明", "全部"] + col_ids          # D1 は用途のドロップダウン
    ncol = len(header); last = ncol
    data, vals, bg, req = [], [], [], []
    for i, r in enumerate(rows, start=2):
        data.append([r["label"], r["key"], r["desc"], r["use"]] + [r["values"].get(cid, "") for cid in col_ids])
        if r["header"]: bg.append({"row": i, "cols": ncol, "color": "#dbe4f0", "bold": True}); continue
        if r["type"] == "enum" and r["options"]: vals.append({"row": i, "col_start": FIRST_COL, "col_end": last, "type": "list", "values": r["options"]})
        elif r["type"] == "bool": vals.append({"row": i, "col_start": FIRST_COL, "col_end": last, "type": "checkbox"})
        if r["required"] and not en_mode and col_ids: req.append({"row": i, "col_start": FIRST_COL, "col_end": last})
    groups = [{"start": 2, "end": 3, "collapsed": True}]
    old = [j for j, cid in enumerate(col_ids) if cid in past_ids][:-2]      # 終わった大会のうち、直近 2 つを除いて畳む
    if len(old) >= 1: groups.append({"start": FIRST_COL + old[0], "end": FIRST_COL + old[-1], "collapsed": True})
    vals.append({"row": 1, "col_start": 4, "col_end": 4, "type": "list", "values": USES})
    nrow = len(rows) + 1; colz = _col_letter(ncol)
    highlight = [{"range": f"A2:{colz}{nrow}", "formula": f'=AND($D$1<>"全部",ISNUMBER(SEARCH($D$1,$D2)))', "bg": "#fff2a8"},
                 {"range": f"A2:{colz}{nrow}", "formula": f'=AND($D$1<>"全部",$D2<>"",NOT(ISNUMBER(SEARCH($D$1,$D2))))', "fg": "#b0b0b0"}]
    return {"name": name, "header": header, "rows": data, "widths": [300, 300, 480, 150] + [360] * len(col_ids), "freeze_rows": 1, "freeze_cols": 1,
            "col_groups": groups, "validations": vals, "bg": bg, "required": req, "highlight": highlight, "protect": "A:D", "wrap": True,
            "notes": [{"cell": "D1", "text": "用途を選ぶと、その用途で使う行に色が付き、他の行は薄くなります。「全部」で元に戻ります。"}]}

def _col_letter(n: int) -> str:
    s = ""
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s

def catalog_tabs() -> list[dict]:
    f = load_fields(); tracks, profiles = load_catalog()
    tr = {"name": "トラック", "header": ["id", "名前", "人数", "方式", "チーム当たり試合数（下限）", "チーム当たり試合数（上限）", "説明"],
          "rows": [["（変えない識別子）", "日本語の表示名", "村の人数（役職は roles/<人数>.yaml）", "turn=ターン式 / anytime=いつでも発話", "既定値", "", "行を足せばトラックが増える。大会で使うかどうかは「大会」タブの「開催トラック」"]]
                  + [[t["id"], t["name"], t["size"], t["mode"], (t.get("games_per_team") or ["", ""])[0], (t.get("games_per_team") or ["", ""])[1], ""] for t in tracks],
          "widths": [110, 240, 90, 120, 170, 170, 360], "validations": [{"row": 3, "row_end": 200, "col_start": 4, "col_end": 4, "type": "list", "values": ["turn", "anytime"]}],
          "bg": [{"row": 2, "cols": 7, "color": "#f1f3f4"}], "freeze_rows": 1, "keep_existing": True}
    tre = {"name": "トラック_en", "header": ["id", "名前（英語）", "日本語の名前（参考）"],
           "rows": [["（トラックタブと同じ id）", "英語ページで使う表示名", ""]] + [[t["id"], t.get("name_en", ""), t["name"]] for t in tracks],
           "widths": [110, 300, 240], "validations": [], "bg": [{"row": 2, "cols": 3, "color": "#f1f3f4"}], "freeze_rows": 1, "keep_existing": True}
    names = list(profiles.keys())
    rows = [[k["label"]] + [("" if profiles[n].get(k["key"]) is None else profiles[n][k["key"]]) for n in names] + [k["key"], k["desc"]] for k in f["rules"]["keys"]]
    ru = {"name": "ルール", "header": ["項目"] + names + ["キー", "説明"], "rows": rows, "widths": [260] + [140] * len(names) + [220, 320], "validations": [], "bg": [], "freeze_rows": 1, "keep_existing": True}
    return [tr, tre, ru]

# ---------- 格子の 1 列 → contest.yaml ----------
def _parse_date_cell(s) -> dict | None:
    s = str(s).strip().replace("～", "〜").replace("-", "/")
    if not s: return None
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})\s*(〜\s*(?:(\d{4})/)?(\d{1,2})/(\d{1,2})|〜)?$", s)
    if not m: return {"date": s}
    out = {"date": datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))}
    if m.group(4) and m.group(4).strip() == "〜": out["open"] = True
    elif m.group(4): out["end"] = datetime.date(int(m.group(5) or m.group(1)), int(m.group(6)), int(m.group(7)))
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
    parts = re.findall(r"([A-Za-z_]+)(?:\[([^\]]+)\])?", path); cur = d
    for i, (name, idx) in enumerate(parts):
        last = i == len(parts) - 1
        if idx and idx.isdigit():
            lst = cur.setdefault(name, []); k = int(idx) - 1
            while len(lst) <= k: lst.append({})
            if last: lst[k] = value
            else: cur = lst[k]
        elif idx:
            dct = cur.setdefault(name, {})
            if last: dct[idx] = value
            else: cur = dct.setdefault(idx, {})
        else:
            if last: cur[name] = value
            else: cur = cur.setdefault(name, {})

def grid_columns(grid: list[list]) -> list[str]:
    """1 行目の D 列以降 = 大会 id"""
    return [str(x).strip() for x in (grid[0] if grid else [])[FIRST_COL - 1:] if str(x).strip()]

def column_items(grid: list[list], cid: str) -> list[tuple[str, object, str]]:
    """(項目, 値, キー) の列。grid の 1 行目から cid の列を探す"""
    hdr = grid[0] if grid else []
    if cid not in [str(x).strip() for x in hdr]: return []
    j = [str(x).strip() for x in hdr].index(cid); out = []
    for r in grid[1:]:
        r = list(r) + [""] * (j + 1)
        out.append((str(r[0]), r[j], str(r[1]).strip()))
    return out

def items_to_contest(cid: str, ja_items, en_items=None, catalog=None) -> dict:
    f = load_fields(); types = {q["key"]: q["type"] for q in f["basic"]}
    for c in f["rounds"]["columns"]: types["rounds." + c["key"]] = c["type"]
    out = {"id": cid}
    def eat(items):
        for label, value, key in items:
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
                    for k2, v2 in d.items(): _set(out, key[:-5] + "." + k2, v2)
                continue
            base = re.sub(r"\[[^\]]+\]", "", key)
            v = _cast(value, types.get(base) or types.get(base.split(".")[-1]) or "text")
            if v is None: continue
            _set(out, key, v)
    eat(ja_items)
    if en_items: eat(en_items)
    tracks, profiles = catalog or load_catalog()
    enabled = out.pop("_enabled", [])
    out["tracks"] = [dict(t) for t in tracks if t["id"] in enabled]
    if out.get("rules_profile") in profiles: out["rules"] = dict(profiles[out["rules_profile"]])
    rounds = []
    for r in out.get("rounds", []):
        if not r.get("id"): continue
        r["tracks"] = [t for t in (r.get("tracks") or enabled) if t in enabled]
        ms = r.get("milestones") or {}
        r["milestones"] = [{"key": k, **{kk: vv for kk, vv in m.items() if vv not in (None, False, "")}} for k, m in ms.items() if m.get("date")]
        r["milestones"].sort(key=lambda m: str(m["date"]))          # 日程は日付順
        rounds.append(r)
    out["rounds"] = rounds
    if "sponsors" in out:
        out["sponsors"] = [s for s in out["sponsors"] if s.get("name")]
        if not out["sponsors"]: out.pop("sponsors")
    order = ["id", "kind", "name", "name_en", "language", "owners", "form_url", "paper_submission", "venue", "sponsors", "rules_profile", "rules", "tracks", "rounds", "texts", "extra"]
    return {k: out[k] for k in order if k in out} | {k: v for k, v in out.items() if k not in order}

def catalog_from_tabs(tracks_rows, tracks_en_rows, rules_rows) -> tuple[list[dict], dict]:
    tracks, profiles = load_catalog()
    if tracks_rows and len(tracks_rows) > 2:
        en_map = {r[0]: (r[1] if len(r) > 1 else "") for r in (tracks_en_rows or [])[2:] if r and r[0]}
        tracks = []
        for r in tracks_rows[2:]:
            r = (list(r) + [""] * 7)[:7]
            if not str(r[0]).strip(): continue
            t = {"id": r[0].strip(), "name": r[1], "name_en": en_map.get(r[0].strip(), ""), "size": int(float(r[2])), "mode": r[3]}
            if str(r[4]).strip(): t["games_per_team"] = [int(float(r[4])), int(float(r[5] or r[4]))]
            tracks.append(t)
    if rules_rows and len(rules_rows) > 1:
        header = rules_rows[0]; ki = header.index("キー") if "キー" in header else len(header) - 2; names = header[1:ki]
        profiles = {n: {} for n in names}
        for r in rules_rows[1:]:
            r = (list(r) + [""] * len(header))[:len(header)]
            if not r[ki]: continue
            for j, n in enumerate(names, start=1): profiles[n][r[ki]] = int(float(r[j])) if str(r[j]).strip() else None
    return tracks, profiles

def save_catalog(tracks, profiles):
    CATALOG_TRACKS.write_text(CATALOG_TRACKS.read_text(encoding="utf-8").split("tracks:")[0] + yaml.safe_dump({"tracks": tracks}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    CATALOG_RULES.write_text(CATALOG_RULES.read_text(encoding="utf-8").split("profiles:")[0] + yaml.safe_dump({"profiles": profiles}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
