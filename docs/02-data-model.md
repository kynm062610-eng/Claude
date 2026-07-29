# データモデルと RLS 設計

Supabase Postgres。マイグレーションは `supabase/migrations/` に置く。

---

## 1. テーブル

### `guardians` — 保護者

Supabase Auth の `auth.users` と 1:1。子どもは Auth ユーザーを持たず、保護者のセッションで動く。

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | `auth.users.id` を参照 |
| `email` | text | Auth 側にもあるが参照用に保持 |
| `consent_version` | text | 同意した文言のバージョン |
| `consented_at` | timestamptz | 同意日時 |
| `created_at` | timestamptz | |

### `children` — 子どもプロフィール

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `guardian_id` | uuid FK → guardians | |
| `nickname` | text | 20 文字以内。本名は入れない旨を UI で案内 |
| `avatar_key` | text | プリセットアバターのキー |
| `grade` | int | 1〜6。同意要否の判定と表示調整に使う |
| `watch_mode` | text | `off` / `notify_only` / `full`。**既定 `off`** |
| `furigana_enabled` | bool | 既定 true。true ならひらがな中心の表示、false なら漢字を含む表示（設定画面の「ひらがな / かんじ」ボタン。中学生・高校生の利用も想定） |
| `quiet_hours_start` | int | 既定 21（時） |
| `quiet_hours_end` | int | 既定 6（時） |
| `deleted_at` | timestamptz | 退会時の論理削除 |

### `groups` — グループ

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `name` | text | |
| `invite_code` | text UNIQUE | 6 文字。紛らわしい文字（0/O/1/I）を除いた英数 |
| `created_by_child_id` | uuid FK → children | |
| `max_members` | int | 既定 6 |
| `created_at` | timestamptz | |

### `memberships` — 参加

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `group_id` | uuid FK → groups | |
| `child_id` | uuid FK → children | |
| `turn_order` | int | 回覧順。グループ内で一意 |
| `joined_at` | timestamptz | |
| `left_at` | timestamptz | 退出時 |

UNIQUE (`group_id`, `child_id`)

### `notebooks` — ノート（1 冊）

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `group_id` | uuid FK → groups | |
| `title` | text | |
| `current_turn_child_id` | uuid FK → children | 今の番。null なら誰も書けない |
| `turn_started_at` | timestamptz | 「かえして！」の 3 日判定に使う |
| `is_closed` | bool | 書き終わったノート |
| `created_at` | timestamptz | |

### `pages` — ページ

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `notebook_id` | uuid FK → notebooks | |
| `author_child_id` | uuid FK → children | |
| `page_number` | int | ノート内連番 |
| `content` | jsonb | ストローク列・テキスト・スタンプ配置（後述） |
| `thumbnail_path` | text | Storage 上の PNG パス |
| `prompt_text` | text | お題を使った場合その文言 |
| `is_hidden` | bool | 通報対応で非表示にした場合 |
| `created_at` | timestamptz | |

UNIQUE (`notebook_id`, `page_number`)

### `reactions` — 絵文字リアクション

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `page_id` | uuid FK → pages | |
| `child_id` | uuid FK → children | |
| `emoji` | text | 許可リスト内の 1 文字のみ |

UNIQUE (`page_id`, `child_id`, `emoji`)

### `reports` — 通報

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `page_id` | uuid FK → pages | |
| `reporter_child_id` | uuid FK → children | |
| `reason` | text | `mean` / `scary` / `personal_info` / `other` |
| `status` | text | `open` / `resolved` / `dismissed` |
| `created_at` | timestamptz | |

### `blocks` — ブロック

| 列 | 型 | 備考 |
|---|---|---|
| `child_id` | uuid FK → children | ブロックした側 |
| `blocked_child_id` | uuid FK → children | された側 |

PK (`child_id`, `blocked_child_id`)

### `nudges` — 「かえして！」

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `notebook_id` | uuid FK → notebooks | |
| `from_child_id` | uuid FK → children | |
| `created_at` | timestamptz | 1 日 1 回の制限判定に使う |

### `guardian_events` — 保護者向け監査ログ

見まもりモードの変更・開示請求を記録し、子どもへの通知の根拠にする。

