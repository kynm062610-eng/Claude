import type { Membership, Notebook } from '../types';

/** 「かえして！」を送れるようになるまでの日数 */
export const NUDGE_AFTER_DAYS = 3;

export function isMyTurn(notebook: Notebook, childId: string | null): boolean {
  return !notebook.is_closed && !!childId && notebook.current_turn_child_id === childId;
}

/** 現在の担当が滞留していて、催促を送れる状態か */
export function canNudge(notebook: Notebook, childId: string | null, now = new Date()): boolean {
  if (notebook.is_closed) return false;
  if (!childId) return false;
  if (notebook.current_turn_child_id === childId) return false; // 自分の番なら催促しない

  const elapsedDays =
    (now.getTime() - new Date(notebook.turn_started_at).getTime()) / (1000 * 60 * 60 * 24);
  return elapsedDays >= NUDGE_AFTER_DAYS;
}

/**
 * 順番の次の子を返す。DB 側の next_turn_child() と同じ規則。
 * 表示用（「つぎは○○ちゃん」）に使う。順番の確定は必ず DB 側で行う。
 */
export function nextTurnChildId(
  memberships: Membership[],
  currentChildId: string | null,
): string | null {
  const active = memberships
    .filter((m) => m.left_at === null)
    .sort((a, b) => a.turn_order - b.turn_order);

  if (active.length === 0) return null;
  if (!currentChildId) return active[0].child_id;

  const index = active.findIndex((m) => m.child_id === currentChildId);
  if (index === -1) return active[0].child_id;

  return active[(index + 1) % active.length].child_id;
}
