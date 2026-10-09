# Google 側の準備（フォーム生成のため、初回だけ）

`ops form create` は Apps Script を生成し、`clasp` で push して実行する。そのために kanolab.share のアカウントで次を 1 回行う。
所要は 15 分ほど。詰まりやすい点を先に書いておく。

## 1. Apps Script API を有効にする

https://script.google.com/home/usersettings で「Google Apps Script API」をオン。

## 2. clasp を入れてログインする

```bash
npm install -g @google/clasp
clasp login --no-localhost
```

- 表示された URL をブラウザで開き、kanolab.share で承認する。
- **承認後、ブラウザは `http://localhost:8888/?state=…&code=…` へ飛んで「アクセスできません」になる。これで正常。**
  SSH 先（freccia など）で clasp を動かしている場合、この `localhost` は手元の PC を指すので clasp には届かない。
  ブラウザのアドレスバーの URL 全体をコピーして、ターミナルの `paste it here:` に貼る。
  同意画面が「固まった」ように見えるのも、この転送待ちである（F12 の Network に `localhost:8888` が pending で出る）。
- 代わりに VS Code のポート転送（8888）か `ssh -L 8888:localhost:8888 freccia` を張っておけば、`--no-localhost` 無しで自動的に完了する。
- 成功すると `~/.clasprc.json` ができる（権限 600 にしておく）。これは Google 製の審査済みクライアントでのログインなので、トークンは 7 日で切れない。

これで `clasp push`（コードの送信）はできる。実行まで行うには 3 節が要る。

## 3. スクリプトの実行口（ウェブアプリ）を用意する

`ops form create` は、push したスクリプトを「ウェブアプリ」として呼び出して実行する（`clasp run` は環境によって
「server error occurred while reading from storage. Error code NOT_FOUND」で動かなかったため使わない）。
ウェブアプリの呼び出しには自前の OAuth クライアントのトークンが要るので、次を 1 回行う。

1. Google Cloud でプロジェクトを作り（例: aiwolf）、「OAuth 同意画面」を User Type「外部」、公開ステータス「テスト」のまま、
   テストユーザーに kanolab.share を追加。本番環境への切り替えは不要（ホームページ URL と承認済みドメインの所有確認を求められ、通らない）。
2. 「認証情報」→「OAuth クライアント ID」→ 種類「デスクトップ アプリ」→ JSON をダウンロードし `~/.ops/clasp_client_secret.json`（600）に置く。
3. `clasp login --no-localhost --creds ~/.ops/clasp_client_secret.json`（2 節と同じ要領で URL を貼る）。
   同意画面が「テスト」なのでトークンは 7 日で失効する。`ops form create` は実行前に更新を試み、失効していればこのコマンドを案内して止まる。
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
