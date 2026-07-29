import { supabase } from '../lib/supabase';
import type {
  Child,
  ChildProfile,
  GuardianEvent,
  Group,
  Membership,
  Notebook,
  Page,
  PageContent,
  ProfileAnswers,
  Reaction,
  WatchMode,
} from '../types';

/* ------------------------------------------------------------------ */
/* プロフィール                                                         */
/* ------------------------------------------------------------------ */

/** 子ども端末: 匿名サインインしたあと、保護者が発行したリンクコードで受け取る */
export async function claimChildProfile(linkCode: string): Promise<string> {
  const { data, error } = await supabase.rpc('claim_child_profile', {
    p_link_code: linkCode.trim().toUpperCase(),
  });
  if (error) throw error;
  return data as string;
}

export async function fetchMyChildProfile(authUserId: string): Promise<Child | null> {
  const { data, error } = await supabase
    .from('children')
    .select('*')
    .eq('auth_user_id', authUserId)
    .maybeSingle();
  if (error) throw error;
  return data as Child | null;
}

/** 保護者が子どもプロフィールを作る。返ったリンクコードを子ども端末で入力させる。 */
export async function createChild(args: {
  nickname: string;
  avatarKey: string;
  grade: number;
}): Promise<{ childId: string; linkCode: string }> {
  const { data, error } = await supabase.rpc('create_child', {
    p_nickname: args.nickname,
    p_avatar_key: args.avatarKey,
    p_grade: args.grade,
  });
  if (error) throw error;
  const row = (data as { child_id: string; link_code: string }[])[0];
  return { childId: row.child_id, linkCode: row.link_code };
}

export async function fetchChildrenOfGuardian(): Promise<Child[]> {
  const { data, error } = await supabase.from('children').select('*').is('deleted_at', null);
  if (error) throw error;
  return (data ?? []) as Child[];
}

export async function updateChildPreferences(
  childId: string,
  patch: Partial<Pick<Child, 'nickname' | 'avatar_key' | 'furigana_enabled'>>,
): Promise<void> {
  const { error } = await supabase.from('children').update(patch).eq('id', childId);
  if (error) throw error;
}

/** 自分のプロフィール回答を取得する。まだ何も保存していなければ null。 */
export async function fetchMyProfile(childId: string): Promise<ChildProfile | null> {
  const { data, error } = await supabase
    .from('child_profiles')
    .select('*')
    .eq('child_id', childId)
    .maybeSingle();
  if (error) throw error;
  return data as ChildProfile | null;
}

/** グループの仲間のプロフィールをまとめて取得する（ブロック相手は RLS 側で自動的に除外される）。 */
export async function fetchProfiles(childIds: string[]): Promise<ChildProfile[]> {
  if (childIds.length === 0) return [];
  const { data, error } = await supabase.from('child_profiles').select('*').in('child_id', childIds);
  if (error) throw error;
  return (data ?? []) as ChildProfile[];
}

/** プロフィールの保存。RPC を通し、更新日時を必ず更新する。 */
export async function saveMyProfile(answers: ProfileAnswers): Promise<void> {
  const { error } = await supabase.rpc('save_my_profile', { p_answers: answers });
  if (error) throw error;
}

/* ------------------------------------------------------------------ */
/* グループとノート                                                     */
/* ------------------------------------------------------------------ */

export async function createGroup(name: string): Promise<string> {
  const { data, error } = await supabase.rpc('create_group', { p_name: name });
  if (error) throw error;
  return data as string;
}

export async function joinGroupByCode(code: string): Promise<string> {
  const { data, error } = await supabase.rpc('join_group_by_code', {
    p_code: code.trim().toUpperCase(),
  });
  if (error) throw error;
  return data as string;
}

export async function fetchMyGroups(): Promise<Group[]> {
  const { data, error } = await supabase.from('groups').select('*');
  if (error) throw error;
  return (data ?? []) as Group[];
}

export async function fetchGroup(groupId: string): Promise<Group | null> {
  const { data, error } = await supabase.from('groups').select('*').eq('id', groupId).maybeSingle();
  if (error) throw error;
  return data as Group | null;
}

export async function fetchMemberships(groupId: string): Promise<Membership[]> {
  const { data, error } = await supabase
    .from('memberships')
    .select('*')
    .eq('group_id', groupId)
    .is('left_at', null)
    .order('turn_order');
  if (error) throw error;
  return (data ?? []) as Membership[];
}

export async function fetchMembers(groupId: string): Promise<Child[]> {
  const memberships = await fetchMemberships(groupId);
  if (memberships.length === 0) return [];
  const { data, error } = await supabase
    .from('children')
    .select('*')
    .in('id', memberships.map((m) => m.child_id));
  if (error) throw error;

  const order = new Map(memberships.map((m) => [m.child_id, m.turn_order]));
  return ((data ?? []) as Child[]).sort(
    (a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0),
  );
}

export async function fetchNotebook(notebookId: string): Promise<Notebook | null> {
  const { data, error } = await supabase
    .from('notebooks')
    .select('*')
    .eq('id', notebookId)
    .maybeSingle();
  if (error) throw error;
  return data as Notebook | null;
}

export async function fetchNotebooksForGroups(groupIds: string[]): Promise<Notebook[]> {
  if (groupIds.length === 0) return [];
  const { data, error } = await supabase.from('notebooks').select('*').in('group_id', groupIds);
  if (error) throw error;
  return (data ?? []) as Notebook[];
}

export async function fetchNotebooks(groupId: string): Promise<Notebook[]> {
  const { data, error } = await supabase
    .from('notebooks')
    .select('*')
    .eq('group_id', groupId)
    .order('created_at', { ascending: false });
  if (error) throw error;
  return (data ?? []) as Notebook[];
}

