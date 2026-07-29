-- こうかんノート MVP スキーマ
--
-- 設計の要点:
--   * 子どもは「保護者のセッションのぶら下がり」ではなく、独立した匿名 auth ユーザーを持つ。
--     こうしないと保護者のセッションで子どものデータが常に読めてしまい、
--     見まもりモード off が UI 上の見せかけになる。RLS で本当に閉じるために分ける。
--   * 「自分の番のときだけ書ける」は DB 側で担保する（クライアントの分岐に頼らない）。
--   * 見まもりモードの変更は必ず監査ログに残す。UPDATE を直接許可しない。

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- テーブル
-- ---------------------------------------------------------------------------

create table public.guardians (
  id                uuid primary key references auth.users(id) on delete cascade,
  email             text,
  consent_version   text        not null,
  consented_at      timestamptz not null default now(),
  created_at        timestamptz not null default now()
);

create table public.children (
  id                uuid primary key default gen_random_uuid(),
  guardian_id       uuid        not null references public.guardians(id) on delete cascade,
  -- 子ども端末の匿名 auth ユーザー。claim_child_profile() で紐づくまで null
  auth_user_id      uuid        unique references auth.users(id) on delete set null,
  link_code         text        unique,
  nickname          text        not null check (char_length(nickname) between 1 and 20),
  avatar_key        text        not null default 'cat',
  grade             int         not null check (grade between 1 and 6),
  watch_mode        text        not null default 'off'
                                check (watch_mode in ('off', 'notify_only', 'full')),
  furigana_enabled  boolean     not null default true,
  quiet_hours_start int         not null default 21 check (quiet_hours_start between 0 and 23),
  quiet_hours_end   int         not null default 6  check (quiet_hours_end between 0 and 23),
  push_token        text,
  deleted_at        timestamptz,
  created_at        timestamptz not null default now()
);

create index children_guardian_idx on public.children(guardian_id);

create table public.groups (
  id                  uuid primary key default gen_random_uuid(),
  name                text        not null check (char_length(name) between 1 and 30),
  invite_code         text        not null unique,
  created_by_child_id uuid        not null references public.children(id) on delete cascade,
  max_members         int         not null default 6 check (max_members between 2 and 6),
  created_at          timestamptz not null default now()
);

create table public.memberships (
  id          uuid primary key default gen_random_uuid(),
  group_id    uuid        not null references public.groups(id) on delete cascade,
  child_id    uuid        not null references public.children(id) on delete cascade,
  turn_order  int         not null,
  joined_at   timestamptz not null default now(),
  left_at     timestamptz,
  unique (group_id, child_id)
);

create index memberships_child_idx on public.memberships(child_id) where left_at is null;

create table public.notebooks (
  id                     uuid primary key default gen_random_uuid(),
  group_id               uuid        not null references public.groups(id) on delete cascade,
  title                  text        not null default 'あたらしいノート',
  current_turn_child_id  uuid        references public.children(id) on delete set null,
  turn_started_at        timestamptz not null default now(),
  is_closed              boolean     not null default false,
  created_at             timestamptz not null default now()
);

create index notebooks_group_idx on public.notebooks(group_id);

create table public.pages (
  id               uuid primary key default gen_random_uuid(),
  notebook_id      uuid        not null references public.notebooks(id) on delete cascade,
  author_child_id  uuid        not null references public.children(id) on delete cascade,
  page_number      int         not null,
  content          jsonb       not null,
  thumbnail_path   text,
  prompt_text      text,
  is_hidden        boolean     not null default false,
  created_at       timestamptz not null default now(),
  unique (notebook_id, page_number)
);

create index pages_notebook_idx on public.pages(notebook_id, page_number);

create table public.reactions (
  id        uuid primary key default gen_random_uuid(),
  page_id   uuid not null references public.pages(id) on delete cascade,
  child_id  uuid not null references public.children(id) on delete cascade,
  emoji     text not null,
  created_at timestamptz not null default now(),
  unique (page_id, child_id, emoji)
);

create table public.reports (
  id                 uuid primary key default gen_random_uuid(),
  page_id            uuid not null references public.pages(id) on delete cascade,
  reporter_child_id  uuid not null references public.children(id) on delete cascade,
  reason             text not null check (reason in ('mean', 'scary', 'personal_info', 'other')),
  status             text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  created_at         timestamptz not null default now()
);

create table public.blocks (
  child_id          uuid not null references public.children(id) on delete cascade,
  blocked_child_id  uuid not null references public.children(id) on delete cascade,
  created_at        timestamptz not null default now(),
  primary key (child_id, blocked_child_id)
);

