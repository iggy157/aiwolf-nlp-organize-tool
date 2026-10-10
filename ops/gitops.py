"""contest-data（git リポジトリ）の pull と commit/push。シートのボタン（GitHub Actions）も同じリポジトリに push するので、書く前に必ず pull する。"""
import subprocess, sys
from .paths import CONTESTS

def _git(*args, check=True):
    r = subprocess.run(["git", "-C", str(CONTESTS), *args], capture_output=True, text=True)
    if check and r.returncode != 0: sys.exit(f"git {' '.join(args)} が失敗しました:\n{r.stderr.strip()}")
    return r.stdout.strip()

def pull():
    if _git("status", "--porcelain"):
        print(f"注意: {CONTESTS} に未コミットの変更があるので pull しません"); return
    _git("pull", "-q", "--ff-only")

def commit_push(paths: list[str], message: str, push=True) -> bool:
    _git("add", "-A", *paths)
    if not _git("diff", "--cached", "--name-only"): return False
    _git("commit", "-q", "-m", message)
    if push:
        _git("pull", "-q", "--rebase"); _git("push", "-q")
    return True
