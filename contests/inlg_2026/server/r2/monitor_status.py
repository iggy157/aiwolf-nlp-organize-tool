#!/usr/bin/env python3
"""aiwolf-nlp-server の稼働状況を外部から観測し、人が読める一覧をファイルへ出力し続ける。

サーバ本体には一切手を入れず、以下の4つの情報源だけを使う。

  1. REST API (/api/v1/healthz, /readyz, /games)  … サーバ状態と実行中ゲームの参加チーム
  2. マッチオプティマイザの JSON (matching.output_path) … 全チーム名簿・消化数・残り対戦表
  3. サーバの標準出力ログ … 待機部屋のスナップショット。新規接続のたびに TryStartGame が
     waitingRoom.Teams() をループして UpdateTeam を呼ぶため、「チームが既に登録されています
     team=X」が待機中の全チーム分まとめて出力される。これを待機判定の主軸にする
  4. ss(8) … 生きている TCP 接続。待機部屋に残っているのに接続が無いチーム（試合が組めなく
     なる原因）を補足表示するためだけに使い、状態そのものは変えない

出力先などの設定はサーバの設定ファイル(yml)に status_monitor セクションを足して指定する。
サーバの設定読み込みは未知のキーを無視する実装なので、同居させても起動に影響しない。

    status_monitor:
      output_path: ./status.txt      # 出力先。既定 ./status.txt
      interval: 5                    # 更新間隔[秒]。既定 5
      server_log_path: ./log5.log    # サーバの標準出力を保存しているファイル
      api_base: ""                   # 空ならサーバ設定の host/port から自動組み立て
      max_remaining_matches: 20       # 残り対戦組み合わせの表示件数。0 で全件
      initial_log_scan_bytes: 8388608 # 起動時に遡って読むログの最大バイト数

使い方:  python3 monitor_status.py -c default_en_5.yml
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROLE_ORDER = ["WEREWOLF", "POSSESSED", "SEER", "MEDIUM", "BODYGUARD", "VILLAGER"]

# サーバのログ形式は slog の既定ハンドラ (log パッケージ経由) なので
#   2026/08/06 12:03:26 INFO メッセージ key=value key=value
# となる。値に空白が含まれる場合のみ引用符が付く。
TS_RE = r"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
RE_CONNECTED = re.compile(
    TS_RE + r".*?クライアントが接続しました\s+team_name=(?P<team>\S+)"
    r"\s+original_name=(?P<orig>\S+)\s+remote_addr=(?P<addr>\S+)"
)
RE_WAITING = re.compile(
    TS_RE + r".*?新しいクライアントが待機部屋に追加されました\s+team=(?P<team>\S+)"
    r"\s+remote_addr=(?P<addr>\S+)"
)
# 新規接続のたびに TryStartGame が waitingRoom.Teams() をループして UpdateTeam を呼ぶため、
# 下記3種のいずれかが「その瞬間に待機部屋にいる全チーム」として一気に出力される。
# これが待機部屋のスナップショットであり、接続状況判定の主軸に使う。
RE_TEAM_IN_ROOM = re.compile(
    TS_RE + r".*?(?:チームが既に登録されています|チームを追加しました"
    r"|チーム数が上限に達しているため追加できません)\s+team=(?P<team>\S+)"
)
RE_MATCH_FAIL = re.compile(
    TS_RE + r".*?待機部屋からの接続の取得に失敗しました\s+error=(?P<err>.+?)\s*$"
)
RE_SIGNAL = re.compile(TS_RE + r".*?シグナルを受信しました\s+signal=(?P<sig>\S+)")
RE_BOOT = re.compile(TS_RE + r".*?サーバを起動しました")
RE_ALL_FINISHED = re.compile(TS_RE + r".*?全てのゲームが終了しました")
RE_OPT_LOAD_FAIL = re.compile(TS_RE + r".*?マッチオプティマイザの読み込みに失敗しました")

LOG_TS_FMT = "%Y/%m/%d %H:%M:%S"


# --------------------------------------------------------------------------
# 表示文言（言語ごと）
# --------------------------------------------------------------------------
# 中身の数値・判定は言語に依存しない。変わるのは見出しとラベルだけ。
# 言語を足すときは S にもう1つ辞書を積み、OUTPUT_SUFFIX に名前を入れる。
OUTPUT_SUFFIX = {"ja": ".ja.txt", "en": ".en.txt"}

S = {
    "ja": {
        "title": "AIWolf Server Status",
        "warn_banner": "!!! 警告 ",
        "w_shutdown": "シャットダウン進行中: {ts} に signal={sig} を受信しています",
        "w_all_finished": "サーバは {ts} に終了しました（プロセス不在の可能性）",
        "w_opt_reload": "{ts} にマッチオプティマイザの読み込みに失敗しています（進捗が初期化された恐れ）",
        "w_opt_unreadable": "オプティマイザJSONを読めません: {path} ({err})",
        "w_log_missing": "ログファイルが見つかりません: {path}",
        "w_no_log_conf": "status_monitor.server_log_path が未設定のため接続状況を判定できません",
        "w_no_waiting": "待機部屋の記録がログにまだ現れていないため、待機中/未接続を判定できません"
                        "（クライアントが1台も接続していないか、ログを遡り切れていません）",
        "w_no_games": "実行中ゲームを取得できないため、対戦中のチームも待機中として表示されます",
        "h_server": "【サーバ】",
        "st_running": "稼働中",
        "st_draining": "終了処理中（新規接続を拒否しています）",
        "st_down": "応答なし（停止しているか、APIに到達できません）",
        "l_state": "状態", "l_version": "バージョン", "l_api": "API",
        "l_config": "設定", "l_boot": "最終起動", "unknown": "(不明)",
        "h_progress": "【進捗】",
        "l_done": "消化", "l_left": "残り", "l_running": "実行中",
        "unit_games": "試合",
        "mismatch": "  ※ 消化+残り({sum}) が game_count({total}) と一致しません",
        "l_last_fail": "直近の不成立",
        "h_conn": "【接続状況】 全{n}チーム   対戦中 {a} / 待機中 {b} / 未接続 {c} / 不明 {d}",
        "conn_ts": "   (待機部屋 {ts} 時点)",
        "c_team": "チーム", "c_status": "状態", "c_done": "消化",
        "c_left": "残り", "c_note": "備考",
        "s_ingame": "対戦中", "s_waiting": "待機中",
        "s_offline": "未接続", "s_unknown": "不明",
        "last_seen": "最終接続 {ts}",
        "no_tcp": "[TCP接続を確認できません]",
        "h_games": "【実行中のゲーム】",
        "games_unreachable": "  (APIに到達できないため取得できません)",
        "none": "  (なし)",
        "alive": "生存", "dead": "死亡",
        "h_remaining": "【残りの対戦組み合わせ】 全{n}件",
        "remaining_trunc": "（先頭{n}件を表示 / status_monitor.max_remaining_matches で変更可）",
        "footer": " 次回更新まで {sec:.0f} 秒 / このファイルは自動生成されます",
        "crash": "監視スクリプトでエラーが発生しました: {err}",
    },
    "en": {
        "title": "AIWolf Server Status",
        "warn_banner": "!!! WARNING ",
        "w_shutdown": "Shutdown in progress: signal={sig} received at {ts}",
        "w_all_finished": "The server finished at {ts} (its process may be gone)",
        "w_opt_reload": "Failed to load the match schedule at {ts} (progress may have been reset)",
        "w_opt_unreadable": "Cannot read the match schedule JSON: {path} ({err})",
        "w_log_missing": "Server log file not found: {path}",
        "w_no_log_conf": "status_monitor.server_log_path is not set, so connection state "
                         "cannot be determined",
        "w_no_waiting": "The waiting room has not appeared in the log yet, so waiting/offline "
                        "cannot be determined (no client has connected, or the log could not "
                        "be scanned far enough back)",
        "w_no_games": "Running games cannot be fetched, so teams that are in a game are shown "
                      "as waiting",
        "h_server": "[Server]",
        "st_running": "running",
        "st_draining": "draining (refusing new connections)",
        "st_down": "not responding (stopped, or the API is unreachable)",
        "l_state": "State", "l_version": "Version", "l_api": "API",
        "l_config": "Config", "l_boot": "Started", "unknown": "(unknown)",
        "h_progress": "[Progress]",
        "l_done": "Played", "l_left": "Left", "l_running": "In progress",
        "unit_games": "games",
        "mismatch": "  * played+left ({sum}) does not match game_count ({total})",
        "l_last_fail": "Last failed match",
        "h_conn": "[Connections] {n} teams   in game {a} / waiting {b} / "
                  "offline {c} / unknown {d}",
        "conn_ts": "   (waiting room as of {ts})",
        "c_team": "Team", "c_status": "Status", "c_done": "Played",
        "c_left": "Left", "c_note": "Note",
        "s_ingame": "in game", "s_waiting": "waiting",
        "s_offline": "offline", "s_unknown": "unknown",
        "last_seen": "last seen {ts}",
        "no_tcp": "[no TCP connection found]",
        "h_games": "[Running games]",
        "games_unreachable": "  (cannot fetch: the API is unreachable)",
        "none": "  (none)",
        "alive": "alive", "dead": "dead",
        "h_remaining": "[Remaining matches] {n} total",
        "remaining_trunc": " (showing the first {n} / change with "
                           "status_monitor.max_remaining_matches)",
        "footer": " next update in {sec:.0f}s / this file is generated automatically",
        "crash": "The monitor script hit an error: {err}",
    },
}


# --------------------------------------------------------------------------
# 表示ユーティリティ（全角を2セルとして数える）
# --------------------------------------------------------------------------
def width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - width(s))


def bar(done: int, total: int, cells: int = 40) -> str:
    if total <= 0:
        return "[" + "-" * cells + "]"
    filled = int(cells * done / total)
    return "[" + "#" * filled + "-" * (cells - filled) + "]"


# --------------------------------------------------------------------------
# 設定
# --------------------------------------------------------------------------
class Settings:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        self.raw = cfg

        mon = cfg.get("status_monitor") or {}
        base_dir = config_path.parent

        self.output_path = Path(mon.get("output_path") or "./status.txt")
        self.interval = float(mon.get("interval") or 5)
        self.max_remaining = int(mon.get("max_remaining_matches", 20))
        self.initial_scan_bytes = int(mon.get("initial_log_scan_bytes", 8 * 1024 * 1024))

        log_path = mon.get("server_log_path") or ""
        self.server_log_path = Path(log_path) if log_path else None

        matching = cfg.get("matching") or {}
        self.optimizer_path = Path(matching.get("output_path") or "./match_optimizer.json")
        self.is_optimize = bool(matching.get("is_optimize"))

        ws = ((cfg.get("server") or {}).get("web_socket") or {})
        self.port = int(ws.get("port") or 8080)
        host = str(ws.get("host") or "127.0.0.1")
        # 0.0.0.0 や :: は待ち受けアドレスであって接続先ではない
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        self.api_base = (mon.get("api_base") or f"http://{host}:{self.port}").rstrip("/")

        auth = ((cfg.get("server") or {}).get("authentication") or {})
        self.auth_enabled = bool(auth.get("enable"))

        # 相対パスは設定ファイルの位置ではなく実行時のカレントを基準にする。
        # サーバもカレント基準で解決するため、同じディレクトリで動かす前提に合わせる。
        self.base_dir = base_dir

    def secret_key(self) -> str | None:
        if os.environ.get("SECRET_KEY"):
            return os.environ["SECRET_KEY"]
        for candidate in (Path(".env"), Path("config/.env"), self.base_dir / ".env"):
            if candidate.is_file():
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("SECRET_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        return None


def make_receiver_token(secret: str) -> str:
    """IsValidReceiver が要求するのは HS256 署名と role=RECEIVER クレームのみ。"""

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    exp = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    payload = b64(json.dumps({"role": "RECEIVER", "exp": exp}, separators=(",", ":")).encode())
    signing_input = header + b"." + payload
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + b64(sig)).decode()


# --------------------------------------------------------------------------
# 情報源1: REST API
# --------------------------------------------------------------------------
class Api:
    def __init__(self, base: str, token: str | None):
        self.base = base
        self.token = token
        self.last_error: str | None = None
        # 監視対象は同一ホストなので、環境変数のプロキシ設定は必ず無視する
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _get(self, path: str, auth: bool = False):
        url = self.base + path
        req = urllib.request.Request(url)
        if auth and self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        with self.opener.open(req, timeout=3) as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def healthz(self):
        try:
            _, body = self._get("/api/v1/healthz")
            return body
        except Exception as e:
            self.last_error = f"healthz: {e}"
            return None

    def readyz(self) -> str:
        try:
            status, body = self._get("/api/v1/readyz")
            return str(body.get("status", "ok"))
        except urllib.error.HTTPError as e:
            if e.code == 503:
                return "draining"
            return f"error({e.code})"
        except Exception:
            return "unreachable"

    def games(self):
        """実行中ゲームの一覧。終了したゲームは登録簿から消えるので実行中のみが返る。"""
        try:
            _, body = self._get("/api/v1/games", auth=True)
            games = body.get("games") or []
        except Exception as e:
            self.last_error = f"games: {e}"
            return None
        # 一覧側は day を持たないため、個別取得でライブ状態を足す
        for g in games:
            try:
                _, detail = self._get("/api/v1/games/" + str(g.get("id")), auth=True)
                if isinstance(detail, dict):
                    g.update({k: v for k, v in detail.items() if v not in (None, 0, "")})
            except Exception:
                pass
        return games


# --------------------------------------------------------------------------
# 情報源2: マッチオプティマイザ JSON
# --------------------------------------------------------------------------
class Optimizer:
    def __init__(self, path: Path):
        self.path = path
        self.error: str | None = None
        self.idx_team: dict[int, str] = {}
        self.scheduled: list[dict] = []
        self.ended: list[dict] = []
        self.game_count = 0
        self.team_count = 0
        self.load()

    def load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            self.error = str(e)
            return
        self.error = None
        self.idx_team = {int(k): v for k, v in (d.get("idx_team_map") or {}).items()}
        self.scheduled = d.get("scheduled_matches") or []
        self.ended = d.get("ended_matches") or []
        self.game_count = int(d.get("game_count") or 0)
        self.team_count = int(d.get("team_count") or 0)

    @property
    def teams(self) -> list[str]:
        return [self.idx_team[i] for i in sorted(self.idx_team)]

    def counts_by_team(self) -> dict[str, dict[str, int]]:
        """チームごとの消化数・残り数を数える。履歴も対戦表も idx 基準なので改名に強い。"""
        out = {name: {"done": 0, "left": 0} for name in self.idx_team.values()}
        for match in self.ended:
            for idxs in match.values():
                for i in idxs:
                    name = self.idx_team.get(i)
                    if name:
                        out[name]["done"] += 1
        for sm in self.scheduled:
            for idxs in (sm.get("role_idxs") or {}).values():
                for i in idxs:
                    name = self.idx_team.get(i)
                    if name:
                        out[name]["left"] += 1
        return out

    def remaining_matches(self) -> list[list[tuple[str, list[str]]]]:
        result = []
        for sm in self.scheduled:
            role_idxs = sm.get("role_idxs") or {}
            roles = sorted(
                role_idxs.keys(),
                key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else len(ROLE_ORDER),
            )
            result.append([(r, [self.idx_team.get(i, f"?{i}") for i in role_idxs[r]]) for r in roles])
        return result


# --------------------------------------------------------------------------
# 情報源3: サーバログの追記追尾
# --------------------------------------------------------------------------
class LogTailer:
    def __init__(self, path: Path | None, initial_bytes: int):
        self.path = path
        self.initial_bytes = initial_bytes
        self.fh = None
        self.inode = None
        self.buf = ""
        # team -> {remote_addr -> 最終観測時刻}
        self.team_addrs: dict[str, dict[str, str]] = {}
        self.last_seen: dict[str, str] = {}
        # 待機部屋スナップショット。(時刻, チーム集合) を新しい順に最大3件保持する
        self.bursts: list[tuple[datetime, set[str]]] = []
        self.last_match_error: tuple[str, str] | None = None
        self.last_signal: tuple[str, str] | None = None
        self.last_boot: str | None = None
        self.last_all_finished: str | None = None
        self.optimizer_load_failed: str | None = None
        self.missing_path: Path | None = None
        self.lines_read = 0
        self.bytes_read = 0
        self.scan_start = 0
        self.last_line_ts: str | None = None

    def _open(self):
        if self.path is None:
            return
        try:
            st = self.path.stat()
        except FileNotFoundError:
            # 文言は言語ごとに組むので、ここではパスだけ覚える
            self.missing_path = self.path
            self.fh = None
            return
        self.missing_path = None
        fh = self.path.open("r", encoding="utf-8", errors="replace")
        if st.st_size > self.initial_bytes:
            fh.seek(st.st_size - self.initial_bytes)
            fh.readline()  # 行の途中から始まるので1行捨てる
        self.scan_start = fh.tell()
        self.fh = fh
        self.inode = st.st_ino

    def poll(self):
        if self.path is None:
            return
        if self.fh is None:
            self._open()
            if self.fh is None:
                return
        try:
            st = self.path.stat()
            # ローテートや切り詰めを検知したら開き直す
            if st.st_ino != self.inode or st.st_size < self.fh.tell():
                self.fh.close()
                self.initial_bytes = st.st_size  # 開き直しでは全部読む
                self._open()
                if self.fh is None:
                    return
        except FileNotFoundError:
            self.fh = None
            return

        chunk = self.fh.read()
        if not chunk:
            return
        self.buf += chunk
        self.bytes_read += len(chunk)
        *lines, self.buf = self.buf.split("\n")
        for line in lines:
            self.lines_read += 1
            if len(line) >= 19 and line[4] == "/" and line[13] == ":":
                self.last_line_ts = line[:19]
            self._consume(line)

    def _add_to_burst(self, ts_str: str, team: str):
        try:
            ts = datetime.strptime(ts_str, LOG_TS_FMT)
        except ValueError:
            return
        # 同一バーストはマイクロ秒で出力されるが、秒境界を跨ぐことがあるので1秒まで同一視する
        if self.bursts and 0 <= (ts - self.bursts[-1][0]).total_seconds() <= 1:
            self.bursts[-1][1].add(team)
            return
        self.bursts.append((ts, {team}))
        if len(self.bursts) > 3:
            self.bursts.pop(0)

    def waiting_snapshot(self) -> tuple[set[str] | None, datetime | None]:
        """待機部屋の最新スナップショット。書き込み途中のバーストを掴まないよう2秒待つ。"""
        if not self.bursts:
            return None, None
        now = datetime.now()
        for ts, teams in reversed(self.bursts):
            if (now - ts).total_seconds() >= 2:
                return set(teams), ts
        ts, teams = self.bursts[-1]
        return set(teams), ts

    def _consume(self, line: str):
        m = RE_TEAM_IN_ROOM.search(line)
        if m:
            self._add_to_burst(m.group("ts"), m.group("team").strip("\"'"))
            return
        m = RE_CONNECTED.search(line) or RE_WAITING.search(line)
        if m:
            team = m.group("team").strip("\"'")
            addr = norm_addr(m.group("addr").strip("\"'"))
            ts = m.group("ts")
            self.team_addrs.setdefault(team, {})[addr] = ts
            self.last_seen[team] = ts
            return
        m = RE_MATCH_FAIL.search(line)
        if m:
            self.last_match_error = (m.group("ts"), m.group("err").strip("\"'"))
            return
        m = RE_SIGNAL.search(line)
        if m:
            self.last_signal = (m.group("ts"), m.group("sig"))
            return
        m = RE_BOOT.search(line)
        if m:
            self.last_boot = m.group("ts")
            # 起動を見たらそれ以前のシャットダウン痕跡と待機部屋の記録は無効
            self.last_signal = None
            self.last_all_finished = None
            self.bursts.clear()
            self.last_match_error = None
            return
        m = RE_ALL_FINISHED.search(line)
        if m:
            self.last_all_finished = m.group("ts")
            return
        m = RE_OPT_LOAD_FAIL.search(line)
        if m:
            self.optimizer_load_failed = m.group("ts")


# --------------------------------------------------------------------------
# 情報源4: ss による生存確認
# --------------------------------------------------------------------------
def norm_addr(a: str) -> str:
    """ss は IPv4 射影アドレスを ::ffff:1.2.3.4 形式で出すが Go の RemoteAddr は 1.2.3.4 を返す。"""
    a = a.strip()
    if a.startswith("["):
        a = a[1:].replace("]", "", 1)
    if a.startswith("::ffff:"):
        a = a[len("::ffff:"):]
    return a


def established_peers(port: int) -> set[str] | None:
    """サーバの待ち受けポートに繋がっている peer の ip:port 集合。取れなければ None。"""
    try:
        proc = subprocess.run(
            ["ss", "-tnH", "state", "established"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    peers = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local, peer = norm_addr(parts[2]), norm_addr(parts[3])
        try:
            if int(local.rsplit(":", 1)[1]) != port:
                continue
        except (IndexError, ValueError):
            continue
        peers.add(peer)
    return peers


# --------------------------------------------------------------------------
# レポート生成
# --------------------------------------------------------------------------
def build_report(st: Settings, api: Api, opt: Optimizer, tail: LogTailer,
                 peers: set[str] | None, lang: str = "ja") -> str:
    """1言語ぶんの状況レポートを組む。判定はすべて言語に依存しない。"""
    s = S[lang]
    now = datetime.now().astimezone()
    L: list[str] = []
    line = "=" * 78

    health = api.healthz()
    ready = api.readyz()
    games = api.games()
    waiting_set, waiting_ts = tail.waiting_snapshot()

    L.append(line)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %z")
    L.append(" " + pad(s["title"], 78 - 2 - len(stamp)) + stamp)
    L.append(line)
    L.append("")

    # ---- 警告バナー -------------------------------------------------------
    warns = []
    if tail.last_signal:
        ts, sig = tail.last_signal
        warns.append(s["w_shutdown"].format(ts=ts, sig=sig))
    if tail.last_all_finished:
        warns.append(s["w_all_finished"].format(ts=tail.last_all_finished))
    if tail.optimizer_load_failed:
        warns.append(s["w_opt_reload"].format(ts=tail.optimizer_load_failed))
    if opt.error:
        warns.append(s["w_opt_unreadable"].format(path=opt.path, err=opt.error))
    if tail.missing_path is not None:
        warns.append(s["w_log_missing"].format(path=tail.missing_path))
    if st.server_log_path is None:
        warns.append(s["w_no_log_conf"])
    elif waiting_set is None:
        warns.append(s["w_no_waiting"])
    if games is None:
        warns.append(s["w_no_games"]
                     + (f" ({api.last_error})" if api.last_error else ""))
    if warns:
        L.append(s["warn_banner"] + "!" * max(4, 78 - width(s["warn_banner"])))
        for w in warns:
            L.append("  * " + w)
        L.append("")

    # ---- サーバ -----------------------------------------------------------
    keys = [s["l_state"], s["l_version"], s["l_api"], s["l_config"], s["l_boot"]]
    kw = max(width(k) for k in keys)

    def kv(key: str, value) -> str:
        return f"  {pad(key, kw)} : {value}"

    L.append(s["h_server"])
    if health:
        state = {"ready": s["st_running"], "ok": s["st_running"],
                 "draining": s["st_draining"]}.get(ready, ready)
        L.append(kv(s["l_state"], state))
        L.append(kv(s["l_version"], health.get("version") or s["unknown"]))
    else:
        L.append(kv(s["l_state"], s["st_down"]))
    L.append(kv(s["l_api"], st.api_base))
    L.append(kv(s["l_config"], st.config_path))
    if tail.last_boot:
        L.append(kv(s["l_boot"], tail.last_boot))
    L.append("")

    # ---- 進捗 -------------------------------------------------------------
    done = len(opt.ended)
    left = len(opt.scheduled)
    total = opt.game_count or (done + left)
    pct = (done / total * 100) if total else 0.0
    pkeys = [s["l_done"], s["l_left"], s["l_running"]]
    pw = max(width(k) for k in pkeys)
    L.append(s["h_progress"])
    L.append(f"  {pad(s['l_done'], pw)} : {done} / {total} {s['unit_games']}  ({pct:.1f}%)")
    L.append(f"  {pad(s['l_left'], pw)} : {left} {s['unit_games']}")
    L.append("  " + bar(done, total) + f"  {pct:.1f}%")
    n_running = len(games) if games is not None else "?"
    L.append(f"  {pad(s['l_running'], pw)} : {n_running} {s['unit_games']}")
    if done + left != total and total:
        L.append(s["mismatch"].format(sum=done + left, total=total))
    if tail.last_match_error:
        ts, err = tail.last_match_error
        L.append(f"  {s['l_last_fail']}  : {ts}  {err}")
    L.append("")

    # ---- 接続状況 ---------------------------------------------------------
    in_game: dict[str, list[dict]] = {}
    if games:
        for g in games:
            for a in g.get("agents") or []:
                in_game.setdefault(a.get("team_name", ""), []).append({"game": g, "agent": a})

    # ss が一致を1件も返さない環境（NAT越しやアドレス表記差）では補足表示自体を出さない
    ss_usable = bool(peers) and any(
        set(tail.team_addrs.get(t, {})) & peers for t in opt.teams)

    counts = opt.counts_by_team()
    rows = []
    tally = {k: 0 for k in ("s_ingame", "s_waiting", "s_offline", "s_unknown")}
    for team in opt.teams:
        if team in in_game:
            key = "s_ingame"
        elif waiting_set is None:
            key = "s_unknown"
        elif team in waiting_set:
            key = "s_waiting"
        else:
            key = "s_offline"
        tally[key] += 1
        c = counts.get(team, {"done": 0, "left": 0})
        detail = ""
        if key == "s_ingame":
            entry = in_game[team][0]
            g, a = entry["game"], entry["agent"]
            day = g.get("day")
            detail = f"{a.get('role', '')} / {a.get('game_name', '')}"
            if day:
                detail += f" / day {day}"
        elif tail.last_seen.get(team):
            detail = s["last_seen"].format(ts=tail.last_seen[team])
        # 待機部屋には残っているが TCP 接続が見当たらないケース。試合が組めない原因になる。
        if key == "s_waiting" and ss_usable and not (set(tail.team_addrs.get(team, {})) & peers):
            detail = (detail + "  " if detail else "") + s["no_tcp"]
        rows.append((team, s[key], c["done"], c["left"], detail))

    head = s["h_conn"].format(n=len(opt.teams), a=tally["s_ingame"],
                              b=tally["s_waiting"], c=tally["s_offline"],
                              d=tally["s_unknown"])
    if waiting_ts:
        head += s["conn_ts"].format(ts=f"{waiting_ts:%H:%M:%S}")
    L.append(head)

    name_w = max([width(t) for t in opt.teams] + [12]) + 2
    stat_w = max([width(s[k]) for k in tally] + [width(s["c_status"])]) + 2
    done_w = max(width(s["c_done"]), 4) + 2
    left_w = max(width(s["c_left"]), 4) + 2
    L.append("  " + pad(s["c_team"], name_w) + pad(s["c_status"], stat_w)
             + pad(s["c_done"], done_w) + pad(s["c_left"], left_w) + s["c_note"])
    L.append("  " + "-" * (name_w + stat_w + done_w + left_w + 30))
    for team, status, d, l_, detail in rows:
        L.append("  " + pad(team, name_w) + pad(status, stat_w)
                 + pad(str(d), done_w) + pad(str(l_), left_w) + detail)
    L.append("")

    # ---- 実行中のゲーム ---------------------------------------------------
    L.append(s["h_games"])
    if games is None:
        L.append(s["games_unreachable"])
    elif not games:
        L.append(s["none"])
    else:
        for g in games:
            day = g.get("day")
            head = f"  {g.get('id')}"
            if day:
                head += f"   day {day}"
            L.append(head)
            status_by = g.get("status_by_agent") or {}
            for a in sorted(g.get("agents") or [], key=lambda x: x.get("idx", 0)):
                alive = status_by.get(str(a.get("idx")), status_by.get(a.get("idx")))
                mark = {"ALIVE": s["alive"], "DEAD": s["dead"]}.get(alive, "")
                L.append("      " + pad(str(a.get("role", "")), 10)
                         + pad(str(a.get("team_name", "")), name_w)
                         + pad(str(a.get("game_name", "")), 12) + mark)
    L.append("")

    # ---- 残りの対戦組み合わせ ---------------------------------------------
    remaining = opt.remaining_matches()
    shown = remaining if st.max_remaining <= 0 else remaining[: st.max_remaining]
    header = s["h_remaining"].format(n=len(remaining))
    if len(shown) < len(remaining):
        header += s["remaining_trunc"].format(n=len(shown))
    L.append(header)
    if not remaining:
        L.append(s["none"])
    for i, match in enumerate(shown, 1):
        parts = [f"{role}: {', '.join(teams)}" for role, teams in match]
        L.append(f"  {i:>4}. " + "  |  ".join(parts))
    L.append("")

    L.append(line)
    L.append(s["footer"].format(sec=st.interval))
    L.append(line)
    return "\n".join(L) + "\n"


def print_debug(st: Settings, api: Api, opt: Optimizer, tail: LogTailer,
                peers: set[str] | None):
    """なぜその判定になったのかを全部出す。接続状況が合わないときの切り分け用。"""
    p = print
    p("=" * 70)
    p("診断モード")
    p("=" * 70)

    p("\n[1] 参照しているファイル")
    p(f"  設定            : {st.config_path.resolve()}")
    p(f"  カレント        : {Path.cwd()}")
    p(f"  オプティマイザ  : {st.optimizer_path}  "
      f"(存在: {st.optimizer_path.exists()})")
    p(f"  サーバログ      : {st.server_log_path}  "
      f"(存在: {st.server_log_path.exists() if st.server_log_path else False})")
    if st.server_log_path and st.server_log_path.exists():
        size = st.server_log_path.stat().st_size
        p(f"     サイズ       : {size:,} バイト")
        p(f"     走査開始位置 : {tail.scan_start:,} バイト目"
          + ("  ← 先頭から" if tail.scan_start == 0
             else f"  (末尾 {size - tail.scan_start:,} バイトのみ走査)"))
        p(f"     読んだ行数   : {tail.lines_read:,}")
        p(f"     最終行の時刻 : {tail.last_line_ts or '(時刻付きの行が無い)'}")
    if tail.missing_path is not None:
        p(f"  !! ログファイルが見つかりません: {tail.missing_path}")

    p("\n[2] 待機部屋スナップショット（ログの『チームが既に登録されています』等から）")
    if not tail.bursts:
        p("  検出できませんでした。")
        p("  → 走査範囲にバーストが1件もありません。以下を確認してください:")
        p("     ・server_log_path が本当に今動いているサーバの出力先か")
        p("     ・status_monitor.initial_log_scan_bytes を増やす（既定8MB）")
        p("     ・grep -c 'チームが既に登録されています' <ログ> が0でないか")
    for ts, teams in tail.bursts:
        p(f"  {ts:%Y/%m/%d %H:%M:%S}  {len(teams)}チーム: {sorted(teams)}")
    ws, wts = tail.waiting_snapshot()
    p(f"  → 採用: {wts}  {sorted(ws) if ws else None}")

    p("\n[3] 名簿（オプティマイザJSONの idx_team_map）")
    if opt.error:
        p(f"  !! 読めません: {opt.error}")
    p(f"  {len(opt.teams)}チーム: {opt.teams}")

    p("\n[4] 突き合わせ")
    roster = set(opt.teams)
    if ws is None:
        p("  待機部屋スナップショットが無いため比較できません。")
    else:
        p(f"  名簿にあり待機部屋にもいる  : {sorted(roster & ws)}")
        p(f"  名簿にあるが待機部屋にいない: {sorted(roster - ws)}")
        extra = ws - roster
        p(f"  待機部屋にいるが名簿に無い  : {sorted(extra)}")
        if extra:
            p("  !! ここが空でない場合、ログのチーム名と idx_team_map のチーム名が")
            p("     食い違っています。これが『未接続』になる直接の原因です。")

    p("\n[5] API")
    h = api.healthz()
    p(f"  healthz : {h}")
    p(f"  readyz  : {api.readyz()}")
    games = api.games()
    if games is None:
        p(f"  games   : 取得失敗  ({api.last_error})")
    else:
        p(f"  games   : 実行中 {len(games)} 件")
        for g in games:
            teams = [a.get("team_name") for a in (g.get("agents") or [])]
            p(f"    {g.get('id')}  {teams}")

    p("\n[6] ss による TCP 生存確認（補助情報。判定には使いません）")
    if peers is None:
        p("  ss を実行できませんでした")
    else:
        p(f"  ポート {st.port} への確立済み接続: {len(peers)} 件")
        hit = {t: sorted(set(tail.team_addrs.get(t, {})) & peers) for t in opt.teams}
        hit = {k: v for k, v in hit.items() if v}
        p(f"  ログの remote_addr と一致したチーム: {sorted(hit) or '(なし)'}")
        if not hit and peers:
            p("  → 一致0件。NAT やアドレス表記差が原因なので付記は抑制されます（判定には無影響）")
    p("\n" + "=" * 70)


def write_atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="aiwolf-nlp-server の状況を監視してファイルに出力し続ける")
    ap.add_argument("-c", "--config", default="default_en_5.yml",
                    help="サーバと同じ設定ファイル (既定: default_en_5.yml)")
    ap.add_argument("--once", action="store_true", help="1回だけ出力して終了する")
    ap.add_argument("--debug", action="store_true",
                    help="判定の内訳を標準出力に表示して終了する（接続状況が合わないとき用）")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"設定ファイルが見つかりません: {config_path}", file=sys.stderr)
        candidates = sorted(p.name for p in Path(".").glob("*.yml"))
        if candidates:
            print("候補: " + ", ".join(candidates), file=sys.stderr)
        return 1

    st = Settings(config_path)

    token = None
    if st.auth_enabled:
        secret = st.secret_key()
        if secret:
            token = make_receiver_token(secret)
        else:
            print("警告: 認証が有効ですが SECRET_KEY を見つけられませんでした。"
                  "実行中ゲームの情報は取得できません。", file=sys.stderr)

    api = Api(st.api_base, token)
    tail = LogTailer(st.server_log_path, st.initial_scan_bytes)
    opt = Optimizer(st.optimizer_path)

    if args.debug:
        tail.poll()
        opt.load()
        print_debug(st, api, opt, tail, established_peers(st.port))
        return 0

    outputs = {lang: st.output_path.with_suffix(suffix)
               for lang, suffix in OUTPUT_SUFFIX.items()}
    print(f"監視を開始します: {', '.join(str(p) for p in outputs.values())} へ "
          f"{st.interval:g} 秒ごとに出力", file=sys.stderr)
    print(f"  API      : {st.api_base}", file=sys.stderr)
    print(f"  optimizer: {st.optimizer_path}", file=sys.stderr)
    print(f"  log      : {st.server_log_path or '(未設定)'}", file=sys.stderr)

    while True:
        try:
            tail.poll()
            opt.load()
            peers = established_peers(st.port)
            for lang, out_path in outputs.items():
                write_atomic(out_path, build_report(st, api, opt, tail, peers, lang))
        except KeyboardInterrupt:
            print("\n監視を終了します", file=sys.stderr)
            return 0
        except Exception as e:  # 監視自体は落とさない
            try:
                for lang, out_path in outputs.items():
                    write_atomic(out_path,
                                 S[lang]["crash"].format(err=repr(e)) + "\n"
                                 f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}\n")
            except Exception:
                pass
            print(f"エラー: {e!r}", file=sys.stderr)
        if args.once:
            return 0
        try:
            time.sleep(st.interval)
        except KeyboardInterrupt:
            print("\n監視を終了します", file=sys.stderr)
            return 0


if __name__ == "__main__":
    sys.exit(main())
