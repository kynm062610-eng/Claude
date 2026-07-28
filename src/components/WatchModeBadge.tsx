import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, fontSize, radius, spacing } from '../theme';
import type { WatchMode } from '../types';

/**
 * 見まもりモードのバッジ。
 *
 * 子どもの画面に常時表示する。これは飾りではなく、本アプリの安全設計の芯。
 * 「知らないうちに保護者が読んでいる」状態を作らないために、
 * ノート系の画面には必ずこのバッジを置く（docs/01-safety-and-privacy.md）。
 */
const labels: Record<WatchMode, { text: string; emoji: string; color: string }> = {
  off: { text: 'おうちの人：見ていません', emoji: '🙈', color: colors.success },
  notify_only: { text: 'おうちの人：書いたことだけ つたわります', emoji: '🔔', color: colors.accent },
  full: { text: 'おうちの人：見ています', emoji: '👀', color: colors.primary },
};

export function WatchModeBadge({ mode }: { mode: WatchMode }) {
  const item = labels[mode];
  return (
    <View
      accessibilityRole="text"
      accessibilityLabel={`見まもりモード: ${item.text}`}
      style={[styles.badge, { borderColor: item.color }]}
    >
      <Text style={styles.emoji}>{item.emoji}</Text>
      <Text style={styles.text}>{item.text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    alignSelf: 'flex-start',
    borderWidth: 2,
    borderRadius: radius.pill,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  emoji: { fontSize: fontSize.body },
  text: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
});