| 列 | 型 | 備考 |
|---|---|---|
| `id` | uuid PK | |
| `child_id` | uuid FK → children | |
| `event_type` | text | `watch_mode_changed` / `disclosure_requested` |
| `detail` | jsonb | 変更前後の値など |
| `notified_child_at` | timestamptz | 子どもへ通知した日時 |
| `created_at` | timestamptz | |

---

## 2. `pages.content` の形

ページはラスタ画像ではなく構造として保存する。あとから拡大表示・印刷用の高解像度書き出し・再編集ができるようにするため。

```jsonc
{
  "version": 1,
  "canvas": { "width": 1080, "height": 1440 },
  "background": "dots",          // 便箋の柄キー
  "elements": [
    {
      "type": "stroke",
      "color": "#3B82F6",
      "width": 8,
      "points": [[120, 340], [122, 344], ...]   // 正規化前のキャンバス座標
    },
    {
      "type": "text",
      "text": "きょうのきゅうしょく さいこうだった",
      "x": 100, "y": 900, "size": 32, "color": "#1F2937"
    },
    {
      "type": "stamp",
      "key": "star",
      "x": 800, "y": 200, "scale": 1.2, "rotation": 0.3
    }
  ]
}
```

座標系はキャンバス固定サイズ（1080×1440）で持ち、表示時に画面幅へスケールする。端末ごとの解像度差でレイアウトが崩れないようにするため。

---

## 3. RLS の方針

Supabase の RLS はすべてのテーブルで有効にする。**アプリのクエリを信用せず、DB 側で閉じる。**

判定の起点は「ログイン中の保護者が、その子どもプロフィールを持っているか」。

```sql
-- 補助関数：ログイン中の保護者が持つ子どもの id 一覧
create function public.my_child_ids() returns setof uuid ...
```

主なポリシー：

| テーブル | 読み取り | 書き込み |
|---|---|---|
| `children` | 自分の保護者配下のみ | 同左 |
| `groups` | 自分の子が参加しているグループのみ | 作成は自分の子として、更新は作成者のみ |
| `memberships` | 同じグループの参加者は互いに見える | 追加は自分の子のみ、退出も自分の子のみ |
| `notebooks` | 参加グループのもののみ | 更新は「現在の番の子」のみ（順番の受け渡し） |
| `pages` | 参加グループかつ `is_hidden = false`、かつブロックしていない相手 | **INSERT は `notebooks.current_turn_child_id` が自分の子のときだけ** |
| `reactions` | ページが読めるなら読める | 自分の子としてのみ |
| `reports` | 自分が出した通報のみ | 自分の子としてのみ |
| `guardian_events` | 保護者は自分の子の分を読める。子ども画面も同じ行を読む | 挿入はサーバ側（service role） |

### 特に効かせたいポリシー

**「自分の番のときだけ書ける」を DB で担保する。** ここをクライアント側の分岐だけで実装すると、改造クライアントで順番を無視して投稿できてしまう。

```sql
create policy "pages_insert_only_on_turn" on public.pages
for insert with check (
  author_child_id in (select public.my_child_ids())
  and exists (
    select 1 from public.notebooks n
    where n.id = notebook_id
      and n.current_turn_child_id = author_child_id
      and n.is_closed = false
  )
);
```

---

## 4. サーバ側処理（Edge Function / RPC）

クライアントに任せられない処理は Postgres 関数か Edge Function に置く。

| 処理 | 置き場所 | 理由 |
|---|---|---|
| ページ提出＋順番の受け渡し | RPC `submit_page` | ページ挿入と `current_turn_child_id` 更新を 1 トランザクションにする |
| 招待コードでの参加 | RPC `join_group_by_code` | コード照合と定員チェックを原子的に行う |
| 通報の登録と運営通知 | RPC `report_page` | 通報者の権限確認と保護者通知をまとめる |
| プッシュ通知の送信 | Edge Function | Expo Push トークンを扱う |
| 見まもりモードの変更 | RPC `set_watch_mode` | 変更を `guardian_events` に必ず残し、子どもへの通知を発火させる |

`set_watch_mode` を単なる UPDATE にしないのが重要。監査ログと子どもへの通知が漏れると、`01-safety-and-privacy.md` の透明性原則が崩れる。
