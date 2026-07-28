/**
 * 判定前の正規化。
 *
 * 「し ね」「シネ」「しーね」のような書き換えで検知を抜けられないようにする。
 * 完全に防ぐことはできないが、小学生が思いつく程度の回避には対応する。
 */

/** 全角英数を半角に */
function toHalfWidth(input: string): string {
  return input.replace(/[Ａ-Ｚａ-ｚ０-９]/g, (ch) =>
    String.fromCharCode(ch.charCodeAt(0) - 0xfee0),
  );
}

/** カタカナをひらがなに（半角カナは対象外） */
function katakanaToHiragana(input: string): string {
  return input.replace(/[ァ-ヶ]/g, (ch) =>
    String.fromCharCode(ch.charCodeAt(0) - 0x60),
  );
}

/** 記号・空白・長音・繰り返し記号を落とす */
function stripFillers(input: string): string {
  return input.replace(/[\s　ー~〜・.,!?！？。、「」『』()（）*＊_＿\-]/g, '');
}

/** 同じ文字の 3 回以上の連続を 1 文字に潰す（「しーーーね」「ばかああ」対策） */
function collapseRepeats(input: string): string {
  return input.replace(/(.)\1{2,}/g, '$1');
}

export function normalizeForMatch(input: string): string {
  return collapseRepeats(stripFillers(katakanaToHiragana(toHalfWidth(input.toLowerCase()))));
}
