# プッシュ通知のセットアップ手順

コードは実装済み。通知が実際に届くようにするには、以下の 3 つが必要。

1. Supabase に SQL を適用する（`supabase/migrations/0004_push_notifications.sql`）
2. Android の場合、Firebase Cloud Messaging（FCM）の鍵を EAS に登録する
3. アプリを再ビルドして入れ直す

**2 と 3 は避けられない。** Android の通知は Google の FCM を通す仕組みなので、
その鍵をアプリに埋め込む必要があり、鍵を入れるにはビルドをやり直すしかない。

---

## 1. Supabase に SQL を適用

Supabase の SQL Editor に `supabase/migrations/0004_push_notifications.sql` の中身を
貼り付けて Run する。`Success. No rows returned` が出れば完了。

この SQL がやること:

- `pg_net` 拡張を有効化（Postgres から HTTP リクエストを送るため）
- `children.push_token` をクライアントから読めないよう列単位の権限に張り替え
- `set_my_push_token()` — 端末のトークンを保存する RPC
- `send_push_to_child()` — 1 人へ送る共通処理。おやすみ時間には送らない
- `notebooks` の順番が変わったら通知するトリガー
- `nudges`（かえして！）が入ったら通知するトリガー

### 注意: 列権限の張り替えについて

`children` のテーブル全体の SELECT 権限を外し、`push_token` 以外の列だけを許可する。
そのため **クライアント側で `select('*')` を使うと権限エラーになる**。
`src/api/index.ts` の `CHILD_COLUMNS` と `src/lib/session.tsx` で明示列を指定済み。
今後 `children` に列を追加したら、この 3 か所（SQL の grant、CHILD_COLUMNS、session.tsx）を
揃えて更新する必要がある。

---

## 2. Firebase Cloud Messaging の設定（Android）

### 2-1. Firebase プロジェクトを作る

1. https://console.firebase.google.com を開く
2. 「プロジェクトを追加」→ 名前は何でもよい（例: `kokan-note`）
3. Google アナリティクスは不要なのでオフでよい

### 2-2. Android アプリを登録する

1. プロジェクトのトップで Android のアイコンをクリック
2. **Android パッケージ名**に、`app.json` の `android.package` と同じ値を入れる

   ```
   app.kokannote.mvp
   ```

   ここが 1 文字でも違うと通知は届かない。

3. `google-services.json` をダウンロードする

### 2-3. `google-services.json` をプロジェクトに置く

ダウンロードしたファイルを、リポジトリのルート（`package.json` と同じ場所）に置く。

そして `app.json` の `android` に次を追加する。

```json
"android": {
  "googleServicesFile": "./google-services.json",
  ...
}
```

> `google-services.json` は `.gitignore` に入れて Git に上げない。
> 秘密鍵ではないが、プロジェクト固有の設定なので不要に共有しない。

### 2-4. FCM V1 の鍵を EAS に登録する

1. Firebase コンソールの **プロジェクトの設定** → **サービス アカウント**
2. 「新しい秘密鍵の生成」→ JSON ファイルがダウンロードされる
3. ターミナルで次を実行し、案内に従ってその JSON を選ぶ

   ```
   eas credentials
   ```

   `Android` → `production`（または該当プロファイル）→
   `Google Service Account` → `Manage your Google Service Account Key for Push Notifications (FCM V1)`
   → `Set up a Google Service Account Key for Push Notifications`

> ⚠️ この JSON は**本物の秘密鍵**。Git に上げない。人に渡さない。

---

## 3. 再ビルドして入れ直す

```
eas build --profile development --platform android
```

ビルドが終わったら、出てきたリンクからスマホに入れ直す。
**古いアプリを上書きインストールでよい。** データは Supabase 側にあるので消えない。

---

## 動作確認

1. アプリを開くと、初回だけ通知の許可を聞かれる → 許可する
2. 設定画面の「おしらせ」欄が「じゅんばんが きたら おしらせが とどくよ」になっているか確認
3. 2 人以上のグループで、片方がページを送る
4. 次の番の子の端末に「つぎは あなたの ばんだよ！」が届く

### 届かないときに見るところ

| 症状 | 確認すること |
|---|---|
| 許可のダイアログが出ない | 一度断ると OS が二度目を出さない。設定アプリ → アプリ → 通知 から許可する |
| 許可したのに届かない | `children.push_token` に値が入っているか（Supabase の Table Editor で確認）。空なら EAS の projectId が読めていない |
| トークンはあるが届かない | FCM の鍵が未登録か、パッケージ名の不一致。`eas credentials` で確認 |
| 夜だけ届かない | 仕様。おやすみ時間（既定 21〜6 時）は送らない |
| 送信自体が失敗している | Supabase の SQL Editor で `select * from net._http_response order by created desc limit 10;` を実行し、エラー内容を見る |

---

## iOS について

iOS でも通知は使えるが、Apple Developer Program（年 99 ドル）への登録が必要。
登録後は `eas credentials` で Push Notification Key を作れば、コード側の変更なしで動く。
