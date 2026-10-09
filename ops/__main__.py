import argparse, sys
from . import paths
from .form import cli as form_cli
from .sync import cli as sync_cli
from .server import cli as server_cli
from .results import cli as results_cli

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ops", description="人狼知能コンテスト 運営ツール")
    sub = ap.add_subparsers(dest="group", required=True)
    form_cli.add_parser(sub)
    sync_cli.add_parser(sub)
    server_cli.add_parser(sub)
    results_cli.add_parser(sub)
    a = ap.parse_args(argv)
    return a.func(a)

if __name__ == "__main__":
    sys.exit(main() or 0)
