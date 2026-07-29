-- プロフィール。
--
-- 質問は増減しやすいよう jsonb（質問 ID -> 回答文字列）で持つ。
-- 質問の定義そのものはアプリ側（src/data/profileQuestions.ts）にあり、
-- ここには「どの質問に何と答えたか」だけを保存する。
--
-- 収集しないもの（docs/01-safety-and-privacy.md の方針を維持）:
--   居住地・生年月日・写真・恋愛に関する項目は質問自体を用意しない。

create table public.child_profiles (
  child_id   uuid primary key references public.children(id) on delete cascade,
  answers    jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

alter table public.child_profiles enable row level security;

-- 閲覧:
--   本人はいつでも読める
--   同じグループの子は互いに読める（ブロックした相手は除く）
--   保護者は watch_mode = 'full' のときだけ読める（ページと同じ扱い）
create policy child_profiles_select on public.child_profiles
  for select using (
    child_id = public.current_child_id()
    or (
      exists (
        select 1
        from public.memberships mine
        join public.memberships theirs on theirs.group_id = mine.group_id
        where mine.child_id = public.current_child_id()
          and mine.left_at is null
          and theirs.child_id = child_profiles.child_id
          and theirs.left_at is null
      )
      and not exists (
        select 1 from public.blocks b
        where b.child_id = public.current_child_id()
          and b.blocked_child_id = child_profiles.child_id
      )
    )
    or public.guardian_can_read_content(child_id)
  );

-- 編集は本人のみ
create policy child_profiles_insert on public.child_profiles
  for insert with check (child_id = public.current_child_id());

create policy child_profiles_update on public.child_profiles
  for update using (child_id = public.current_child_id())
  with check (child_id = public.current_child_id());

-- 保存。updated_at を必ず更新するため RPC を通す。
create or replace function public.save_my_profile(p_answers jsonb)
returns void
language plpgsql volatile security definer set search_path = public
as $$
declare
  v_child_id uuid := public.current_child_id();
begin
  if v_child_id is null then
    raise exception 'not_a_child_session';
  end if;

  insert into public.child_profiles (child_id, answers)
  values (v_child_id, p_answers)
  on conflict (child_id)
  do update set answers = p_answers, updated_at = now();
end;
$$;
