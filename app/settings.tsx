import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Body, Card, Loading, Screen, Title } from '../src/components/ui';
import { WatchModeBadge } from '../src/components/WatchModeBadge';
import { updateChildPreferences } from '../src/api';
import { useSession } from '../src/lib/session';
import { useUiText } from '../src/lib/uiText';
import { avatars } from '../src/data/assets';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../src/theme';

export default function Settings() {
  const { child, refresh } = useSession();
  const { t, useKana } = useUiText();
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
      <Title>{t('せってい', '設定')}</Title>

      <Card>
        <Body muted>{t('いまの みまもり', '今の見まもり')}</Body>
        <WatchModeBadge mode={child.watch_mode} />
        <Body muted>
          {t(
            'この せっていは おうちの人が かえられるよ。かわったときは かならず おしらせが くるよ。',
            'この設定はおうちの人が変えられるよ。変わったときは必ずお知らせが来るよ。',
          )}
        </Body>
      </Card>

      <Card>
        <Text style={styles.label}>{t('もじの みため', '文字の見た目')}</Text>
        <Body muted>
          {t(
            'ひらがなと かんじ、どちらで ひょうじするか えらべるよ。',
            'ひらがなと漢字、どちらで表示するか選べるよ。',
          )}
        </Body>
        <View style={styles.segmented}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: useKana }}
            disabled={saving}
            onPress={() => void save({ furigana_enabled: true })}
            style={[styles.segment, useKana && styles.segmentOn]}
          >
            <Text style={[styles.segmentText, useKana && styles.segmentTextOn]}>ひらがな</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: !useKana }}
            disabled={saving}
            onPress={() => void save({ furigana_enabled: false })}
            style={[styles.segment, !useKana && styles.segmentOn]}
          >
            <Text style={[styles.segmentText, !useKana && styles.segmentTextOn]}>かんじ</Text>
          </Pressable>
        </View>
      </Card>

      <Card>
        <Body muted>{t('アバター', 'アバター')}</Body>
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
        <Body muted>{t('おやすみ じかん', 'おやすみ時間')}</Body>
        <Body>
          {t(
            `よる ${child.quiet_hours_start}じ 〜 あさ ${child.quiet_hours_end}じ は ノートを かけないよ。`,
            `夜${child.quiet_hours_start}時〜朝${child.quiet_hours_end}時はノートを書けないよ。`,
          )}
        </Body>
        <Body muted>{t('この じかんは おうちの人が かえられるよ。', 'この時間はおうちの人が変えられるよ。')}</Body>
      </Card>

      <Pressable onPress={() => router.push('/home')} style={styles.link}>
        <Text style={styles.linkText}>{t('ホームに もどる', 'ホームに戻る')}</Text>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: fontSize.body, color: colors.text, fontWeight: '700' },
  segmented: { flexDirection: 'row', gap: spacing.sm },
  segment: {
    flex: 1,
    minHeight: MIN_TAP,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentOn: { borderColor: colors.primary, backgroundColor: colors.primary, borderWidth: 2 },
  segmentText: { fontSize: fontSize.body, fontWeight: '800', color: colors.text },
  segmentTextOn: { color: colors.primaryText },
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
