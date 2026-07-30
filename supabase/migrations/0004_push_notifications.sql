-- プッシュ通知。
--
-- 送信は Edge Function を使わず、Postgres のトリガーから pg_net で
-- Expo の Push API を直接叩く。理由:
--   * トークンをクライアントに配らずに済む（他の子が偽の通知を送れない）
--   * SQL Editor に貼るだけで導入できる。CLI や Docker を使わない
--   * 順番が変わったのと同じトランザクションで確実に発火する
--     （クライアントから送る方式だと、投稿直後にアプリが落ちると通知が飛ばない）

create extension if not exists pg_net;

-- ---------------------------------------------------------------------------
-- push_token を他の子から読めないようにする
--
-- children の SELECT ポリシーは「同じグループの子は互いを読める」ため、
-- そのままだと push_token も読めてしまう。トークンが漏れると偽の通知を
-- 送れてしまうので、列ごとの権限で閉じる。
-- RLS は列単位で制御できないため、テーブル権限を張り替える。
-- ---------------------------------------------------------------------------

revoke select on public.children from authenticated, anon;

grant select (
  id, guardian_id, auth_user_id, link_code, nickname, avatar_key, grade,
  watch_mode, furigana_enabled, quiet_hours_start, quiet_hours_end,
  deleted_at, created_at
) on public.children to authenticated;

-- ---------------------------------------------------------------------------
-- 端末のトークンを保存する
-- ---------------------------------------------------------------------------

create or replace function public.set_my_push_token(p_token text)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  update public.children
     set push_token = p_token
   where id = v_child_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- 送信の共通処理
-- ---------------------------------------------------------------------------

/**
 * 1 人の子どもへ通知を送る。
 * おやすみ時間には送らない（夜に通知で起こさないため）。
 * トークンが未登録なら何もしない。
 */
create or replace function public.send_push_to_child(
  p_child_id uuid,
  p_body_kana text,
  p_body_kanji text,
  p_data jsonb default '{}'::jsonb
)
returns void
language plpgsql volatile security definer set search_path = public, net
as $$
declare
  v_token   text;
  v_kana    boolean;
  v_qs      int;
  v_qe      int;
  v_hour    int;
  v_body    text;
begin
  select push_token, furigana_enabled, quiet_hours_start, quiet_hours_end
    into v_token, v_kana, v_qs, v_qe
    from public.children
   where id = p_child_id and deleted_at is null;

  if v_token is null or v_token = '' then
    return;
  end if;

  -- おやすみ時間の判定。日本時間で見る。
  v_hour := extract(hour from (now() at time zone 'Asia/Tokyo'))::int;
  if (v_qs < v_qe and v_hour >= v_qs and v_hour < v_qe)
     or (v_qs > v_qe and (v_hour >= v_qs or v_hour < v_qe)) then
    return;
  end if;

  v_body := case when coalesce(v_kana, true) then p_body_kana else p_body_kanji end;

  perform net.http_post(
    url     := 'https://exp.host/--/api/v2/push/send',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Accept', 'application/json'
    ),
    body    := jsonb_build_object(
      'to', v_token,
      'title', 'こうかんノート',
      'body', v_body,
      'sound', 'default',
      'channelId', 'default',
      'priority', 'default',
      'data', p_data
    )
  );
end;
$$;

-- ---------------------------------------------------------------------------
-- 順番が回ってきたら通知する
-- ---------------------------------------------------------------------------

create or replace function public.notify_turn_change()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  -- 順番が実際に変わったときだけ。null（誰も書けない状態）へは送らない。
  if new.current_turn_child_id is null
     or new.current_turn_child_id is not distinct from old.current_turn_child_id
     or new.is_closed then
    return new;
  end if;

  perform public.send_push_to_child(
    new.current_turn_child_id,
    'つぎは あなたの ばんだよ！',
    '次はあなたの番だよ！',
    jsonb_build_object('notebookId', new.id, 'kind', 'your_turn')
  );

  return new;
end;
$$;

drop trigger if exists notebooks_notify_turn_change on public.notebooks;

create trigger notebooks_notify_turn_change
  after update of current_turn_child_id on public.notebooks
  for each row
  execute function public.notify_turn_change();

-- ---------------------------------------------------------------------------
-- 「かえして！」が届いたら通知する
-- ---------------------------------------------------------------------------

create or replace function public.notify_nudge()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare
  v_target uuid;
begin
  select current_turn_child_id into v_target
    from public.notebooks
   where id = new.notebook_id and is_closed = false;

  if v_target is null then
    return new;
  end if;

  perform public.send_push_to_child(
    v_target,
    'ノートが まってるよ！',
    'ノートが待ってるよ！',
    jsonb_build_object('notebookId', new.notebook_id, 'kind', 'nudge')
  );

  return new;
end;
$$;

drop trigger if exists nudges_notify on public.nudges;

create trigger nudges_notify
  after insert on public.nudges
  for each row
  execute function public.notify_nudge();
