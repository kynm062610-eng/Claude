import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { BigButton, Body, Card, Loading, Screen, Title } from '../../src/components/ui';
import { fetchMyProfile } from '../../src/api';
import { useSession } from '../../src/lib/session';
import { useUiText } from '../../src/lib/uiText';
import { profileCategories, profileQuestions } from '../../src/data/profileQuestions';
import { colors, fontSize, spacing } from '../../src/theme';
import type { ProfileAnswers } from '../../src/types';

/**
 * プロフィールの閲覧（本人の分も、グループの仲間の分もここで見る）。
 * 答えていない質問は表示しない。全て未回答なら「まだ なにも かいていない」を出す。
 */
export default function ViewProfile() {
  const { childId } = useLocalSearchParams<{ childId: string }>();
  const { child } = useSession();
  const { t } = useUiText();
  const [answers, setAnswers] = useState<ProfileAnswers | null>(null);
  const [loading, setLoading] = useState(true);

  const isMine = childId === child?.id;

  useEffect(() => {
    if (!childId) return;
    (async () => {
      setLoading(true);
      try {
        const profile = await fetchMyProfile(childId);
        setAnswers(profile?.answers ?? {});
      } finally {
        setLoading(false);
      }
    })();
  }, [childId]);

  if (loading || !child) return <Loading />;

  const hasAnyAnswer = answers && Object.keys(answers).length > 0;

  return (
    <Screen>
      <Title>{t('プロフィール', 'プロフィール')}</Title>

      {!hasAnyAnswer && (
        <Card>
          <Body muted>
            {t('まだ なにも かいていないよ。', 'まだ何も書いていないよ。')}
          </Body>
        </Card>
      )}

      {profileCategories.map((category) => {
        const questions = profileQuestions.filter(
          (q) => q.category === category.key && answers?.[q.id],
        );
        if (questions.length === 0) return null;
        return (
          <Card key={category.key}>
            <Text style={styles.categoryTitle}>{t(category.kana, category.kanji)}</Text>
            {questions.map((q) => (
              <View key={q.id} style={styles.row}>
                <Text style={styles.label}>{t(q.kana, q.kanji)}</Text>
                <Text style={styles.answer}>{answers?.[q.id]}</Text>
              </View>
            ))}
          </Card>
        );
      })}

      {isMine && (
        <BigButton label={t('プロフィールを へんしゅう', 'プロフィールを編集')} onPress={() => router.push('/profile/edit')} />
      )}
      <BigButton label={t('もどる', '戻る')} variant="secondary" onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  categoryTitle: { fontSize: fontSize.body, fontWeight: '800', color: colors.primary },
  row: { gap: spacing.xs },
  label: { fontSize: fontSize.label, color: colors.textMuted, fontWeight: '700' },
  answer: { fontSize: fontSize.body, color: colors.text },
});
