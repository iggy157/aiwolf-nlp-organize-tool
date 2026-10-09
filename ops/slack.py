"""Slack Bot（chat.postMessage）。トークンは ~/.ops/secrets.env の SLACK_BOT_TOKEN。"""
import json, urllib.request
import yaml
from .paths import load_secrets, OPS

def _token() -> str:
    t = load_secrets().get("SLACK_BOT_TOKEN")
    if not t: raise SystemExit("SLACK_BOT_TOKEN がありません（~/.ops/secrets.env）")
    return t

def _api(method: str, payload: dict) -> dict:
    req = urllib.request.Request(f"https://slack.com/api/{method}", data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if not d.get("ok"): raise SystemExit(f"Slack {method} に失敗: {d.get('error')}")
    return d

def post(channel: str, text: str) -> None:
    _api("chat.postMessage", {"channel": channel, "text": text})

def people() -> dict:
    cfg = yaml.safe_load((OPS / "ops/config.yaml").read_text(encoding="utf-8")) or {}
    return cfg.get("people", {})

def dm_owners(owners: list[str], text: str) -> list[str]:
    """contest.yaml の owners（config.yaml の people のキー）に DM。送った相手の名前を返す"""
    sent = []
    for name in owners:
        p = people().get(name)
        if not p or not p.get("slack_user"):
            print(f"  [slack] {name} の slack_user が ops/config.yaml にありません。送れませんでした。"); continue
        post(p["slack_user"], text); sent.append(name)
    return sent
