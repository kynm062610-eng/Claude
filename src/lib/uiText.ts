import { useCallback } from 'react';
import { useChild } from './session';

/**
 * ひらがな中心の表示と、かんじを含む表示を切り替える。
 *
 * 中学生・高校生が使う場合を想定し、`children.furigana_enabled` を
 * 「ひらがな優先モードかどうか」として流用する（既定 true = ひらがな）。
 * 保護者向け画面は元々ふつうの日本語（漢字入り）なので対象にしない。
 */
export function useUiText() {
  const child = useChild();
  const useKana = child?.furigana_enabled ?? true;

  const t = useCallback((kana: string, kanji: string) => (useKana ? kana : kanji), [useKana]);

  return { t, useKana };
}
