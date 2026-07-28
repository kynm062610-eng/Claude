import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { BigButton, Body, Card, Screen, Title } from '../../src/components/ui';
import { supabase } from '../../src/lib/supabase';
import { useSession } from '../../src/lib/session';
import { CONSENT_VERSION, consentSummary } from '../../src/consent';
import { colors, fontSize, radius, spacing } from '../../src/theme';

/**
 * 保護者の登録。
 *
 * ここで取得する同意は、法が求める「①保護者の同意」に当たる（docs/01-safety-and-privacy.md）。
 * 同意した文言のバージョンと日時を必ず保存する。
 * この同意は「保護者が中身を読む」こととは別で、閲覧は既定 off のまま始まる。
 */
export default function GuardianOnboarding() {
  const { refresh } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data, error: signUpError } = await supabase.auth.signUp({ email, password });
      if (signUpError) throw signUpError;

      const userId = data.user?.id ?? (await supabase.auth.getUser()).data.user?.id;
      if (!userId) throw new Error('登録に失敗しました。もう一度お試しください。');

      const { error: insertError } = await supabase.from('guardians').insert({
        id: userId,
        email,
        consent_version: CONSENT_VERSION,
        consented_at: new Date().toISOString(),
      });
      if (insertError) throw insertError;

      await refresh();
      router.replace('/guardian/console');
    } catch (e) {
      setError(e instanceof Error ? e.message : '登録に失敗しました');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>おうちの人の とうろく</Title>
      <Body muted>
        お子さまの利用にあたって、保護者の方の同意が必要です。登録後、お子さま用の
        リンクコードを発行します。
      </Body>

      <Card>
        <Text style={styles.label}>メールアドレス</Text>
        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          textContentType="emailAddress"
          placeholder="you@example.com"
        />
        <Text style={styles.label}>パスワード</Text>
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="newPassword"
          placeholder="8文字以上"
        />
      </Card>

      <Card>
        <Text style={styles.label}>同意事項（{CONSENT_VERSION}）</Text>
        {consentSummary.map((line) => (
          <Text key={line} style={styles.consentLine}>
            ・{line}
          </Text>
        ))}
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: agreed }}
          onPress={() => setAgreed((v) => !v)}
          style={styles.checkboxRow}
        >
          <View style={[styles.checkbox, agreed && styles.checkboxOn]}>
            {agreed && <Text style={styles.checkMark}>✓</Text>}
          </View>
          <Text style={styles.checkboxLabel}>上記に同意します</Text>
        </Pressable>
      </Card>

      {error && <Text style={styles.error}>{error}</Text>}

      <BigButton
        label="とうろくする"
        onPress={submit}
        disabled={!agreed || email.length === 0 || password.length < 8}
        loading={busy}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
  input: {
    minHeight: 52,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    fontSize: fontSize.body,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  consentLine: { fontSize: fontSize.label, lineHeight: 24, color: colors.textMuted },
  checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minHeight: 56 },
  checkbox: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  checkboxOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkMark: { color: colors.primaryText, fontWeight: '900', fontSize: 20 },
  checkboxLabel: { fontSize: fontSize.body, color: colors.text },
  error: { color: colors.danger, fontSize: fontSize.label },
});
