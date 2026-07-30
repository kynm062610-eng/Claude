/**
 * 週替わりの質問。
 *
 * 「今日のお題」（日替わり）とは別枠。プロフィールが固定だと飽きるのと同じで、
 * お題も日替わりだけだと流れてしまうため、1 週間じっくり考えられる問いを置く。
 *
 * 質問を作るときの原則（今日のお題と同じ）:
 *   - 家庭環境の差が出るもの（旅行、習い事、持ち物の値段）は避ける
 *   - 見た目や成績を比べさせない
 *   - 答えなくても気まずくならない問いにする
 *
 * 「最近泣いた？」は、共有ノートで公開質問にすると冷やかしの材料になりうるので、
 * 「ちょっと悲しかったこと」という答えやすい形に置き換えている。
 */
export type WeeklyQuestion = { kana: string; kanji: string };

export const weeklyQuestions: WeeklyQuestion[] = [
  { kana: 'こんげつ いちばん わらったことは？', kanji: '今月一番笑ったことは？' },
  { kana: 'きょうの きぶんを えもじ3つで！', kanji: '今日の気分を絵文字3つで！' },
  { kana: 'いま きいている きょくは？', kanji: '今聴いている曲は？' },
  { kana: 'いまの きもちを ひとことで', kanji: '今の気持ちをひとことで' },
  { kana: 'ことし ちょうせんしたいことは？', kanji: '今年挑戦したいことは？' },
  { kana: 'さいきん ちょっと かなしかったことは？', kanji: '最近ちょっと悲しかったことは？' },
  { kana: 'こんしゅう いちばん がんばったことは？', kanji: '今週一番がんばったことは？' },
  { kana: 'いま いちばん ほしいものは？', kanji: '今一番ほしいものは？' },
  { kana: 'さいきん おぼえた ことばや わざは？', kanji: '最近覚えた言葉や技は？' },
  { kana: 'こんしゅうの じぶんに はなまるを あげるなら どこに？', kanji: '今週の自分に花丸をあげるならどこに？' },
  { kana: 'さいきん やさしくされて うれしかったことは？', kanji: '最近やさしくされて嬉しかったことは？' },
  { kana: 'いま はまっている ものを 3つ', kanji: '今はまっているものを3つ' },
  { kana: 'こんど やってみたい あそびは？', kanji: '今度やってみたい遊びは？' },
  { kana: 'さいきん「ありがとう」と おもったことは？', kanji: '最近「ありがとう」と思ったことは？' },
];

/**
 * 月曜日始まりの通し週番号。
 * 1970-01-01 は木曜なので 3 日ぶんずらして週の境界を月曜に合わせる。
 */
export function weekIndexOf(date: Date): number {
  const days = Math.floor(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86_400_000,
  );
  return Math.floor((days + 3) / 7);
}

/**
 * その週の質問を返す。
 * グループ内の全員に同じ質問が出るよう、乱数ではなく週番号を種にする。
 */
export function questionOfTheWeek(date = new Date()): WeeklyQuestion {
  const index = weekIndexOf(date);
  // 負の週番号（1970 年より前）でも配列の範囲に収まるようにする
  const safeIndex = ((index % weeklyQuestions.length) + weeklyQuestions.length) % weeklyQuestions.length;
  return weeklyQuestions[safeIndex];
}
