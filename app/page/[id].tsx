import React, { useCallback, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen } from '../../src/components/ui';
import { PageCanvas } from '../../src/features/canvas/PageCanvas';
import {
  blockChild,
  fetchPage,
  fetchReactions,
  reportPage,
  toggleReaction,
} from '../../src/api';
import { useSession } from '../../src/lib/session';
import { useUiText } from '../../src/lib/uiText';
import { reactionEmojis } from '../../src/data/assets';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../../src/theme';
import type { Page, Reaction } from '../../src/types';

const reportReasons: { key: string; kana: string; kanji: string }[] = [
  { key: 'mean', kana: 'いじわるな ことばが ある', kanji: '意地悪な言葉がある' },
  { key: 'scary', kana: 'こわい / ふあんに なる', kanji: '怖い／不安になる' },
  { key: 'personal_info', kana: 'じゅうしょや でんわばんごうが ある', kanji: '住所や電話番号がある' },
  { key: 'other', kana: 'そのほか', kanji: 'そのほか' },
];

export default function PageScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { child } = useSession();
  const { t } = useUiText();
  const [page, setPage] = useState<Page | null>(null);
  const [reactions, setReactions] = useState<Reaction[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [p, r] = await Promise.all([fetchPage(id), fetchReactions(id)]);
      setPage(p);
      setReactions(r);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (loading || !child) return <Loading />;
  if (!page) {
    return (
      <Screen>
        <Body>{t('ページが みつからなかったよ。', 'ページが見つからなかったよ。')}</Body>
        <BigButton label={t('もどる', '戻る')} variant="secondary" onPress={() => router.back()} />
      </Screen>
    );
  }

  const onReact = async (emoji: string) => {
    // 先に画面を更新して、通信を待たせない
    const mine = reactions.find((r) => r.child_id === child.id && r.emoji === emoji);
    setReactions((prev) =>
      mine
        ? prev.filter((r) => r.id !== mine.id)
        : [...prev, { id: `temp-${emoji}`, page_id: page.id, child_id: child.id, emoji }],
    );
    try {
      await toggleReaction(page.id, child.id, emoji, reactions);
    } finally {
      await load();
    }
  };

  /** 通報。見まもりモードの値に関係なく、いつでも使える。 */
  const onReport = () => {
    Alert.alert(t('しらせる', '知らせる'), t('どうしたのか おしえてね。', 'どうしたのか教えてね。'), [
      ...reportReasons.map((reason) => ({
        text: t(reason.kana, reason.kanji),
        onPress: async () => {
          try {
            await reportPage(page.id, reason.key);
            Alert.alert(t('ありがとう', 'ありがとう'), t('おとなの人が かくにんするね。', '大人の人が確認するね。'));
          } catch {
            Alert.alert(
              t('おくれなかったよ', '送れなかったよ'),
              t('もういちど ためしてみてね。', 'もう一度試してみてね。'),
            );
          }
        },
      })),
      { text: t('やめる', 'やめる'), style: 'cancel' as const },
    ]);
  };

  const onBlock = () => {
    if (page.author_child_id === child.id) return;
    Alert.alert(
      t('この人の ページを かくす？', 'この人のページを隠す？'),
      t('これから この人の ページは 見えなくなるよ。', 'これからこの人のページは見えなくなるよ。'),
      [
        { text: t('やめる', 'やめる'), style: 'cancel' },
        {
          text: t('かくす', '隠す'),
          onPress: async () => {
            await blockChild(child.id, page.author_child_id);
            router.back();
          },
        },
      ],
    );
  };

  const countOf = (emoji: string) => reactions.filter((r) => r.emoji === emoji).length;
  const mineHas = (emoji: string) =>
    reactions.some((r) => r.emoji === emoji && r.child_id === child.id);

  return (
    <Screen>
      {page.prompt_text && (
        <Card>
          <Text style={styles.promptLabel}>{t('おだい', 'お題')}</Text>
          <Body>{page.prompt_text}</Body>
        </Card>
      )}

      <PageCanvas content={page.content} />

      <View style={styles.reactionRow}>
        {reactionEmojis.map((emoji) => (
          <Pressable
            key={emoji}
            accessibilityRole="button"
            accessibilityLabel={`りあくしょん ${emoji}`}
            onPress={() => void onReact(emoji)}
            style={[styles.reaction, mineHas(emoji) && styles.reactionOn]}
          >
            <Text style={styles.reactionEmoji}>{emoji}</Text>
            {countOf(emoji) > 0 && <Text style={styles.reactionCount}>{countOf(emoji)}</Text>}
          </Pressable>
        ))}
      </View>

      <BigButton label={t('おとなの人に しらせる', '大人の人に知らせる')} variant="secondary" onPress={onReport} />
      {page.author_child_id !== child.id && (
        <BigButton
          label={t('この人の ページを かくす', 'この人のページを隠す')}
          variant="secondary"
          onPress={onBlock}
        />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  promptLabel: { fontSize: fontSize.label, fontWeight: '800', color: colors.textMuted },
  reactionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  reaction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    minHeight: MIN_TAP,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  reactionOn: { borderColor: colors.primary, borderWidth: 3 },
  reactionEmoji: { fontSize: 26 },
  reactionCount: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
});