create table public.nudges (
  id            uuid primary key default gen_random_uuid(),
  notebook_id   uuid not null references public.notebooks(id) on delete cascade,
  from_child_id uuid not null references public.children(id) on delete cascade,
  created_at    timestamptz not null default now()
);

-- 安全フロア。見まもりモードの値に関係なく保護者へ届く通知の元になる。
-- 本文は保存しない（カテゴリのみ）。「何が起きたか」は伝えるが「何を書いたか」は渡さない。
create table public.safety_alerts (
  id         uuid primary key default gen_random_uuid(),
  child_id   uuid not null references public.children(id) on delete cascade,
  category   text not null check (category in ('violence', 'self_harm', 'exclusion', 'insult', 'personal_info')),
  created_at timestamptz not null default now()
);

create index safety_alerts_child_idx on public.safety_alerts(child_id, created_at desc);

-- 見まもりモードの変更・開示請求の監査ログ。子どもへの通知の根拠になる。
create table public.guardian_events (
  id                uuid primary key default gen_random_uuid(),
  child_id          uuid not null references public.children(id) on delete cascade,
  event_type        text not null check (event_type in ('watch_mode_changed', 'disclosure_requested')),
  detail            jsonb not null default '{}'::jsonb,
  acknowledged_at   timestamptz,
  created_at        timestamptz not null default now()
);

create index guardian_events_child_idx on public.guardian_events(child_id, created_at desc);

-- ---------------------------------------------------------------------------
-- 補助関数
-- ---------------------------------------------------------------------------

-- ログイン中の「子ども」セッションに対応する children.id
create or replace function public.current_child_id()
returns uuid
language sql stable security definer set search_path = public
as $$
  select c.id from public.children c
  where c.auth_user_id = auth.uid() and c.deleted_at is null
  limit 1;
$$;

-- ログイン中の「保護者」セッションが持つ子どもの id 一覧
create or replace function public.my_child_ids()
returns setof uuid
language sql stable security definer set search_path = public
as $$
  select c.id from public.children c
  where c.guardian_id = auth.uid() and c.deleted_at is null;
$$;

-- ログイン中の子どもが参加しているグループ
create or replace function public.my_group_ids()
returns setof uuid
language sql stable security definer set search_path = public
as $$
  select m.group_id from public.memberships m
  where m.child_id = public.current_child_id() and m.left_at is null;
$$;

-- 保護者が「中身まで」見てよい子どもか（watch_mode = 'full' のときだけ）
create or replace function public.guardian_can_read_content(p_child_id uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.children c
    where c.id = p_child_id
      and c.guardian_id = auth.uid()
      and c.watch_mode = 'full'
  );
$$;

-- 紛らわしい文字（0/O/1/I）を除いたコード生成
create or replace function public.generate_code(p_len int)
returns text
language plpgsql volatile
as $$
declare
  alphabet text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  result   text := '';
  i        int;
begin
  for i in 1..p_len loop
    result := result || substr(alphabet, floor(random() * length(alphabet))::int + 1, 1);
  end loop;
  return result;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table public.guardians       enable row level security;
alter table public.children        enable row level security;
alter table public.groups          enable row level security;
alter table public.memberships     enable row level security;
alter table public.notebooks       enable row level security;
alter table public.pages           enable row level security;
alter table public.reactions       enable row level security;
alter table public.reports         enable row level security;
alter table public.blocks          enable row level security;
alter table public.nudges          enable row level security;
alter table public.guardian_events enable row level security;
alter table public.safety_alerts   enable row level security;

-- guardians: 自分の行のみ
create policy guardians_select on public.guardians
  for select using (id = auth.uid());
create policy guardians_insert on public.guardians
  for insert with check (id = auth.uid());
create policy guardians_update on public.guardians
  for update using (id = auth.uid());

-- children:
--   保護者は自分の子のプロフィール行を読める（プロフィール自体は見まもりモードの対象外。
--   ニックネーム・学年は保護者が登録したもので、子どもが書いた内容ではないため）
--   子ども本人は自分の行を読める
--   同じグループの子は、互いのニックネームとアバターを読む必要がある
create policy children_select on public.children
  for select using (
    guardian_id = auth.uid()
    or auth_user_id = auth.uid()
    or exists (
      select 1 from public.memberships m
      where m.child_id = children.id
        and m.left_at is null
        and m.group_id in (select public.my_group_ids())
    )
  );

create policy children_insert on public.children
  for insert with check (guardian_id = auth.uid());

