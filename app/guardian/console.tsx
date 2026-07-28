import React, { useCallback, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../../src/components/ui';
import {
  createChild,
  fetchChildActivity,
  fetchChildrenOfGuardian,
  fetchSafetyAlerts,
  requestDisclosure,
  setWatchMode,
} from '../../src/api';
import { useSession } from '../../src/lib/session';
import { avatarEmoji } from '../../src/data/assets';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../../src/theme';
import type { Child, WatchMode } from '../../src/types';

const watchModeOptions: { value: WatchMode; label: string; detail: string }[] = [
  {
    value: 'off',
    label: '見ない（初期設定）',
    detail: 'ノートの内容は表示されません。お子さまのプライバシーを尊重する設定です。',
  },
  {
    value: 'notify_only',
    label: '書いたことだけ知る',
    detail: '「いつ書いたか」だけが表示されます。本文と絵は表示されません。',
  },
  {
    value: 'full',
    label: 'ぜんぶ見る',
    detail: 'お子さまが参加しているノートの全ページを閲覧できます。',
  },
];

const alertLabels: Record<string, string> = {
  violence: '危険を示す表現が検知されました',
  exclusion: '仲間はずれを示す表現が検知されました',
  insult: 'きつい表現が検知されました',
  personal_info: '個人情報らしき記載が検知されました',
};

export default function GuardianConsole() {
  const { signOut } = useSession();
  const [children, setChildren] = useState<Child[]>([]);
  const [loading, setLoading] = useState(true);
  const [nickname, setNickname] = useState('');
  const [grade, setGrade] = useState('3');
  const [issuedCode, setIssuedCode] = useState<string | null>(null);
  const [activity, setActivity] = useState<Record<string, { written_at: string; notebook_title: string }[]>>({});
  const [alerts, setAlerts] = useState<Record<string, { id: string; category: string; created_at: string }[]>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await fetchChildrenOfGuardian();
      setChildren(rows);

      // 安全フロアの通知は見まもりモードに関係なく取得する
      const alertEntries = await Promise.all(
        rows.map(async (c) => [c.id, await fetchSafetyAlerts(c.id).catch(() => [])] as const),
      );
      setAlerts(Object.fromEntries(alertEntries));

      const activityEntries = await Promise.all(
        rows
          .filter((c) => c.watch_mode !== 'off')
          .map(async (c) => [c.id, await fetchChildActivity(c.id).catch(() => [])] as const),
      );
      setActivity(Object.fromEntries(activityEntries));
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const onCreateChild = async () => {
    const parsedGrade = Number(grade);
    if (nickname.trim().length === 0 || !Number.isInteger(parsedGrade)) return;
    try {
      const { linkCode } = await createChild({
        nickname: nickname.trim(),
        avatarKey: 'cat',
        grade: Math.min(6, Math.max(1, parsedGrade)),
      });
      setIssuedCode(linkCode);
      setNickname('');
      await load();
    } catch {
      Alert.alert('登録できませんでした', 'もう一度お試しください。');
    }
  };

  const onChangeMode = (child: Child, mode: WatchMode) => {
    if (child.watch_mode === mode) return;
    Alert.alert(
      '設定を変更しますか？',
      'この変更はお子さま本人にも通知されます。隠れて閲覧することはできません。',
      [
        { text: 'やめる', style: 'cancel' },
        {
          text: '変更する',
          onPress: async () => {
            await setWatchMode(child.id, mode);
            await load();
          },
        },
      ],
    );
  };

  const onRequestDisclosure = (child: Child) => {
    Alert.alert(
      '記録の開示を請求しますか？',
      '保護者の権利として、閲覧設定が「見ない」でも請求できます。請求したことはお子さま本人に通知されます。',
      [
        { text: 'やめる', style: 'cancel' },
        {
          text: '請求する',
          onPress: async () => {
            await requestDisclosure(child.id);
            Alert.alert('受け付けました', '担当より追ってご連絡します。');
            await load();
          },
        },
      ],
    );
  };

  if (loading) return <Loading />;

  return (
    <Screen>
      <Title>保護者メニュー</Title>

      {issuedCode && (
        <Card>
          <Body>お子さまの端末で、このコードを入力してください。</Body>
          <Text style={styles.code}>{issuedCode}</Text>
          <Body muted>コードは一度使うと無効になります。</Body>
        </Card>
      )}

      {children.map((child) => (
        <Card key={child.id}>
          <Text style={styles.childName}>
            {avatarEmoji(child.avatar_key)} {child.nickname}（{child.grade}年生）
          </Text>

          <Body muted>見まもりモード</Body>
          {watchModeOptions.map((option) => (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ selected: child.watch_mode === option.value }}
              onPress={() => onChangeMode(child, option.value)}
              style={[styles.option, child.watch_mode === option.value && styles.optionOn]}
            >
              <Text style={styles.optionLabel}>
                {child.watch_mode === option.value ? '● ' : '○ '}
                {option.label}
              </Text>
              <Text style={styles.optionDetail}>{option.detail}</Text>
            </Pressable>
          ))}

          {(alerts[child.id]?.length ?? 0) > 0 && (
            <View style={styles.alertBox}>
              <Text style={styles.alertTitle}>安全に関するお知らせ</Text>
              <Text style={styles.alertNote}>
                閲覧設定に関わらず通知されます。本文は保護者にも表示されません。
              </Text>
              {alerts[child.id].map((alert) => (
                <Text key={alert.id} style={styles.alertLine}>
                  ・{new Date(alert.created_at).toLocaleDateString('ja-JP')}{' '}
                  {alertLabels[alert.category] ?? alert.category}
                </Text>
              ))}
            </View>
          )}

          {child.watch_mode === 'notify_only' && (
            <View>
              <Body muted>書いた記録</Body>
              {(activity[child.id] ?? []).slice(0, 5).map((entry, index) => (
                <Text key={index} style={styles.activityLine}>
                  ・{new Date(entry.written_at).toLocaleString('ja-JP')}「{entry.notebook_title}」
                </Text>
              ))}
              {(activity[child.id] ?? []).length === 0 && <Body muted>まだ記録はありません。</Body>}
            </View>
          )}

          <BigButton
            label="記録の開示を請求する"
            variant="secondary"
            onPress={() => onRequestDisclosure(child)}
          />
        </Card>
      ))}

      <Card>
        <Body>お子さまを追加</Body>
        <TextInput
          style={styles.input}
          value={nickname}
          onChangeText={setNickname}
          maxLength={20}
          placeholder="ニックネーム（本名は避けてください）"
          placeholderTextColor={colors.textMuted}
        />
        <TextInput
          style={styles.input}
          value={grade}
          onChangeText={setGrade}
          keyboardType="number-pad"
          maxLength={1}
          placeholder="学年（1〜6）"
          placeholderTextColor={colors.textMuted}
        />
        <BigButton label="追加してコードを発行" onPress={onCreateChild} disabled={nickname.trim().length === 0} />
      </Card>

      <BigButton label="ログアウト" variant="secondary" onPress={() => void signOut()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  code: { fontSize: 34, fontWeight: '900', letterSpacing: 6, color: colors.primary },
  childName: { fontSize: fontSize.body, fontWeight: '800', color: colors.text },
  option: {
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: spacing.md,
    minHeight: MIN_TAP,
    gap: spacing.xs,
  },
  optionOn: { borderColor: colors.primary, borderWidth: 3 },
  optionLabel: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
  optionDetail: { fontSize: 14, color: colors.textMuted, lineHeight: 20 },
  alertBox: {
    backgroundColor: '#FFF1EC',
    borderWidth: 2,
    borderColor: colors.danger,
    borderRadius: radius.sm,
    padding: spacing.md,
    gap: spacing.xs,
  },
  alertTitle: { fontSize: fontSize.label, fontWeight: '800', color: colors.danger },
  alertNote: { fontSize: 13, color: colors.textMuted, lineHeight: 18 },
  alertLine: { fontSize: 14, color: colors.text, lineHeight: 22 },
  activityLine: { fontSize: 14, color: colors.text, lineHeight: 22 },
  input: {
    minHeight: MIN_TAP,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    fontSize: fontSize.body,
    color: colors.text,
    backgroundColor: colors.surface,
  },
});
