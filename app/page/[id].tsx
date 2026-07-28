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
import { reactionEmojis } from '../../src/data/assets';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../../src/theme';
import type { Page, Reaction } from '../../src/types';

const reportReasons: { key: string; label: string }[] = [
  { key: 'mean', label: 'いじわるな ことばが ある' },
  { key: 'scary', label: 'こわい / ふあんに なる' },
  { key: 'personal_info', label: 'じゅうしょや でんわばんごうが ある' },
  { key: 'other', label: 'そのほか' },
];

export default function PageScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { child } = useSession();
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
        <Body>ページが みつからなかったよ。</Body>
        <BigButton label="もどる" variant="secondary" onPress={() => router.back()} />
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
    Alert.alert('しらせる', 'どうしたのか おしえてね。', [
      ...reportReasons.map((reason) => ({
        text: reason.label,
        onPress: async () => {
          try {
            await reportPage(page.id, reason.key);
            Alert.alert('ありがとう', 'おとなの人が かくにんするね。');
          } catch {
            Alert.alert('おくれなかったよ', 'もういちど ためしてみてね。');
          }
        },
      })),
      { text: 'やめる', style: 'cancel' as const },
    ]);
  };

  const onBlock = () => {
    if (page.author_child_id === child.id) return;
    Alert.alert('この人の ページを かくす？', 'これから この人の ページは 見えなくなるよ。', [
      { text: 'やめる', style: 'cancel' },
      {
        text: 'かくす',
        onPress: async () => {
          await blockChild(child.id, page.author_child_id);
          router.back();
        },
      },
    ]);
  };

  const countOf = (emoji: string) => reactions.filter((r) => r.emoji === emoji).length;
  const mineHas = (emoji: string) =>
    reactions.some((r) => r.emoji === emoji && r.child_id === child.id);

  return (
    <Screen>
      {page.prompt_text && (
        <Card>
          <Text style={styles.promptLabel}>おだい</Text>
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

      <BigButton label="おとなの人に しらせる" variant="secondary" onPress={onReport} />
      {page.author_child_id !== child.id && (
        <BigButton label="この人の ページを かくす" variant="secondary" onPress={onBlock} />
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
