import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../../src/components/ui';
import { fetchMyProfile, raiseSafetyAlert, saveMyProfile } from '../../src/api';
import { checkPageTexts } from '../../src/moderation';
import { useSession } from '../../src/lib/session';
import { useUiText } from '../../src/lib/uiText';
import { profileCategories, questionsByCategory } from '../../src/data/profileQuestions';
import { MIN_TAP, colors, fontSize, radius, spacing } from '../../src/theme';
import type { ProfileAnswers } from '../../src/types';

/**
 * プロフィールの編集。
 *
 * 全問 任意回答。自由入力の欄は、ページ投稿と同じ NG ワード・個人情報チェックを
 * 保存前に通す（誰かに見られる文章のため）。選択肢式の質問は語彙が固定なので
 * チェック対象にしない。
 */
export default function EditProfile() {
  const { child } = useSession();
  const { t } = useUiText();
  const [answers, setAnswers] = useState<ProfileAnswers>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!child) return;
    (async () => {
      try {
        const profile = await fetchMyProfile(child.id);
        setAnswers(profile?.answers ?? {});
      } finally {
        setLoading(false);
      }
    })();
  }, [child]);

  if (!child || loading) return <Loading />;

  const setAnswer = (questionId: string, value: string) => {
    setAnswers((prev) => {
      const next = { ...prev };
      if (value.trim().length === 0) {
        delete next[questionId];
      } else {
        next[questionId] = value;
      }
      return next;
    });
  };

  const save = async () => {
    // 自由入力の欄だけを検査する（選択肢式は語彙が固定で安全なため対象外）。
    const allQuestions = profileCategories.flatMap((c) => questionsByCategory(c.key));
    const freeTexts = allQuestions
      .filter((q) => !q.options)
      .map((q) => answers[q.id])
      .filter((v): v is string => !!v && v.trim().length > 0);

    const result = checkPageTexts(freeTexts);

    if (result.notifyGuardian) {
      const categories = [...new Set(result.findings.map((f) => f.category))];
      await Promise.all(categories.map((c) => raiseSafetyAlert(c).catch(() => undefined)));
    }

    if (result.severity === 'block') {
      Alert.alert(t('ちょっと まって', 'ちょっと待って'), result.message ? t(result.message.kana, result.message.kanji) : '');
      return;
    }

    const doSave = async () => {
      setSaving(true);
      try {
        await saveMyProfile(answers);
        router.back();
      } catch {
        Alert.alert(
          t('ほぞんできなかったよ', '保存できなかったよ'),
          t('もういちど ためしてみてね。', 'もう一度試してみてね。'),
        );
      } finally {
        setSaving(false);
      }
    };

    if (result.severity === 'warn') {
      Alert.alert(t('かくにん', '確認'), result.message ? t(result.message.kana, result.message.kanji) : '', [
        { text: t('なおす', '直す'), style: 'cancel' },
        { text: t('このまま ほぞん', 'このまま保存'), onPress: () => void doSave() },
      ]);
      return;
    }

    await doSave();
  };

  return (
    <Screen>
      <Title>{t('プロフィール', 'プロフィール')}</Title>
      <Body muted>
        {t(
          'ぜんぶ こたえなくて だいじょうぶ。こたえたいものだけ かいてね。',
          '全部答えなくて大丈夫。答えたいものだけ書いてね。',
        )}
      </Body>

      {profileCategories.map((category) => (
        <Card key={category.key}>
          <Text style={styles.categoryTitle}>{t(category.kana, category.kanji)}</Text>
          {questionsByCategory(category.key).map((q) => (
            <View key={q.id} style={styles.questionBlock}>
              <Text style={styles.questionLabel}>{t(q.kana, q.kanji)}</Text>
              {q.options ? (
                <View style={styles.optionRow}>
                  {q.options.map((option) => (
                    <Pressable
                      key={option}
                      accessibilityRole="button"
                      accessibilityState={{ selected: answers[q.id] === option }}
                      onPress={() => setAnswer(q.id, answers[q.id] === option ? '' : option)}
                      style={[styles.option, answers[q.id] === option && styles.optionOn]}
                    >
                      <Text
                        style={[styles.optionText, answers[q.id] === option && styles.optionTextOn]}
                      >
                        {option}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              ) : (
                <TextInput
                  style={styles.input}
                  value={answers[q.id] ?? ''}
                  onChangeText={(value) => setAnswer(q.id, value)}
                  placeholder={q.placeholder ? t(q.placeholder.kana, q.placeholder.kanji) : undefined}
                  placeholderTextColor={colors.textMuted}
                  maxLength={60}
                />
              )}
            </View>
          ))}
        </Card>
      ))}

      <BigButton label={t('ほぞんする', '保存する')} onPress={save} loading={saving} />
      <BigButton label={t('やめる', 'やめる')} variant="secondary" onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  categoryTitle: { fontSize: fontSize.body, fontWeight: '800', color: colors.primary },
  questionBlock: { gap: spacing.xs },
  questionLabel: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
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
  optionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  option: {
    minHeight: MIN_TAP,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionOn: { borderColor: colors.primary, backgroundColor: colors.primary },
  optionText: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
  optionTextOn: { color: colors.primaryText },
});
