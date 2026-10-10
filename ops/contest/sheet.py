"""大会定義シートの「形」を作る（行の並び・型・色）。値の解釈（シート → contest.yaml）は contest-data の tools/sheet_import.py。

タブ「大会」:    A 項目 / B キー / C 説明（B・C は折りたたみ）/ D 用途 / E 列以降が大会（1 行目が大会 id）
タブ「大会_en」: 同じ列構成で英語の項目だけ。1 行目は「大会」タブを参照する数式なので、id を書く必要はない
タブ「トラック」「トラック_en」「ルール」: 大会横断（最初の 1 回だけ作る）

型（ドロップダウン・チェックボックス・必須の赤・用途のハイライト）は右端の先の列まで最初から敷く。
新しい大会は空いている列の 1 行目に id を書くだけで始められる。
  - 必須の赤: A 列に「＊」がある行で、1 行目に id があり、学会期間（終了）が今日以降か空の列だけ
  - 「大会_en」の必須: 上に加えて、その列の「サイトの言語」が英語か両方のとき
"""
import datetime, importlib.util, re
from ..paths import CONTESTS

def _tool():
    spec = importlib.util.spec_from_file_location("sheet_import", CONTESTS / "tools" / "sheet_import.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

SI = _tool()
TAB_JA, TAB_EN, FIRST_COL = SI.TAB_JA, SI.TAB_EN, SI.FIRST_COL
TOTAL_COLS = 40                     # 大会の列（型を敷いておく列）の数
USES = ["全部", "サイト", "フォーム", "サーバ", "通知"]
TIER = {"every": "毎回変える", "sometimes": "たまに変える", "fixed": "規則で決まる", "auto": "道具が書く"}
LANG_LABEL = {v: k for k, v in SI.SITE_LANG.items()}
MIN_ROUNDS, MIN_SPONSORS = 2, 3

def R(label, key, desc="", typ="text", options=None, required=False, header=False, indent=0, use=""):
    return {"label": ("　" * indent) + ("＊" if required else "") + label, "key": key, "desc": desc, "type": typ, "options": options,
            "header": header, "use": use}

def template(n_rounds=MIN_ROUNDS, n_sponsors=MIN_SPONSORS):
    f = SI.load_fields(); tracks, profiles = SI.load_catalog(); mk = f.get("milestone_keys", {}); ja, en = [], []
    H = lambda rows, text, note="": rows.append(R(text, "", note, header=True))
    H(ja, "■ 基本", "＊は必須（会期前の大会だけ赤くなる）。新しい大会は空いている列の 1 行目に id を書く"); H(en, "■ 基本（英語）", "英語ページで使う値。1 行目は「大会」タブと連動")
    for q in f["basic"]:
        desc = f"[{TIER.get(q.get('tier', 'every'), '')}] {q['desc']}"
        opts = list(profiles.keys()) if q["key"] == "rules_profile" else q.get("options")
        if q["type"] == "text_en": en.append(R(q["label"], q["key"], desc, "text", None, bool(q.get("required_en")), use=q.get("use", "サイト")))
        else: ja.append(R(q["label"], q["key"], desc, q["type"], opts, bool(q.get("required")), use=q.get("use", "サイト")))
    H(ja, "■ 開催トラック", "実施するトラックにチェック。トラック自体の追加は「トラック」タブ")
    for t in tracks:
        ja.append(R(f"{t['name']}（{t['id']}）", f"tracks_enabled.{t['id']}", f"[毎回変える] 人数 {t['size']}、方式 {t['mode']}", "bool", indent=1, use="サイト,フォーム,サーバ"))
    rc = {c["key"]: c for c in f["rounds"]["columns"]}
    for i in range(1, n_rounds + 1):
        req = i == 1
        H(ja, f"■ 回 {i}", "回が 1 つの大会は回 1 だけ埋める"); H(en, f"■ 回 {i}（英語）")
        ja.append(R(rc["id"]["label"], f"rounds[{i}].id", "[規則で決まる] " + rc["id"]["desc"], required=req, indent=1, use="サイト,サーバ,フォーム"))
        ja.append(R(rc["name"]["label"], f"rounds[{i}].name", "[たまに変える] " + rc["name"]["desc"], indent=1, use="サイト,フォーム"))
        en.append(R(rc["name_en"]["label"], f"rounds[{i}].name_en", rc["name_en"]["desc"], indent=1, use="サイト,フォーム"))
        ja.append(R(rc["public_name"]["label"], f"rounds[{i}].public_name", "[毎回変える] " + rc["public_name"]["desc"], required=req, indent=1, use="サーバ"))
        ja.append(R(rc["tracks"]["label"], f"rounds[{i}].tracks", "[たまに変える] 空なら開催トラック全部。この回だけ絞るときに id をカンマ区切りで", "list", indent=1, use="サイト,サーバ,フォーム"))
        H(ja, f"■ 回 {i} の日程", "使う種類だけ埋める。日付は 2026/07/04、期間は 2026/10/17〜10/21、「〜」付きは 2026/07/06〜"); H(en, f"■ 回 {i} の日程（英語の表示文）")
        for k, kl in mk.items():
            ja.append(R(f"{kl} 日付", f"rounds[{i}].milestones[{k}].date", "[毎回変える] 空ならこの日程は無し", required=(req and k in ("registration", "main_start")), indent=1, use="サイト,通知"))
            ja.append(R(f"{kl} 表示文", f"rounds[{i}].milestones[{k}].name", "[たまに変える] サイトの日程に出る文", indent=1, use="サイト"))
            en.append(R(f"{kl} 表示文（英語）", f"rounds[{i}].milestones[{k}].name_en", "英語ページの日程に出る文", indent=1, use="サイト"))
    H(ja, "■ スポンサー", "無ければ空のまま"); H(en, "■ スポンサー（英語）")
    for i in range(1, n_sponsors + 1):
        ja.append(R(f"スポンサー {i} 名前", f"sponsors[{i}].name", "[毎回変える]", indent=1, use="サイト"))
        ja.append(R(f"スポンサー {i} URL", f"sponsors[{i}].url", "[毎回変える]", "url", indent=1, use="サイト"))
        en.append(R(f"スポンサー {i} 名前（英語）", f"sponsors[{i}].name_en", "", indent=1, use="サイト"))
    H(ja, "■ 追加項目（自由）", f["extra"]["desc"] + "。A 列に項目名、B 列にキー（extra.名前）")
    for _ in range(3): ja.append(R("", "extra.", "", indent=1))
    return ja, en

# ---------- contest.yaml → セル ----------
def _fmt_date(m):
    if not m or not m.get("date"): return ""
    d = str(m["date"])[:10].replace("-", "/")
    if m.get("end"):
        e = str(m["end"])[:10].replace("-", "/"); return f"{d}〜{e[5:] if e[:4] == d[:4] else e}"
    return d + ("〜" if m.get("open") else "")

def _cell(v, t):
    if v is None or v == "": return ""
    if t == "bool": return bool(v)
    if t == "list": return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    if t == "date": return str(v)[:10].replace("-", "/")
    return v

def lookup(c, key, typ):
    if not key or key.endswith("."): return ""
    if key.startswith("tracks_enabled."): return key.split(".", 1)[1] in {t["id"] for t in c.get("tracks", [])}
    if key == "site_language":
        v = c.get("site_language") or ("both" if c.get("language") == "en" else "ja"); return LANG_LABEL.get(v, v)
    if key == "rules_profile" and not c.get("rules_profile"): return "international" if c.get("language") == "en" else "domestic"
    m = re.match(r"^(rounds|sponsors)\[(\d+)\]\.(.+)$", key)
    if m:
        lst = c.get(m.group(1)) or []; i = int(m.group(2)) - 1
        if i >= len(lst): return ""
        item, rest = lst[i], m.group(3)
        m2 = re.match(r"^milestones\[([a-z_0-9]+)\]\.(\w+)$", rest)
        if m2:
            ms = [x for x in item.get("milestones", []) if x.get("key") == m2.group(1)]
            if not ms: return ""
            return _fmt_date(ms[0]) if m2.group(2) == "date" else _cell(ms[0].get(m2.group(2)), "text")
        return _cell(item.get(rest), typ)
    if key.startswith("extra."): return _cell((c.get("extra") or {}).get(key[6:]), "text")
    d = c
    for k in key.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return _cell(d, typ)

def fill(rows, contests: dict):
    for r in rows:
        r["values"] = {cid: ("" if r["header"] else lookup(c, r["key"], r["type"])) for cid, c in contests.items()}
    return rows

def keep_custom_rows(rows, grid, col_ids):
    """シートに人が足した行（雛形に無いキー）を、作り直しても残す。「追加項目」の後ろに付ける"""
    known = {r["key"] for r in rows}
    hdr = [str(x).strip() for x in (grid[0] if grid else [])]
    for g in (grid or [])[1:]:
        g = list(g) + [""] * len(hdr)
        key = str(g[1]).strip()
        if not key or key in known or key == "extra.": continue
        row = R(str(g[0]).lstrip("　").lstrip("＊"), key, str(g[2]), required=str(g[0]).find("＊") >= 0, indent=1, use=str(g[3]))
        row["values"] = {cid: g[hdr.index(cid)] for cid in col_ids if cid in hdr}
        rows.append(row); known.add(key)
    return rows

def _col(n):
    s = ""
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s

def grid_tab(name, rows, col_ids, en_mode, past_ids=(), lang_row=None, end_row=None):
    ncol = FIRST_COL - 1 + max(TOTAL_COLS, len(col_ids) + 10)
    cols = col_ids + [""] * (ncol - (FIRST_COL - 1) - len(col_ids))
    if en_mode: cols = [f"='{TAB_JA}'!{_col(FIRST_COL + j)}1" for j in range(len(cols))]
    header = ["項目", "キー", "説明", "全部"] + cols
    data, vals, bg = [], [], []
    for i, r in enumerate(rows, start=2):
        data.append([r["label"], r["key"], r["desc"], r["use"]] + [r.get("values", {}).get(cid, "") for cid in col_ids] + [""] * (len(cols) - len(col_ids)))
        if r["header"]: bg.append({"row": i, "cols": ncol, "color": "#dbe4f0", "bold": True}); continue
        if r["type"] == "enum" and r["options"]: vals.append({"row": i, "col_start": FIRST_COL, "col_end": ncol, "type": "list", "values": r["options"]})
        elif r["type"] == "bool": vals.append({"row": i, "col_start": FIRST_COL, "col_end": ncol, "type": "checkbox"})
    vals.append({"row": 1, "col_start": 4, "col_end": 4, "type": "list", "values": USES})
    nrow = len(rows) + 1; first, last = _col(FIRST_COL), _col(ncol)
    # 会期前（終了日が空か今日以降）の列か
    def end_ref(sheet_prefix=""):
        cell = f"{sheet_prefix}{first}${end_row}" if not en_mode else f"INDIRECT(\"'{TAB_JA}'!R{end_row}C\"&COLUMN(),FALSE)"
        return f'OR({cell}="",IFERROR(IF(ISNUMBER({cell}),{cell},DATEVALUE({cell})),0)>=TODAY())'
    cond = [f'{first}$1<>""', f'{first}2=""', 'REGEXMATCH($A2,"＊")', end_ref()]
    if en_mode: cond.append(f"REGEXMATCH(INDIRECT(\"'{TAB_JA}'!R{lang_row}C\"&COLUMN(),FALSE),\"英語|両方\")")
    rules = [{"range": f"{first}2:{last}{nrow}", "formula": "=AND(" + ",".join(cond) + ")", "bg": "#f8d7da"},
             {"range": f"A2:{last}{nrow}", "formula": '=AND($D$1<>"全部",ISNUMBER(SEARCH($D$1,$D2)))', "bg": "#fff2a8"},
             {"range": f"A2:{last}{nrow}", "formula": '=AND($D$1<>"全部",$D2<>"",NOT(ISNUMBER(SEARCH($D$1,$D2))))', "fg": "#b0b0b0"}]
    groups = [{"start": 2, "end": 3, "collapsed": True}]
    old = [j for j, cid in enumerate(col_ids) if cid in past_ids][:-2]
    if old: groups.append({"start": FIRST_COL + old[0], "end": FIRST_COL + old[-1], "collapsed": True})
    return {"name": name, "header": header, "rows": data, "ncols": ncol, "widths": [300, 300, 480, 150] + [300] * len(cols), "freeze_rows": 1, "freeze_cols": 1,
            "col_groups": groups, "validations": vals, "bg": bg, "rules": rules, "protect": "A:D", "wrap": True,
            "notes": [{"cell": "D1", "text": "用途を選ぶと、その用途で使う行に色が付き、他の行は薄くなります。「全部」で元に戻ります。"}]}

def catalog_tabs():
    f = SI.load_fields(); tracks, profiles = SI.load_catalog()
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

def build_tabs(contests: dict, current_ja=None, current_en=None, today=None):
    today = today or datetime.date.today()
    n_rounds = max([2] + [len(c.get("rounds", [])) for c in contests.values()])
    n_sp = max([3] + [len(c.get("sponsors") or []) for c in contests.values()])
    ja, en = template(n_rounds, n_sp); ids = list(contests)
    fill(ja, contests); fill(en, contests)
    keep_custom_rows(ja, current_ja, ids); keep_custom_rows(en, current_en, ids)
    row_of = {r["key"]: i for i, r in enumerate(ja, start=2)}
    past = [cid for cid, c in contests.items() if not SI.is_active(c, today)]
    return catalog_tabs() + [grid_tab(TAB_JA, ja, ids, False, past, end_row=row_of["venue.end"]),
                             grid_tab(TAB_EN, en, ids, True, past, lang_row=row_of["site_language"], end_row=row_of["venue.end"])]
