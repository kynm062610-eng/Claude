import React, { useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Body, Card, Loading, Screen, Title } from '../src/components/ui';
import { WatchModeBadge } from '../src/components/WatchModeBadge';
import { updateChildPreferences } from '../src/api';
import { useSession } from '../src/lib/session';
import { avatars } from '../src/data/assets';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../src/theme';

export default function Settings() {
  const { child, refresh } = useSession();
  const [saving, setSaving] = useState(false);

  if (!child) return <Loading />;

  const save = async (patch: Parameters<typeof updateChildPreferences>[1]) => {
    setSaving(true);
    try {
      await updateChildPreferences(child.id, patch);
      await refresh();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen>
      <Title>せってい</Title>

      <Card>
        <Body muted>いまの みまもり</Body>
        <WatchModeBadge mode={child.watch_mode} />
        <Body muted>
          この せっていは おうちの人が かえられるよ。かわったときは かならず おしらせが くるよ。
        </Body>
      </Card>

      <Card>
        <View style={styles.row}>
          <Text style={styles.label}>ふりがなを つける</Text>
          <Switch
            value={child.furigana_enabled}
            disabled={saving}
            onValueChange={(value) => void save({ furigana_enabled: value })}
          />
        </View>
      </Card>

      <Card>
        <Body muted>アバター</Body>
        <View style={styles.avatarRow}>
          {avatars.map((avatar) => (
            <Pressable
              key={avatar.key}
              accessibilityRole="button"
              accessibilityLabel={avatar.label}
              disabled={saving}
              onPress={() => void save({ avatar_key: avatar.key })}
              style={[styles.avatar, child.avatar_key === avatar.key && styles.avatarOn]}
            >
              <Text style={styles.avatarEmoji}>{avatar.emoji}</Text>
            </Pressable>
          ))}
        </View>
      </Card>

      <Card>
        <Body muted>おやすみ じかん</Body>
        <Body>
          よる {child.quiet_hours_start}じ 〜 あさ {child.quiet_hours_end}じ は ノートを かけないよ。
        </Body>
        <Body muted>この じかんは おうちの人が かえられるよ。</Body>
      </Card>

      <Pressable onPress={() => router.push('/home')} style={styles.link}>
        <Text style={styles.linkText}>ホームに もどる</Text>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: MIN_TAP },
  label: { fontSize: fontSize.body, color: colors.text, fontWeight: '700' },
  avatarRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  avatar: {
    width: MIN_TAP,
    height: MIN_TAP,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarOn: { borderColor: colors.primary, borderWidth: 3 },
  avatarEmoji: { fontSize: 28 },
  link: { minHeight: MIN_TAP, justifyContent: 'center' },
  linkText: { fontSize: fontSize.body, color: colors.accent, fontWeight: '700' },
});
