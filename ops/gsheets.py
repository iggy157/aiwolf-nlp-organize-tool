"""Google スプレッドシートの読み取り（サービスアカウント）。"""
import json
from pathlib import Path
from .paths import load_secrets

def _service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa = load_secrets().get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa or not Path(sa).exists():
        raise SystemExit("サービスアカウントの鍵がありません（~/.ops/secrets.env の GOOGLE_SERVICE_ACCOUNT_JSON）。docs/setup_google.md の 4 節。")
    creds = service_account.Credentials.from_service_account_file(sa, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def read_rows(sheet_id: str) -> tuple[list[str], list[dict]]:
    """先頭シートの 1 行目を見出し、2 行目以降を辞書の列として返す。"""
    svc = _service()
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties.title").execute()
    title = meta["sheets"][0]["properties"]["title"]
    vals = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{title}'").execute().get("values", [])
    if not vals: return [], []
    header = vals[0]
    rows = [{header[i]: (r[i] if i < len(r) else "") for i in range(len(header))} for r in vals[1:] if any(c.strip() for c in r)]
    return header, rows