-- 直接 UPDATE できるのは子ども本人の表示設定のみ。
-- watch_mode の変更は set_watch_mode() 経由に限定する（監査ログを必ず残すため）。
create policy children_update_self on public.children
  for update using (auth_user_id = auth.uid())
  with check (auth_user_id = auth.uid());

create policy children_update_guardian on public.children
  for update using (guardian_id = auth.uid())
  with check (guardian_id = auth.uid());

-- groups: 参加中の子ども、およびその保護者（full のときのみ）
create policy groups_select on public.groups
  for select using (
    id in (select public.my_group_ids())
    or exists (
      select 1 from public.memberships m
      where m.group_id = groups.id
        and m.left_at is null
        and public.guardian_can_read_content(m.child_id)
    )
  );

-- memberships: 同じグループの参加者は互いに見える
create policy memberships_select on public.memberships
  for select using (
    group_id in (select public.my_group_ids())
    or public.guardian_can_read_content(child_id)
  );

create policy memberships_delete on public.memberships
  for delete using (child_id = public.current_child_id());

-- notebooks
create policy notebooks_select on public.notebooks
  for select using (
    group_id in (select public.my_group_ids())
    or exists (
      select 1 from public.memberships m
      where m.group_id = notebooks.group_id
        and m.left_at is null
        and public.guardian_can_read_content(m.child_id)
    )
  );

create policy notebooks_insert on public.notebooks
  for insert with check (group_id in (select public.my_group_ids()));

-- pages
--   閲覧: 同じグループの子ども（ブロック相手を除く）、または watch_mode='full' の保護者
create policy pages_select on public.pages
  for select using (
    is_hidden = false
    and (
      (
        exists (
          select 1 from public.notebooks n
          where n.id = pages.notebook_id
            and n.group_id in (select public.my_group_ids())
        )
        and not exists (
          select 1 from public.blocks b
          where b.child_id = public.current_child_id()
            and b.blocked_child_id = pages.author_child_id
        )
      )
      or exists (
        select 1
        from public.notebooks n
        join public.memberships m on m.group_id = n.group_id and m.left_at is null
        where n.id = pages.notebook_id
          and public.guardian_can_read_content(m.child_id)
      )
    )
  );

--   投稿: 自分の番のときだけ。ここをクライアント任せにしない。
create policy pages_insert_only_on_turn on public.pages
  for insert with check (
    author_child_id = public.current_child_id()
    and exists (
      select 1 from public.notebooks n
      where n.id = notebook_id
        and n.current_turn_child_id = author_child_id
        and n.is_closed = false
    )
  );

-- reactions
create policy reactions_select on public.reactions
  for select using (
    exists (select 1 from public.pages p where p.id = reactions.page_id)
  );

create policy reactions_insert on public.reactions
  for insert with check (child_id = public.current_child_id());

create policy reactions_delete on public.reactions
  for delete using (child_id = public.current_child_id());

-- reports: 自分が出したものだけ見える
create policy reports_select on public.reports
  for select using (reporter_child_id = public.current_child_id());

create policy reports_insert on public.reports
  for insert with check (reporter_child_id = public.current_child_id());

-- blocks
create policy blocks_all on public.blocks
  for all using (child_id = public.current_child_id())
  with check (child_id = public.current_child_id());

-- nudges
create policy nudges_select on public.nudges
  for select using (
    exists (
      select 1 from public.notebooks n
      where n.id = nudges.notebook_id
        and n.group_id in (select public.my_group_ids())
    )
  );

create policy nudges_insert on public.nudges
  for insert with check (from_child_id = public.current_child_id());

-- guardian_events: 保護者も子どもも読める（子どもに隠さないことが本設計の要）
create policy guardian_events_select on public.guardian_events
  for select using (
    child_id = public.current_child_id()
    or child_id in (select public.my_child_ids())
  );

-- 子ども本人が「確認した」を記録できる
create policy guardian_events_update on public.guardian_events
  for update using (child_id = public.current_child_id())
  with check (child_id = public.current_child_id());

-- safety_alerts: 保護者は見まもりモードに関係なく読める（安全フロアのため）。
-- 子ども本人も自分の分を読める（本人に隠さない）。
create policy safety_alerts_select on public.safety_alerts
  for select using (
    child_id = public.current_child_id()
    or child_id in (select public.my_child_ids())
  );

-- ---------------------------------------------------------------------------
-- RPC
-- ---------------------------------------------------------------------------

-- 子ども端末が匿名サインイン後、保護者が発行したリンクコードでプロフィールを受け取る
create or replace function public.claim_child_profile(p_link_code text)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid;
begin
  update public.children
     set auth_user_id = auth.uid(),
         link_code    = null
   where link_code = upper(p_link_code)
     and auth_user_id is null
     and deleted_at is null
  returning id into v_child_id;

  if v_child_id is null then
    raise exception 'link_code_invalid';
  end if;

  return v_child_id;