/* ------------------------------------------------------------------ */
/* ページ                                                              */
/* ------------------------------------------------------------------ */

export async function fetchPages(notebookId: string): Promise<Page[]> {
  const { data, error } = await supabase
    .from('pages')
    .select('*')
    .eq('notebook_id', notebookId)
    .order('page_number');
  if (error) throw error;
  return (data ?? []) as Page[];
}

export async function fetchPage(pageId: string): Promise<Page | null> {
  const { data, error } = await supabase.from('pages').select('*').eq('id', pageId).maybeSingle();
  if (error) throw error;
  return data as Page | null;
}

/**
 * ページ提出。ページ挿入と順番の受け渡しを 1 トランザクションで行う RPC を呼ぶ。
 * 「自分の番かどうか」の判定は DB 側でも行われるため、ここでの分岐は UI のためのもの。
 */
export async function submitPage(args: {
  notebookId: string;
  content: PageContent;
  thumbnailPath?: string | null;
  promptText?: string | null;
}): Promise<string> {
  const { data, error } = await supabase.rpc('submit_page', {
    p_notebook_id: args.notebookId,
    p_content: args.content,
    p_thumbnail_path: args.thumbnailPath ?? null,
    p_prompt_text: args.promptText ?? null,
  });
  if (error) throw error;
  return data as string;
}

export async function passTurn(notebookId: string): Promise<void> {
  const { error } = await supabase.rpc('pass_turn', { p_notebook_id: notebookId });
  if (error) throw error;
}

export async function sendNudge(notebookId: string): Promise<void> {
  const { error } = await supabase.rpc('send_nudge', { p_notebook_id: notebookId });
  if (error) throw error;
}

/* ------------------------------------------------------------------ */
/* リアクション・通報                                                   */
/* ------------------------------------------------------------------ */

export async function fetchReactions(pageId: string): Promise<Reaction[]> {
  const { data, error } = await supabase.from('reactions').select('*').eq('page_id', pageId);
  if (error) throw error;
  return (data ?? []) as Reaction[];
}

export async function toggleReaction(
  pageId: string,
  childId: string,
  emoji: string,
  existing: Reaction[],
): Promise<void> {
  const mine = existing.find((r) => r.child_id === childId && r.emoji === emoji);
  if (mine) {
    const { error } = await supabase.from('reactions').delete().eq('id', mine.id);
    if (error) throw error;
    return;
  }
  const { error } = await supabase
    .from('reactions')
    .insert({ page_id: pageId, child_id: childId, emoji });
  if (error) throw error;
}

export async function reportPage(pageId: string, reason: string): Promise<void> {
  const { error } = await supabase.rpc('report_page', { p_page_id: pageId, p_reason: reason });
  if (error) throw error;
}

/**
 * 安全フロアの発火。見まもりモードの値に関係なく保護者へ届く。
 * 本文は送らない。カテゴリだけを渡す。
 */
export async function raiseSafetyAlert(category: string): Promise<void> {
  const { error } = await supabase.rpc('raise_safety_alert', { p_category: category });
  if (error) throw error;
}

export async function fetchSafetyAlerts(
  childId: string,
): Promise<{ id: string; category: string; created_at: string }[]> {
  const { data, error } = await supabase
    .from('safety_alerts')
    .select('id, category, created_at')
    .eq('child_id', childId)
    .order('created_at', { ascending: false })
    .limit(20);
  if (error) throw error;
  return (data ?? []) as { id: string; category: string; created_at: string }[];
}

export async function blockChild(childId: string, blockedChildId: string): Promise<void> {
  const { error } = await supabase
    .from('blocks')
    .insert({ child_id: childId, blocked_child_id: blockedChildId });
  if (error) throw error;
}

/* ------------------------------------------------------------------ */
/* 保護者向け                                                          */
/* ------------------------------------------------------------------ */

/**
 * 見まもりモードの変更。直接 UPDATE ではなく RPC を通す。
 * 監査ログ（guardian_events）を必ず残し、子どもへの通知を発火させるため。
 */
export async function setWatchMode(childId: string, mode: WatchMode): Promise<void> {
  const { error } = await supabase.rpc('set_watch_mode', {
    p_child_id: childId,
    p_mode: mode,
  });
  if (error) throw error;
}

/** 開示請求。閲覧モードが off でも行使できるが、実行は必ず子どもに伝わる。 */
export async function requestDisclosure(childId: string): Promise<void> {
  const { error } = await supabase.rpc('request_disclosure', { p_child_id: childId });
  if (error) throw error;
}

/** notify_only 用。本文は返らず、書いた日時とノート名だけが返る。 */
export async function fetchChildActivity(
  childId: string,
): Promise<{ written_at: string; notebook_title: string }[]> {
  const { data, error } = await supabase.rpc('get_child_activity', { p_child_id: childId });
  if (error) throw error;
  return (data ?? []) as { written_at: string; notebook_title: string }[];
}

/** 子ども側で読む、保護者の操作履歴。透明性の原則のかなめ。 */
export async function fetchGuardianEvents(childId: string): Promise<GuardianEvent[]> {
  const { data, error } = await supabase
    .from('guardian_events')
    .select('*')
    .eq('child_id', childId)
    .order('created_at', { ascending: false })
    .limit(20);
  if (error) throw error;
  return (data ?? []) as GuardianEvent[];
}

export async function acknowledgeGuardianEvent(eventId: string): Promise<void> {
  const { error } = await supabase
    .from('guardian_events')
    .update({ acknowledged_at: new Date().toISOString() })
    .eq('id', eventId);
  if (error) throw error;
}
