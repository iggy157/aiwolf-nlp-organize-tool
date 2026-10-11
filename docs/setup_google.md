# Google 側の準備（フォーム生成のため、初回だけ）

`ops form create` は Apps Script を生成し、`clasp` で push して実行する。そのために kanolab.share のアカウントで次を 1 回行う。
所要は 15 分ほど。詰まりやすい点を先に書いておく。

## 1. Apps Script API を有効にする

https://script.google.com/home/usersettings で「Google Apps Script API」をオン。

## 2. clasp を入れる

```bash
npm install -g @google/clasp
```

ログインは 3 節の `--creds` 付きの 1 回だけ行う（`--creds` なしのログインは要らない。保存される鍵は 1 つで、後のログインで上書きされる）。

## 3. スクリプトの実行口（ウェブアプリ）を用意する

`ops form create` は、push したスクリプトを「ウェブアプリ」として呼び出して実行する（`clasp run` は環境によって
「server error occurred while reading from storage. Error code NOT_FOUND」で動かなかったため使わない）。
ウェブアプリの呼び出しには自前の OAuth クライアントのトークンが要るので、次を 1 回行う。

1. Google Cloud でプロジェクトを作り（例: aiwolf）、「OAuth 同意画面」を User Type「外部」、公開ステータス「テスト」のまま、
   テストユーザーに kanolab.share を追加。本番環境への切り替えは不要（ホームページ URL と承認済みドメインの所有確認を求められ、通らない）。
2. 「認証情報」→「OAuth クライアント ID」→ 種類「デスクトップ アプリ」→ JSON をダウンロードし `~/.ops/clasp_client_secret.json`（600）に置く。
3. `clasp login --creds ~/.ops/clasp_client_secret.json` でログインする（どのディレクトリで実行してもよい。鍵は `~/.clasprc.json` に保存される）。
   - VS Code の Remote-SSH で入っているなら、表示された URL を開いて「許可」を押すだけで終わる（VS Code が 8888 番を手元に転送する。自動で転送されないときは「ポート」タブで 8888 を足す）。
   - 転送が効かないときは `--no-localhost` を付けて実行する。許可したあとブラウザが `http://localhost:8888/?…&code=…` に飛んで「アクセスできません」になるので、その URL 全体をターミナルに貼る（アドレスバーに出ないときは F12 の Network で `localhost:8888` の行を見る）。
   - 同意画面が「テスト」なのでトークンは発行から 7 日で失効する。`ops form create` などは実行前に更新を試み、失効していればこのコマンドを案内して止まる。マシンごとに別の鍵なので、別のマシンでログインしても他のマシンの鍵は切れない。
4. 初回だけ、スクリプトをエディタで開いて何か 1 つ関数（`ping`）を実行し、権限を承認する。
   `https://script.google.com/d/<ops/config.yaml の form_script_id>/edit` → 関数 `ping` → 実行 → 承認。
5. `ops/form/gas` で `clasp deploy -d webapp` を実行し、出てきたデプロイ ID を `ops/config.yaml` の `form_webapp_deployment` に書く。
   以後 `ops form create` が push のたびに同じデプロイ ID へ新しい版を当てるので、手動のデプロイは要らない。

スクリプトプロジェクト（`form_script_id`）は 1 つを使い回す。大会が増えても 1〜5 をやり直す必要はない。

## 4. 回答シートを無人で読む（ops sync 用。後で）

同じ Cloud プロジェクトの「IAM と管理」→「サービス アカウント」→「作成」→「キー」タブ→「鍵を追加」→ JSON。
`~/.ops/service_account.json`（600）に置き、`~/.ops/secrets.env` に `GOOGLE_SERVICE_ACCOUNT_JSON=` でパスを書く。
`ops form create` はこの鍵のメールアドレスを回答シートの閲覧者に自動で加える。

## 置き場所のまとめ

| ファイル | 中身 | 権限 |
|---|---|---|
| `~/.clasprc.json` | clasp のトークン | 600 |
| `~/.ops/clasp_client_secret.json` | 自前 OAuth クライアント（任意） | 600 |
| `~/.ops/service_account.json` | サービスアカウントの鍵（任意） | 600 |
| `~/.ops/secrets.env` | Webhook、鍵のパスなど | 600 |
