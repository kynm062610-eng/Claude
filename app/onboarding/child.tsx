import React, { useState } from 'react';
import { StyleSheet, Text, TextInput } from 'react-native';
import { router } from 'expo-router';
import { BigButton, Body, Card, Screen, Title } from '../../src/components/ui';
import { supabase } from '../../src/lib/supabase';
import { useSession } from '../../src/lib/session';
import { claimChildProfile } from '../../src/api';
import { colors, fontSize, radius, spacing } from '../../src/theme';

/**
 * 子ども端末のセットアップ。
 *
 * 子どもはメールアドレスを持たない前提なので、匿名サインインでこの端末専用の
 * auth ユーザーを作り、保護者が発行した 8 文字のリンクコードでプロフィールを受け取る。
 * 保護者とセッションを分けることで、見まもりモード off を RLS で本当に閉じられる。
 */
export default function ChildOnboarding() {
  const { refresh } = useSession();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        const { error: signInError } = await supabase.auth.signInAnonymously();
        if (signInError) throw signInError;
      }

      await claimChildProfile(code);
      await refresh();
      router.replace('/home');
    } catch (e) {
      const message = e instanceof Error ? e.message : '';
      setError(
        message.includes('link_code_invalid')
          ? 'コードが ちがうみたい。もういちど かくにんしてみよう。'
          : 'うまく いかなかったよ。もういちど ためしてみてね。',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>コードを いれてね</Title>
      <Body>おうちの人が おしえてくれた 8もじの コードを いれてね。</Body>

      <Card>
        <TextInput
          style={styles.codeInput}
          value={code}
          onChangeText={(t) => setCode(t.toUpperCase())}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={8}
          placeholder="ABCD2345"
          placeholderTextColor={colors.textMuted}
        />
      </Card>

      {error && <Text style={styles.error}>{error}</Text>}

      <BigButton label="はじめる" onPress={submit} disabled={code.length !== 8} loading={busy} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  codeInput: {
    minHeight: 72,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.md,
    textAlign: 'center',
    fontSize: 36,
    letterSpacing: 8,
    fontWeight: '800',
    color: colors.text,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
  },
  error: { color: colors.danger, fontSize: fontSize.label },
});