end;
$$;

-- 保護者が子どもプロフィールを作る。リンクコードを採番して返す。
-- 子どもはこのコードを自分の端末で入力してプロフィールを受け取る。
create or replace function public.create_child(
  p_nickname   text,
  p_avatar_key text,
  p_grade      int
)
returns table (child_id uuid, link_code text)
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_code     text;
  v_child_id uuid;
begin
  if not exists (select 1 from public.guardians where id = auth.uid()) then
    raise exception 'guardian_not_registered';
  end if;

  loop
    v_code := public.generate_code(8);
    exit when not exists (select 1 from public.children c where c.link_code = v_code);
  end loop;

  insert into public.children (guardian_id, nickname, avatar_key, grade, link_code)
  values (auth.uid(), p_nickname, p_avatar_key, p_grade, v_code)
  returning id into v_child_id;

  return query select v_child_id, v_code;
end;
$$;

-- グループ作成。作成者を turn_order = 0 で参加させ、最初のノートを 1 冊作る。
create or replace function public.create_group(p_name text)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
  v_group_id uuid;
  v_code     text;
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  loop
    v_code := public.generate_code(6);
    exit when not exists (select 1 from public.groups where invite_code = v_code);
  end loop;

  insert into public.groups (name, invite_code, created_by_child_id)
  values (p_name, v_code, v_child_id)
  returning id into v_group_id;

  insert into public.memberships (group_id, child_id, turn_order)
  values (v_group_id, v_child_id, 0);

  insert into public.notebooks (group_id, current_turn_child_id)
  values (v_group_id, v_child_id);

  return v_group_id;
end;
$$;

-- 招待コードで参加。定員チェックと turn_order 採番を原子的に行う。
create or replace function public.join_group_by_code(p_code text)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
  v_group    public.groups%rowtype;
  v_count    int;
  v_next     int;
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  select * into v_group from public.groups
   where invite_code = upper(p_code)
   for update;

  if v_group.id is null then
    raise exception 'invite_code_invalid';
  end if;

  if exists (
    select 1 from public.memberships
     where group_id = v_group.id and child_id = v_child_id and left_at is null
  ) then
    return v_group.id;
  end if;

  select count(*) into v_count from public.memberships
   where group_id = v_group.id and left_at is null;

  if v_count >= v_group.max_members then
    raise exception 'group_full';
  end if;

  select coalesce(max(turn_order), -1) + 1 into v_next
    from public.memberships where group_id = v_group.id;

  insert into public.memberships (group_id, child_id, turn_order)
  values (v_group.id, v_child_id, v_next)
  on conflict (group_id, child_id)
  do update set left_at = null, joined_at = now();

  return v_group.id;
end;
$$;

-- ページ提出と順番の受け渡しを 1 トランザクションで行う。
create or replace function public.submit_page(
  p_notebook_id    uuid,
  p_content        jsonb,
  p_thumbnail_path text default null,
  p_prompt_text    text default null
)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
  v_notebook public.notebooks%rowtype;
  v_page_no  int;
  v_page_id  uuid;
  v_next     uuid;
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  select * into v_notebook from public.notebooks
   where id = p_notebook_id for update;

  if v_notebook.id is null then
    raise exception 'notebook_not_found';
  end if;
  if v_notebook.is_closed then
    raise exception 'notebook_closed';
  end if;
  if v_notebook.current_turn_child_id is distinct from v_child_id then
    raise exception 'not_your_turn';
  end if;

  select coalesce(max(page_number), 0) + 1 into v_page_no
    from public.pages where notebook_id = p_notebook_id;

  insert into public.pages (notebook_id, author_child_id, page_number, content, thumbnail_path, prompt_text)
  values (p_notebook_id, v_child_id, v_page_no, p_content, p_thumbnail_path, p_prompt_text)
  returning id into v_page_id;

  v_next := public.next_turn_child(v_notebook.group_id, v_child_id);

  update public.notebooks
     set current_turn_child_id = v_next,
         turn_started_at       = now()
   where id = p_notebook_id;

  return v_page_id;
end;
$$;

-- 順番の次の子を返す。参加者が 1 人だけならその子のまま。
create or replace function public.next_turn_child(p_group_id uuid, p_current_child_id uuid)
returns uuid
language sql stable security definer set search_path = public
as $$
  with ordered as (
    select child_id, turn_order,
           row_number() over (order by turn_order) as rn,
           count(*) over () as total
      from public.memberships
     where group_id = p_group_id and left_at is null
  ),
  cur as (select rn, total from ordered where child_id = p_current_child_id)
  select o.child_id
    from ordered o, cur
   where o.rn = (cur.rn % cur.total) + 1;
