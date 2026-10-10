# aiwolf-nlp-organizer-tool

人狼知能コンテスト（自然言語部門）の運営用の道具。公開してよいデータは
[aiwolf-nlp-contest-data](https://github.com/aiwolfdial/aiwolf-nlp-contest-data) に置き、このリポジトリはそれを読んで動く。
**このリポジトリは非公開。** 秘密情報（トークン、鍵）は git に入れず `~/.ops/` に置く（[docs/setup_google.md](docs/setup_google.md)）。

```
ops/                 入口。 python -m ops <コマンド>
  form/              参加登録フォームの生成（Apps Script を生成して clasp で push・ウェブアプリ経由で実行）
  sync/              回答シート → contests の teams.yaml、担当者へ Slack DM
  server/            大会サーバの設定一式（雛形は templates/、対戦組合せのスクリプトは scripts/）
  results/           決着ログ → results.yaml → サイト
contests/<大会 id>/
  form.yaml          その大会のフォーム定義（質問の並び、追加の質問）
  ops.yaml           非公開だが秘密ではないメタ情報（回答シートの ID など。道具が書き戻す）
docs/                運営向けの手順
```

## 使い方

```bash
uv sync                                        # 依存の導入（pyyaml のみ）
uv run python -m ops form create inlg_2027 --dry-run   # 生成される質問と Apps Script を見るだけ
uv run python -m ops form create inlg_2027             # フォームと回答シートを作り、URL を contests に書き戻す
uv run python -m ops form create inlg_2027 --test      # タイトルに [test] を付けて試し作成

uv run python -m ops sync inlg_2027 --once               # 回答シート → contests の teams.yaml、新規登録を担当者に DM
uv run python -m ops sync inlg_2027                      # 5 分おきに繰り返す（tmux で常駐させる）

uv run python -m ops server render inlg_2027 r1       # 回 r1 の設定一式を生成（トラック別 yml、接続確認用、teams.yml、Makefile）
uv run python -m ops server deploy inlg_2027 r1       # aiwolf サーバへ配置（公開ディレクトリとバイナリも用意）
uv run python -m ops server make inlg_2027 r1 check optimize-all    # サーバ側で make（起動は run-<track>、停止は stop-<track>）

uv run python -m ops results config inlg_2027         # サイトの集計設定を生成（ジャッジの出力パスは人が埋める）
uv run python -m ops results fetch inlg_2027          # 決着ログを手元へ
uv run python -m ops results build inlg_2027          # results.yaml を生成（サイトの build_contest_yaml.py）
uv run python -m ops results site inlg_2027           # サイト側で submodule を進めてコミット
```

工程ごとの自動・手動の線引きと未決事項は [docs/plan.md](docs/plan.md)。

`contests/<id>/form.yaml` が無ければ、`ops form init <id> --from <前回>` が前回大会のものから作る。
初回の Google 側の準備は [docs/setup_google.md](docs/setup_google.md)。
