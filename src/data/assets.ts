/**
 * アバター・スタンプ・便箋の柄。
 *
 * 画像アップロードを持たないため、すべてアプリ内プリセット。
 * 顔写真が入らない構造にしておくことが安全設計の一部。
 */

export const avatars = [
  { key: 'cat', label: 'ねこ', emoji: '🐱' },
  { key: 'dog', label: 'いぬ', emoji: '🐶' },
  { key: 'bear', label: 'くま', emoji: '🐻' },
  { key: 'rabbit', label: 'うさぎ', emoji: '🐰' },
  { key: 'panda', label: 'ぱんだ', emoji: '🐼' },
  { key: 'fox', label: 'きつね', emoji: '🦊' },
  { key: 'penguin', label: 'ぺんぎん', emoji: '🐧' },
  { key: 'frog', label: 'かえる', emoji: '🐸' },
  { key: 'unicorn', label: 'ゆにこーん', emoji: '🦄' },
  { key: 'dino', label: 'きょうりゅう', emoji: '🦖' },
] as const;

export function avatarEmoji(key: string): string {
  return avatars.find((a) => a.key === key)?.emoji ?? '🐱';
}

export const stamps = [
  { key: 'star', emoji: '⭐' },
  { key: 'heart', emoji: '💖' },
  { key: 'smile', emoji: '😄' },
  { key: 'cry', emoji: '😢' },
  { key: 'fire', emoji: '🔥' },
  { key: 'flower', emoji: '🌸' },
  { key: 'cake', emoji: '🍰' },
  { key: 'ball', emoji: '⚽' },
  { key: 'music', emoji: '🎵' },
  { key: 'rainbow', emoji: '🌈' },
  { key: 'thumbsup', emoji: '👍' },
  { key: 'sparkle', emoji: '✨' },
] as const;

export function stampEmoji(key: string): string {
  return stamps.find((s) => s.key === key)?.emoji ?? '⭐';
}

export const backgrounds = [
  { key: 'plain', label: 'むじ', color: '#FFFFFF' },
  { key: 'dots', label: 'みずたま', color: '#FFF7E8' },
  { key: 'grid', label: 'ほうがん', color: '#F3F9FF' },
  { key: 'lined', label: 'せんつき', color: '#FFFDF5' },
  { key: 'sky', label: 'そら', color: '#EAF6FF' },
  { key: 'mint', label: 'みんと', color: '#EDFBF3' },
] as const;

export function backgroundColor(key: string): string {
  return backgrounds.find((b) => b.key === key)?.color ?? '#FFFFFF';
}

/** リアクションに使える絵文字。自由入力にしないことで荒れを防ぐ。 */
export const reactionEmojis = ['👍', '💖', '😄', '🎉', '😲', '🥺'] as const;