$$;

-- 「パスする」。ページを書かずに順番だけ次へ送る。記録は残さない。
create or replace function public.pass_turn(p_notebook_id uuid)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
  v_notebook public.notebooks%rowtype;
begin
  select * into v_notebook from public.notebooks where id = p_notebook_id for update;

  if v_notebook.current_turn_child_id is distinct from v_child_id then
    raise exception 'not_your_turn';
  end if;

  update public.notebooks
     set current_turn_child_id = public.next_turn_child(v_notebook.group_id, v_child_id),
         turn_started_at       = now()
   where id = p_notebook_id;
end;
$$;

-- 「かえして！」。1 人 1 ノートにつき 1 日 1 回まで。
create or replace function public.send_nudge(p_notebook_id uuid)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
begin
  if exists (
    select 1 from public.nudges
     where notebook_id = p_notebook_id
       and from_child_id = v_child_id
       and created_at > now() - interval '1 day'
  ) then
    raise exception 'nudge_rate_limited';
  end if;

  insert into public.nudges (notebook_id, from_child_id)
  values (p_notebook_id, v_child_id);
end;
$$;

-- 通報。見まもりモードの値に関係なく作動する「安全フロア」。
create or replace function public.report_page(p_page_id uuid, p_reason text)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id  uuid := public.current_child_id();
  v_report_id uuid;
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  insert into public.reports (page_id, reporter_child_id, reason)
  values (p_page_id, v_child_id, p_reason)
  returning id into v_report_id;

  -- 通報が 2 件集まった時点で自動的に非表示にし、運営の確認を待つ
  update public.pages p
     set is_hidden = true
   where p.id = p_page_id
     and (select count(*) from public.reports r where r.page_id = p_page_id) >= 2;

  return v_report_id;
end;
$$;

-- 安全フロアの発火。見まもりモードの値に関係なく記録される。
-- 本文は受け取らない。カテゴリだけを残し、保護者には「何が起きたか」だけを伝える。
create or replace function public.raise_safety_alert(p_category text)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  insert into public.safety_alerts (child_id, category)
  values (v_child_id, p_category);
end;
$$;

-- 見まもりモードの変更。監査ログを必ず残すため、直接 UPDATE ではなくこの関数を通す。
create or replace function public.set_watch_mode(p_child_id uuid, p_mode text)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_old text;
begin
  select watch_mode into v_old from public.children
   where id = p_child_id and guardian_id = auth.uid();

  if v_old is null then
    raise exception 'child_not_found';
  end if;
  if p_mode not in ('off', 'notify_only', 'full') then
    raise exception 'invalid_mode';
  end if;
  if v_old = p_mode then
    return;
  end if;

  update public.children set watch_mode = p_mode where id = p_child_id;

  insert into public.guardian_events (child_id, event_type, detail)
  values (p_child_id, 'watch_mode_changed',
          jsonb_build_object('from', v_old, 'to', p_mode));
end;
$$;

-- 開示請求。閲覧モードが off でも保護者は行使できる（法定の権利のため）。
-- ただし実行したことは必ず子どもに伝わる。
create or replace function public.request_disclosure(p_child_id uuid)
returns uuid
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_event_id uuid;
begin
  if not exists (
    select 1 from public.children where id = p_child_id and guardian_id = auth.uid()
  ) then
    raise exception 'child_not_found';
  end if;

  insert into public.guardian_events (child_id, event_type, detail)
  values (p_child_id, 'disclosure_requested', jsonb_build_object('requested_at', now()))
  returning id into v_event_id;

  return v_event_id;
end;
$$;

-- notify_only 用。本文は返さず「いつ書いたか」だけを返す。
create or replace function public.get_child_activity(p_child_id uuid)
returns table (written_at timestamptz, notebook_title text)
language plpgsql stable security definer set search_path = public
as $$
declare
  v_mode text;
begin
  select watch_mode into v_mode from public.children
   where id = p_child_id and guardian_id = auth.uid();

  if v_mode is null then
    raise exception 'child_not_found';
  end if;
  if v_mode = 'off' then
    raise exception 'watch_mode_off';
  end if;

  return query
    select p.created_at, n.title
      from public.pages p
      join public.notebooks n on n.id = p.notebook_id
     where p.author_child_id = p_child_id
     order by p.created_at desc
     limit 100;
end;
$$;
