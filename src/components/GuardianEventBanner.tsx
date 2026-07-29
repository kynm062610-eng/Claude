import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { acknowledgeGuardianEvent, fetchGuardianEvents } from '../api';
import { useUiText } from '../lib/uiText';
import { colors, fontSize, radius, spacing } from '../theme';
import type { GuardianEvent } from '../types';
import { BigButton } from './ui';

/**
 * 保護者が見まもりモードを変えた／開示請求をしたことを、子ども本人に知らせる。
 *
 * 親がこっそり `full` に切り替えて黙っている、という状態を作らないための仕組み。
 * 「確認した」を押すまで消えない。
 */
function describe(event: GuardianEvent, useKana: boolean): string {
  if (event.event_type === 'watch_mode_changed') {
    const to = String(event.detail.to ?? '');
    if (to === 'full') {
      return useKana
        ? 'おうちの人が、ノートを 見られる せっていに かえたよ。'
        : 'おうちの人が、ノートを見られる設定に変えたよ。';
    }
    if (to === 'notify_only') {
      return useKana
        ? 'おうちの人には「書いたこと」だけ つたわる せっていに かわったよ。'
        : 'おうちの人には「書いたこと」だけ伝わる設定に変わったよ。';
    }
    return useKana
      ? 'おうちの人が、ノートを 見ない せっていに かえたよ。'
      : 'おうちの人が、ノートを見ない設定に変えたよ。';
  }
  return useKana
    ? 'おうちの人が、きろくの かくにんを もうしこんだよ。'
    : 'おうちの人が、記録の確認を申し込んだよ。';
}

export function GuardianEventBanner({ childId }: { childId: string }) {
  const { t, useKana } = useUiText();
  const [events, setEvents] = useState<GuardianEvent[]>([]);

  const load = useCallback(async () => {
    try {
      const rows = await fetchGuardianEvents(childId);
      setEvents(rows.filter((e) => e.acknowledged_at === null));
    } catch {
      // 通知の取得に失敗しても本体の操作は止めない
    }
  }, [childId]);

  useEffect(() => {
    void load();
  }, [load]);

  const acknowledge = useCallback(
    async (eventId: string) => {
      setEvents((prev) => prev.filter((e) => e.id !== eventId));
      try {
        await acknowledgeGuardianEvent(eventId);
      } catch {
        void load();
      }
    },
    [load],
  );

  if (events.length === 0) return null;
  const event = events[0];

  return (
    <View style={styles.banner}>
      <Text style={styles.title}>{t('おしらせ', 'お知らせ')}</Text>
      <Text style={styles.text}>{describe(event, useKana)}</Text>
      <BigButton label={t('わかった', 'わかった')} variant="secondary" onPress={() => void acknowledge(event.id)} />
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: '#FFF4D6',
    borderWidth: 2,
    borderColor: colors.turnBadge,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  title: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
  text: { fontSize: fontSize.body, lineHeight: 26, color: colors.text },
});
