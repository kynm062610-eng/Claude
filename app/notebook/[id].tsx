import React, { useCallback, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../../src/components/ui';
import { WatchModeBadge } from '../../src/components/WatchModeBadge';
import { PageCanvas } from '../../src/features/canvas/PageCanvas';
import { fetchMembers, fetchNotebook, fetchPages, passTurn, sendNudge } from '../../src/api';
import { useSession } from '../../src/lib/session';
import { avatarEmoji } from '../../src/data/assets';
import { canNudge, isMyTurn } from '../../src/utils/turn';
import { isQuietHours, quietHoursMessage } from '../../src/utils/quietHours';
import { colors, fontSize, spacing } from '../../src/theme';
import type { Child, Notebook, Page } from '../../src/types';

export default function NotebookScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { child } = useSession();
  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [members, setMembers] = useState<Child[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [nb, rows] = await Promise.all([fetchNotebook(id), fetchPages(id)]);
      setNotebook(nb);
      setPages(rows);
      setMembers(nb ? await fetchMembers(nb.group_id) : []);
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
  if (!notebook) {
    return (
      <Screen>
        <Body>ノートが みつからなかったよ。</Body>
        <BigButton label="もどる" variant="secondary" onPress={() => router.back()} />
      </Screen>
    );
  }

  const myTurn = isMyTurn(notebook, child.id);
  const quiet = isQuietHours(new Date(), child.quiet_hours_start, child.quiet_hours_end);
  const nudgeable = canNudge(notebook, child.id);
  const nameOf = (childId: string | null) =>
    members.find((m) => m.id === childId)?.nickname ?? 'だれか';

  const onWrite = () => {
    if (quiet) {
      Alert.alert('おやすみ じかん', quietHoursMessage(child.quiet_hours_start, child.quiet_hours_end));
      return;
    }
    router.push({ pathname: '/page/new', params: { notebookId: notebook.id } });
  };

  const onPass = () => {
    Alert.alert('パスする？', 'かかずに つぎの ひとに まわすよ。', [
      { text: 'やめる', style: 'cancel' },
      {
        text: 'パスする',
        onPress: async () => {
          await passTurn(notebook.id);
          await load();
        },
      },
    ]);
  };

  const onNudge = async () => {
    try {
      await sendNudge(notebook.id);
      Alert.alert('おくったよ', 'かえして！を おくったよ。');
    } catch {
      Alert.alert('きょうは もう おくったよ', 'あしたに なったら また おくれるよ。');
    }
  };

  return (
    <Screen>
      <WatchModeBadge mode={child.watch_mode} />
      <Title>{notebook.title}</Title>

      {myTurn ? (
        <Card>
          <Body>いまは あなたの ばん！</Body>
          <BigButton label="ページを かく" onPress={onWrite} />
          <BigButton label="きょうは パスする" variant="secondary" onPress={onPass} />
        </Card>
      ) : (
        <Card>
          <Body>いまは {nameOf(notebook.current_turn_child_id)} の ばん</Body>
          {nudgeable && <BigButton label="かえして！ を おくる" variant="secondary" onPress={onNudge} />}
        </Card>
      )}

      {pages.length === 0 && <Body muted>まだ 1ページも かかれていないよ。</Body>}

      {pages.map((page) => (
        <Card key={page.id} onPress={() => router.push(`/page/${page.id}`)}>
          <View style={styles.pageHeader}>
            <Text style={styles.pageAuthor}>
              {avatarEmoji(members.find((m) => m.id === page.author_child_id)?.avatar_key ?? 'cat')}{' '}
              {nameOf(page.author_child_id)}
            </Text>
            <Text style={styles.pageNumber}>{page.page_number}ページ</Text>
          </View>
          <PageCanvas content={page.content} />
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  pageHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  pageAuthor: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
  pageNumber: { fontSize: fontSize.label, color: colors.textMuted },
});
