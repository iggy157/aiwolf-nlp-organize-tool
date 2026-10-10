"""contests リポジトリの読み書き。"""
import yaml
from .paths import contest_dir

def load_contest(cid: str) -> dict:
    p = contest_dir(cid) / "contest.yaml"
    if not p.exists():
        raise SystemExit(f"contest.yaml がありません: {p}\n先に aiwolf-nlp-contest-data に contests/{cid}/contest.yaml を書いてください。")
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def set_contest_field(cid: str, key: str, value: str) -> None:
    """contest.yaml の最上位の項目を 1 つ書き換える（並びとコメントを保つため、行の置換で行う）。無ければ末尾ではなく id の次に足す。"""
    import re
    p = contest_dir(cid) / "contest.yaml"; s = p.read_text(encoding="utf-8")
    line = f"{key}: {value}"
    if re.search(rf"^{re.escape(key)}:.*$", s, re.M):
        s = re.sub(rf"^{re.escape(key)}:.*$", line, s, count=1, flags=re.M)
    else:
        s = re.sub(r"^(id: .*\n)", lambda m: m.group(1) + line + "\n", s, count=1, flags=re.M)
    p.write_text(s, encoding="utf-8")
