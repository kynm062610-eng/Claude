import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { TreeView } from './TreeView';
import { seasonLabels, seasonOf, treeProgress } from './treeStage';
import { useUiText } from '../../lib/uiText';
import { colors, fontSize, radius, spacing } from '../../theme';

/**
 * ノートの育ち具合を木で見せるカード。
 *
 * 「あと何ページで次の姿になる」だけを示し、書かなかったことは一切責めない。
 * 減らない設計なので「途切れた」という表示も持たない。
 */
export function TreeCard({
  notebookId,
  pageCount,
}: {
  notebookId: string;
  pageCount: number;
}) {
  const { t } = useUiText();
  const season = useMemo(() => seasonOf(), []);
  const { current, next, ratio, remaining } = treeProgress(pageCount);

  return (
    <View style={styles.card}>
      <TreeView level={current.level} season={season} seed={notebookId} />

      <View style={styles.body}>
        <View style={styles.headerRow}>
          <Text style={styles.stage}>{t(current.labelKana, current.labelKanji)}</Text>
          <Text style={styles.season}>
            {t(seasonLabels[season].kana, seasonLabels[season].kanji)}
          </Text>
        </View>

        <Text style={styles.pages}>
          {t(`みんなで ${pageCount}ページ`, `みんなで${pageCount}ページ`)}
        </Text>

        <View style={styles.barTrack}>
          <View style={[styles.barFill, { width: `${Math.round(ratio * 100)}%` }]} />
        </View>

        {next ? (
          <Text style={styles.next}>
            {t(
              `あと ${remaining}ページで「${next.labelKana}」`,
              `あと${remaining}ページで「${next.labelKanji}」`,
            )}
          </Text>
        ) : (
          <Text style={styles.next}>
            {t('いちばん おおきな すがたに なったよ！', '一番大きな姿になったよ！')}
          </Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  body: { padding: spacing.md, gap: spacing.sm },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stage: { fontSize: fontSize.title, fontWeight: '800', color: colors.text },
  season: { fontSize: fontSize.label, fontWeight: '700', color: colors.textMuted },
  pages: { fontSize: fontSize.label, color: colors.textMuted },
  barTrack: {
    height: 12,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    overflow: 'hidden',
  },
  barFill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.success },
  next: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
});
