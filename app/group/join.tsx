import React, { useState } from 'react';
import { StyleSheet, Text, TextInput } from 'react-native';
import { router } from 'expo-router';
import { BigButton, Body, Card, Screen, Title } from '../../src/components/ui';
import { createGroup, joinGroupByCode } from '../../src/api';
import { useUiText } from '../../src/lib/uiText';
import { colors, fontSize, radius, spacing } from '../../src/theme';

export default function JoinGroup() {
  const { t } = useUiText();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const join = async () => {
    setBusy(true);
    setError(null);
    try {
      const groupId = await joinGroupByCode(code);
      router.replace(`/group/${groupId}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : '';
      setError(
        message.includes('group_full')
          ? t('この グループは いっぱいだよ（6にんまで）。', 'このグループはいっぱいだよ（6人まで）。')
          : message.includes('invite_code_invalid')
            ? t('あいことばが ちがうみたい。もういちど かくにんしてね。', '合言葉が違うみたい。もう一度確認してね。')
            : t('うまく いかなかったよ。もういちど ためしてみてね。', 'うまくいかなかったよ。もう一度試してみてね。'),
      );
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const groupId = await createGroup(name.trim());
      router.replace(`/group/${groupId}`);
    } catch {
      setError(t('うまく いかなかったよ。もういちど ためしてみてね。', 'うまくいかなかったよ。もう一度試してみてね。'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>{t('あいことばで はいる', '合言葉で入る')}</Title>
      <Card>
        <TextInput
          style={styles.codeInput}
          value={code}
          onChangeText={(value) => setCode(value.toUpperCase())}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={6}
          placeholder="ABC234"
          placeholderTextColor={colors.textMuted}
        />
      </Card>
      <BigButton label={t('はいる', '入る')} onPress={join} disabled={code.length !== 6} loading={busy} />

      <Title>{t('あたらしく つくる', '新しく作る')}</Title>
      <Body muted>{t('グループは 6にんまで はいれるよ。', 'グループは6人まで入れるよ。')}</Body>
      <Card>
        <TextInput
          style={styles.nameInput}
          value={name}
          onChangeText={setName}
          maxLength={30}
          placeholder={t('グループの なまえ', 'グループの名前')}
          placeholderTextColor={colors.textMuted}
        />
      </Card>
      <BigButton
        label={t('つくる', '作る')}
        variant="secondary"
        onPress={create}
        disabled={name.trim().length === 0}
        loading={busy}
      />

      {error && <Text style={styles.error}>{error}</Text>}
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
  },
  nameInput: {
    minHeight: 56,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    fontSize: fontSize.body,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  error: { color: colors.danger, fontSize: fontSize.label },
});
