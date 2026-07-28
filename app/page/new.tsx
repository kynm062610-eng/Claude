import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BigButton } from '../../src/components/ui';
import { DrawingCanvas, type Tool } from '../../src/features/canvas/DrawingCanvas';
import { raiseSafetyAlert, submitPage } from '../../src/api';
import { checkPageTexts } from '../../src/moderation';
import { promptOfTheDay } from '../../src/data/prompts';
import { backgrounds, stamps } from '../../src/data/assets';
import { useSession } from '../../src/lib/session';
import { isQuietHours, quietHoursMessage } from '../../src/utils/quietHours';
import { MIN_TAP, colors, fontSize, penColors, penWidths, radius, spacing } from '../../src/theme';
import { emptyPageContent, type PageContent } from '../../src/types';

export default function NewPage() {
  const { notebookId } = useLocalSearchParams<{ notebookId: string }>();
  const { child } = useSession();
  const [content, setContent] = useState<PageContent>(() => emptyPageContent('dots'));
  const [tool, setTool] = useState<Tool>({ kind: 'pen', color: penColors[0], width: penWidths[1] });
  const [draftText, setDraftText] = useState('');
  const [usePrompt, setUsePrompt] = useState(false);
  const [busy, setBusy] = useState(false);

  const prompt = useMemo(() => promptOfTheDay(), []);

  const addText = () => {
    const text = draftText.trim();
    if (text.length === 0) return;
    const existingTexts = content.elements.filter((el) => el.type === 'text').length;
    setContent({
      ...content,
      elements: [
        ...content.elements,
        {
          type: 'text',
          text,
          x: 80,
          y: 80 + existingTexts * 90,
          size: 40,
          color: colors.text,
        },
      ],
    });
    setDraftText('');
  };

  const submit = async () => {
    if (!notebookId || !child) return;

    if (isQuietHours(new Date(), child.quiet_hours_start, child.quiet_hours_end)) {
      Alert.alert('おやすみ じかん', quietHoursMessage(child.quiet_hours_start, child.quiet_hours_end));
      return;
    }

    // 投稿前の検査。見まもりモードの値に関係なく必ず走る（安全フロア）。
    const texts = content.elements
      .filter((el): el is Extract<typeof el, { type: 'text' }> => el.type === 'text')
      .map((el) => el.text);
    const result = checkPageTexts(texts);

    if (result.notifyGuardian) {
      // 本文は送らない。カテゴリだけを記録する。
      const categories = [...new Set(result.findings.map((f) => f.category))];
      await Promise.all(categories.map((c) => raiseSafetyAlert(c).catch(() => undefined)));
    }

    if (result.severity === 'block') {
      Alert.alert('ちょっと まって', result.message ?? '');
      return;
    }

    const send = async () => {
      setBusy(true);
      try {
        await submitPage({
          notebookId,
          content,
          promptText: usePrompt ? prompt : null,
        });
        router.replace(`/notebook/${notebookId}`);
      } catch (e) {
        const message = e instanceof Error ? e.message : '';
        Alert.alert(
          'おくれなかったよ',
          message.includes('not_your_turn')
            ? 'いまは じぶんの ばんじゃ ないみたい。'
            : 'もういちど ためしてみてね。',
        );
      } finally {
        setBusy(false);
      }
    };

    if (result.severity === 'warn') {
      Alert.alert('かくにん', result.message ?? '', [
        { text: 'なおす', style: 'cancel' },
        { text: 'このまま おくる', onPress: () => void send() },
      ]);
      return;
    }

    await send();
  };

  return (
    <SafeAreaView style={styles.screen} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable style={styles.promptCard} onPress={() => setUsePrompt((v) => !v)}>
          <Text style={styles.promptLabel}>きょうの おだい {usePrompt ? '✓' : ''}</Text>
          <Text style={styles.promptText}>{prompt}</Text>
        </Pressable>

        <DrawingCanvas content={content} onChange={setContent} tool={tool} />

        <View style={styles.toolRow}>
          {penColors.map((color) => (
            <Pressable
              key={color}
              accessibilityRole="button"
              accessibilityLabel={`いろ ${color}`}
              onPress={() => setTool({ kind: 'pen', color, width: tool.kind === 'pen' ? tool.width : penWidths[1] })}
              style={[
                styles.swatch,
                { backgroundColor: color },
                tool.kind === 'pen' && tool.color === color && styles.swatchSelected,
              ]}
            />
          ))}
        </View>

        <View style={styles.toolRow}>
          {penWidths.map((width) => (
            <Pressable
              key={width}
              accessibilityRole="button"
              accessibilityLabel={`ふとさ ${width}`}
              onPress={() =>
                setTool({ kind: 'pen', color: tool.kind === 'pen' ? tool.color : penColors[0], width })
              }
              style={[styles.toolChip, tool.kind === 'pen' && tool.width === width && styles.toolChipOn]}
            >
              <View style={{ width: width * 1.4, height: width * 1.4, borderRadius: width, backgroundColor: colors.text }} />
            </Pressable>
          ))}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="ひとつ もどす"
            onPress={() => setTool({ kind: 'eraser' })}
            style={[styles.toolChip, tool.kind === 'eraser' && styles.toolChipOn]}
          >
            <Text style={styles.toolChipText}>けす</Text>
          </Pressable>
        </View>
        {tool.kind === 'eraser' && (
          <Text style={styles.hint}>キャンバスを タップすると、さいごに かいたものが きえるよ。</Text>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.stampRow}>
          {stamps.map((stamp) => (
            <Pressable
              key={stamp.key}
              accessibilityRole="button"
              accessibilityLabel={`すたんぷ ${stamp.key}`}
              onPress={() => setTool({ kind: 'stamp', stampKey: stamp.key })}
              style={[
                styles.stamp,
                tool.kind === 'stamp' && tool.stampKey === stamp.key && styles.toolChipOn,
              ]}
            >
              <Text style={styles.stampEmoji}>{stamp.emoji}</Text>
            </Pressable>
          ))}
        </ScrollView>
        {tool.kind === 'stamp' && (
          <Text style={styles.hint}>キャンバスを タップすると スタンプが はれるよ。</Text>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.stampRow}>
          {backgrounds.map((background) => (
            <Pressable
              key={background.key}
              accessibilityRole="button"
              accessibilityLabel={`はいけい ${background.label}`}
              onPress={() => setContent({ ...content, background: background.key })}
              style={[
                styles.background,
                { backgroundColor: background.color },
                content.background === background.key && styles.swatchSelected,
              ]}
            >
              <Text style={styles.backgroundLabel}>{background.label}</Text>
            </Pressable>
          ))}
        </ScrollView>

        <View style={styles.textRow}>
          <TextInput
            style={styles.textInput}
            value={draftText}
            onChangeText={setDraftText}
            placeholder="もじを かく"
            placeholderTextColor={colors.textMuted}
            maxLength={80}
          />
          <Pressable
            accessibilityRole="button"
            onPress={addText}
            style={[styles.toolChip, styles.addTextButton]}
          >
            <Text style={styles.toolChipText}>いれる</Text>
          </Pressable>
        </View>

        <BigButton label="おくる" onPress={submit} loading={busy} />
        <BigButton label="やめる" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.md, gap: spacing.md },
  promptCard: {
    backgroundColor: '#FFF4D6',
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.turnBadge,
    padding: spacing.md,
    gap: spacing.xs,
  },
  promptLabel: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
  promptText: { fontSize: fontSize.body, color: colors.text },
  toolRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, alignItems: 'center' },
  swatch: { width: MIN_TAP, height: MIN_TAP, borderRadius: radius.pill, borderWidth: 3, borderColor: 'transparent' },
  swatchSelected: { borderColor: colors.text },
  toolChip: {
    minWidth: MIN_TAP,
    minHeight: MIN_TAP,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  toolChipOn: { borderColor: colors.primary, borderWidth: 3 },
  toolChipText: { fontSize: fontSize.label, fontWeight: '800', color: colors.text },
  stampRow: { gap: spacing.sm, paddingVertical: spacing.xs },
  stamp: {
    width: MIN_TAP + 8,
    height: MIN_TAP + 8,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stampEmoji: { fontSize: 30 },
  background: {
    minWidth: 84,
    height: MIN_TAP,
    borderRadius: radius.md,
    borderWidth: 3,
    borderColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backgroundLabel: { fontSize: fontSize.label, fontWeight: '700', color: colors.text },
  textRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center' },
  textInput: {
    flex: 1,
    minHeight: MIN_TAP,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    fontSize: fontSize.body,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  addTextButton: { backgroundColor: colors.accent, borderColor: colors.accent },
  hint: { fontSize: fontSize.label, color: colors.textMuted },
});
