# 運営の自動化 — 現在地と相談ごと

「何を自動にし、何を人が決めるか」はこの表で決める。変更したいことがあればここに書き足す。

| 工程 | いまの形 | 人がやること | 状態 |
|---|---|---|---|
| 大会の定義 | `ops contest new`（1 枚の定義シート。行 = 項目、列 = 大会。横断のトラック・ルールは別タブ）→ `ops contest import` で `contest.yaml` | 自分の大会の列を埋める | 動作確認済み（INLG 2026・JSAI 2026 を往復させてサイトの全ページが一致） |
| 参加フォーム | `ops form create <id>`（Apps Script を生成・push・ウェブアプリ経由で実行） | 定番外の質問を `form.yaml` に足す／確認 | 動作確認済み（2 大会で試作） |
| 登録の取り込み | `ops sync <id>`（回答シート → 公開 `teams.yaml`、担当者へ DM） | Slack の招待を送る | 動作確認済み |
| サイトの大会ページ | `scripts/contest/new.py`（前回のページを複製）＋ショートコード＋ `check.py` | 文章を書く、TODO を埋める | 動作確認済み（2 大会を削除→再作成で検証） |
| 一覧の仕切り | 会期から自動、毎日 06:00 JST に再ビルド | なし | 実装済み・未デプロイ |
| サーバ設定 | `ops server render/deploy/make`（回ごとの yml・teams.yml・Makefile・対戦組合せ） | 起動・停止の判断（`make run-*` / `stop-*`） | 試験用ディレクトリで検証済み |
| 配信（勝率・指標） | `make live`（aiwolf-nlp-calculate-score の start_live.sh） | なし | 要: サーバに calculate-score を clone |
| 結果の集計 | `ops results config/fetch/build/site` | ジャッジを各リポジトリの README で回し、出力パスを設定に書く | 実装済み・実データで未検証 |
| LLM ジャッジ | 各リポジトリで手動（GPU が要る） | 実行 | 従来どおり |
| 人手評価 | 従来どおり（Apps Script でフォーム生成、集計シート） | 全部 | 未着手（ops form と同じ仕組みに乗せられる） |
| 表彰・賞状・配布 | 未着手 | — | 未着手（results.yaml から生成する想定） |
| 告知 | 未着手 | — | 未着手（Bot からチャンネルへ、文面は md） |

## 決めたこと

- データは `aiwolf-nlp-contest-data`（公開）に 1 か所。連絡先は書かない（回答シートが台帳）。
- 秘密は `~/.ops/`（git の外）。非公開だが秘密でないものは ops の `contests/<id>/ops.yaml`。
- サイトの本文は人が書く。事実（日程・フォーム・役職・試合数・会場・ルール値）はショートコードで contests から出す。
- 国内大会のページは直近の国際大会を元にし、国内固有の 3 点（言語・学会セッション・スポンサー）だけ戻す。
- 実行は全部コマンド。UI は作らない（必要になったら薄く乗せる）。

## 相談中・未決

- 役職の並び順の統一（サイト 4 ページで表記が変わる）を受け入れるか。
- contests / ops を GitHub に作るタイミングと、サイトの submodule URL の切り替え。
- 試作で作った `[test]` のフォーム 2 つ・シート 2 つ・`ops-probe` スクリプトの削除。
- `~/ops-test-inlg_2026-r2`（aiwolf サーバの試験用ディレクトリ）の削除。
- 賞状: 受賞者を results.yaml から読む形に書き換え、描画を SVG + ヘッドレス Chrome にするか。

## 初回だけ要る手作業（済んだものに ✔）

- ✔ Apps Script API 有効化、clasp login（自前クライアント）、スクリプトの初回認可、ウェブアプリのデプロイ
- ✔ サービスアカウントの鍵（`~/.ops/service_account.json`）
- ✔ Slack アプリ `aiwolf-ops`（Bot トークン）
- GitHub に contests / ops のリポジトリ作成
- aiwolf サーバに `aiwolf-nlp-calculate-score` を clone して `uv sync`
