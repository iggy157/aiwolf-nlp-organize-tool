"""置き場所の規約。contests リポジトリは環境変数 AIWOLF_CONTESTS で上書きできる（既定はこのリポジトリの隣）。"""
import os
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
CONTESTS = Path(os.environ.get("AIWOLF_CONTESTS", OPS.parent / "aiwolf-nlp-contest-data")).resolve()
SECRETS = Path(os.environ.get("OPS_SECRETS", Path.home() / ".ops" / "secrets.env"))

def contest_dir(cid: str) -> Path:
    return CONTESTS / "contests" / cid

def ops_contest_dir(cid: str) -> Path:
    d = OPS / "contests" / cid; d.mkdir(parents=True, exist_ok=True); return d

def load_secrets() -> dict:
    out = {}
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k.strip()] = v.strip()
    return out
