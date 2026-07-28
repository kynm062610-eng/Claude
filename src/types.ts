export type WatchMode = 'off' | 'notify_only' | 'full';

export type Child = {
  id: string;
  guardian_id: string;
  nickname: string;
  avatar_key: string;
  grade: number;
  watch_mode: WatchMode;
  furigana_enabled: boolean;
  quiet_hours_start: number;
  quiet_hours_end: number;
};

export type Group = {
  id: string;
  name: string;
  invite_code: string;
  created_by_child_id: string;
  max_members: number;
};

export type Membership = {
  id: string;
  group_id: string;
  child_id: string;
  turn_order: number;
  left_at: string | null;
};

export type Notebook = {
  id: string;
  group_id: string;
  title: string;
  current_turn_child_id: string | null;
  turn_started_at: string;
  is_closed: boolean;
};

export type Page = {
  id: string;
  notebook_id: string;
  author_child_id: string;
  page_number: number;
  content: PageContent;
  thumbnail_path: string | null;
  prompt_text: string | null;
  created_at: string;
};

export type Reaction = {
  id: string;
  page_id: string;
  child_id: string;
  emoji: string;
};

export type GuardianEvent = {
  id: string;
  child_id: string;
  event_type: 'watch_mode_changed' | 'disclosure_requested';
  detail: Record<string, unknown>;
  acknowledged_at: string | null;
  created_at: string;
};

/* ------------------------------------------------------------------ */
/* ページの中身                                                         */
/* ------------------------------------------------------------------ */

/**
 * ページはラスタ画像ではなく構造として保存する。
 * あとから拡大表示・印刷用の高解像度書き出し・再編集ができるようにするため。
 * 座標はこの固定キャンバス上の値で、表示時に画面幅へスケールする。
 */
export const CANVAS_WIDTH = 1080;
export const CANVAS_HEIGHT = 1440;

export type StrokeElement = {
  type: 'stroke';
  color: string;
  width: number;
  points: [number, number][];
};

export type TextElement = {
  type: 'text';
  text: string;
  x: number;
  y: number;
  size: number;
  color: string;
};

export type StampElement = {
  type: 'stamp';
  key: string;
  x: number;
  y: number;
  scale: number;
  rotation: number;
};

export type PageElement = StrokeElement | TextElement | StampElement;

export type PageContent = {
  version: 1;
  canvas: { width: number; height: number };
  background: string;
  elements: PageElement[];
};

export function emptyPageContent(background = 'plain'): PageContent {
  return {
    version: 1,
    canvas: { width: CANVAS_WIDTH, height: CANVAS_HEIGHT },
    background,
    elements: [],
  };
}
