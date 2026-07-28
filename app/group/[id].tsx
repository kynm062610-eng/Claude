import React, { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../../src/components/ui';
import { WatchModeBadge } from '../../src/components/WatchModeBadge';
import { fetchGroup, fetchMembers, fetchNotebooks } from '../../src/api';
import { useSession } from '../../src/lib/session';
import { avatarEmoji } from '../../src/data/assets';
import { colors, fontSize, radius, spacing } from '../../src/theme';
import type { Child, Group, Notebook } from '../../src/types';

export default function GroupScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { child } = useSession();
  const [group, setGroup] = useState<Group | null>(null);
  const [members, setMembers] = useState<Child[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [g, m, n] = await Promise.all([fetchGroup(id), fetchMembers(id), fetchNotebooks(id)]);
      setGroup(g);
      setMembers(m);
      setNotebooks(n);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (loading || !group || !child) return <Loading />;

  const nameOf = (childId: string | null) =>
    members.find((m) => m.id === childId)?.nickname ?? 'だれか';

  return (
    <Screen>
      <WatchModeBadge mode={child.watch_mode} />
      <Title>{group.name}</Title>

      <Card>
        <Body muted>あいことば（ともだちに おしえてね）</Body>
        <Text style={styles.code}>{group.invite_code}</Text>
        <Body muted>{members.length} / {group.max_members} にん</Body>
      </Card>

      <Card>
        <Body muted>じゅんばん</Body>
        <View style={styles.memberRow}>
          {members.map((member, index) => (
            <View key={member.id} style={styles.member}>
              <Text style={styles.memberEmoji}>{avatarEmoji(member.avatar_key)}</Text>
              <Text style={styles.memberName}>{member.nickname}</Text>
              <Text style={styles.memberOrder}>{index + 1}</Text>
            </View>
          ))}
        </View>
      </Card>

      {notebooks.map((notebook) => {
        const isMine = notebook.current_turn_child_id === child.id;
        return (
          <Card key={notebook.id} onPress={() => router.push(`/notebook/${notebook.id}`)}>
            <Text style={styles.notebookTitle}>{notebook.title}</Text>
            {notebook.is_closed ? (
              <Body muted>かきおわった ノート</Body>
            ) : isMine ? (
              <View style={styles.turnBadge}>
                <Text style={styles.turnBadgeText}>あなたの ばん！</Text>
              </View>
            ) : (
              <Body muted>いまは {nameOf(notebook.current_turn_child_id)} の ばん</Body>
            )}
          </Card>
        );
      })}

      <BigButton label="ホームに もどる" variant="secondary" onPress={() => router.push('/home')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  code: { fontSize: 34, fontWeight: '900', letterSpacing: 6, color: colors.primary },
  memberRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  member: { alignItems: 'center', width: 72 },
  memberEmoji: { fontSize: 34 },
  memberName: { fontSize: fontSize.label, color: colors.text, fontWeight: '700' },
  memberOrder: { fontSize: 12, color: colors.textMuted },
  notebookTitle: { fontSize: fontSize.body, fontWeight: '800', color: colors.text },
  turnBadge: {
    alignSelf: 'flex-start',
    backgroundColor: colors.turnBadge,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
  turnBadgeText: { fontWeight: '800', color: colors.text, fontSize: fontSize.label },
});
