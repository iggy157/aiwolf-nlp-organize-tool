# aiwolf-nlp-organizer-tool

人狼知能コンテスト（自然言語部門）の運営用の道具。公開してよいデータは
[aiwolf-nlp-contest-data](https://github.com/iggy157/aiwolf-nlp-contest-data) に置き、このリポジトリはそれを読んで動く。
**このリポジトリは非公開。** 秘密情報（トークン、鍵）は git に入れず `~/.ops/` に置く（[docs/setup_google.md](docs/setup_google.md)）。

```
ops/                 入口。 python -m ops <コマンド>
  contest/           大会定義シートの形（行・型・色）と、シートに付ける「大会データを更新」ボタン
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
uv run python -m ops contest url                 # 大会定義シートの URL
uv run python -m ops contest import --push       # シート → contest.yaml を手元で（ボタンと同じ処理。差分を見せて確認）
uv run python -m ops contest layout              # シートの形を作り直す（fields.yaml の項目を変えたとき。値は残る）
uv run python -m ops contest button              # シートに「大会データ」メニューを付ける／更新する

uv run python -m ops form create inlg_2027 --dry-run   # 生成される質問と Apps Script を見るだけ
uv run python -m ops form create inlg_2027             # フォームと回答シートを作り、URL を大会定義シートに書く
uv run python -m ops form create inlg_2027 --test      # タイトルに [test] を付けて試し作成

uv run python -m ops sync inlg_2027 --once               # 回答シート → contest-data の teams.yaml（push まで）、新規登録を担当者に DM
uv run python -m ops sync inlg_2027                      # 5 分おきに繰り返す（tmux で常駐させる）

uv run python -m ops server render inlg_2027 r1       # 回 r1 の設定一式を生成（トラック別 yml、接続確認用、teams.yml、Makefile）
uv run python -m ops server deploy inlg_2027 r1       # aiwolf サーバへ配置（公開ディレクトリとバイナリも用意）
uv run python -m ops server make inlg_2027 r1 check optimize-all    # サーバ側で make（起動は run-<track>、停止は stop-<track>）

uv run python -m ops results config inlg_2027         # サイトの集計設定を生成（ジャッジの出力パスは人が埋める）
uv run python -m ops results fetch inlg_2027          # 決着ログを手元へ
uv run python -m ops results build inlg_2027          # results.yaml を生成（サイトの build_contest_yaml.py）
uv run python -m ops results site inlg_2027           # サイト側で submodule を進めてコミット
```

## 大会の始め方

1. 大会定義シート（`ops contest url`）の「大会」タブで、空いている列の 1 行目に大会 id（例: `aiwolfdial2026_winterjp`）を書く。
   型（ドロップダウン・チェックボックス・必須の赤）は最初から敷いてあるので、値を埋めるだけ。英語が要る大会は「サイトの言語」を英語か両方にし、「大会_en」タブの同じ列を埋める。
2. メニュー「大会データ → 大会データを更新」を押す。contest-data の GitHub Actions がシートを読んで `contests/<id>/contest.yaml` を書き、push する。結果（変更・未記入の警告）はダイアログに出る。
3. `ops form init <id> --from <前回>` → `ops form create <id>`。フォームの URL がシートに入るので、もう一度「大会データを更新」を押す。
4. サイト（aiwolf-nlp）で取り込み・ページ生成・確認・push（サイトの運営マニュアル「ウェブサイトの編集」）。

以後はシートを直して「大会データを更新」→ サイトで取り込み、の繰り返し。contest.yaml は手で編集しない（次の更新で上書きされる）。
contest-data は GitHub 上で更新されるので、このリポジトリのコマンド（form / sync / layout / import）は最初に contest-data を `git pull` する。

### 更新ボタンの準備（押す人ごとに 1 回）

GitHub で fine-grained personal access token を作る（Settings → Developer settings → Fine-grained tokens）。
対象リポジトリは contest-data だけ、権限は **Actions: Read and write** だけ。シートのメニュー「大会データ → GitHub のトークンを設定」に貼る（本人専用の領域に保存され、他の人には見えない）。
初回の実行時に Google の承認画面が出るので許可する。

工程ごとの自動・手動の線引きと未決事項は [docs/plan.md](docs/plan.md)。

`contests/<id>/form.yaml` が無ければ、`ops form init <id> --from <前回>` が前回大会のものから作る。
初回の Google 側の準備は [docs/setup_google.md](docs/setup_google.md)。
