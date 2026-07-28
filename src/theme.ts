/**
 * 小学生向けのため、色は彩度高め・コントラスト強めにする。
 * タップ対象は最小 56dp（低学年の指で押せる大きさ）。
 */
export const colors = {
  bg: '#FFFBF2',
  surface: '#FFFFFF',
  border: '#E7DFD0',
  text: '#2C2A26',
  textMuted: '#7A736A',
  primary: '#FF8A3D',
  primaryText: '#FFFFFF',
  accent: '#3BA7F5',
  success: '#3CB371',
  danger: '#E4572E',
  turnBadge: '#FFD84D',
} as const;

export const radius = { sm: 8, md: 16, lg: 24, pill: 999 } as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;

/** タップ対象の最小サイズ。これを下回るボタンを作らない。 */
export const MIN_TAP = 56;

export const fontSize = {
  body: 18,
  label: 16,
  title: 26,
  huge: 34,
} as const;

/** 描画パレット。多すぎると選べないので 8 色に絞る。 */
export const penColors = [
  '#2C2A26',
  '#E4572E',
  '#FF8A3D',
  '#F5C518',
  '#3CB371',
  '#3BA7F5',
  '#8A63D2',
  '#F06BA8',
] as const;

export const penWidths = [6, 12, 24] as const;
