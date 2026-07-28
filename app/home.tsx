import React, { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../src/components/ui';
import { WatchModeBadge } from '../src/components/WatchModeBadge';
import { GuardianEventBanner } from '../src/components/GuardianEventBanner';
import { fetchMyGroups, fetchNotebooksForGroups } from '../src/api';
import { useSession } from '../src/lib/session';
import { colors, fontSize, radius, spacing } from '../src/theme';
import type { Group, Notebook } from '../src/types';

export default function Home() {
  const { child, loading } = useSession();
  const [groups, setGroups] = useState<Group[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [fetching, setFetching] = useState(true);

  const load = useCallback(async () => {
    setFetching(true);
    try {
      const rows = await fetchMyGroups();
      setGroups(rows);
      setNotebooks(await fetchNotebooksForGroups(rows.map((g) => g.id)));
    } finally {
      setFetching(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (loading || !child) return <Loading />;

  const myTurnGroupIds = new Set(
    notebooks.filter((n) => !n.is_closed && n.current_turn_child_id === child.id).map((n) => n.group_id),
  );

  return (
    <Screen>
      <WatchModeBadge mode={child.watch_mode} />
      <GuardianEventBanner childId={child.id} />

      <Title>こんにちは、{child.nickname}</Title>

      {fetching && groups.length === 0 ? (
        <Loading />
      ) : groups.length === 0 ? (
        <Card>
          <Body>まだ グループが ないよ。</Body>
          <Body muted>
            あたらしく つくるか、ともだちから もらった 6もじの コードで はいってみよう。
          </Body>
        </Card>
      ) : (
        groups.map((group) => {
          const isMyTurn = myTurnGroupIds.has(group.id);
          return (
            <Card key={group.id} onPress={() => router.push(`/group/${group.id}`)}>
              <View style={styles.row}>
                <Text style={styles.groupName}>{group.name}</Text>
                {isMyTurn && (
                  <View style={styles.turnBadge}>
                    <Text style={styles.turnBadgeText}>あなたの ばん！</Text>
                  </View>
                )}
              </View>
              <Text style={styles.code}>あいことば: {group.invite_code}</Text>
            </Card>
          );
        })
      )}

      <BigButton label="グループに はいる" onPress={() => router.push('/group/join')} />
      <BigButton label="せってい" variant="secondary" onPress={() => router.push('/settings')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  groupName: { fontSize: fontSize.body, fontWeight: '800', color: colors.text, flexShrink: 1 },
  turnBadge: {
    backgroundColor: colors.turnBadge,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
  turnBadgeText: { fontWeight: '800', color: colors.text, fontSize: fontSize.label },
  code: { color: colors.textMuted, fontSize: fontSize.label },
});
