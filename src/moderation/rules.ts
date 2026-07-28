/**
 * NG ワードと個人情報パターンの定義。
 *
 * 語彙リストは完全ではないし、完全にはなりえない。これは「言い直す機会を作る」ための
 * 仕組みであって、いじめを検出しきる装置ではない。通報導線と運営のモデレーションが本体で、
 * ここはその手前の一次フィルタ。
 */

export type ModerationCategory =
  | 'violence' // 死ね・殺す など
  | 'exclusion' // なかまはずれ・グループ抜けて など
  | 'insult' // ばか・きもい など
  | 'personal_info'; // 電話番号・住所・学校名 など

/**
 * 判定語。素の日本語で書いてよい。
 * 照合時に `normalizeForMatch` を通してから比較するため、ここで正規化しておく必要はない。
 */
export const wordRules: { category: ModerationCategory; words: string[] }[] = [
  {
    category: 'violence',
    words: ['しね', '死ね', 'ころす', '殺す', 'きえろ', '消えろ', 'じさつ', 'なぐる', '殴る'],
  },
  {
    category: 'exclusion',
    words: [
      'なかまはずれ',
      '仲間はずれ',
      'むしよう',
      'むしする',
      'はぶる',
      'グループぬけて',
      'ぐるーぷぬけて',
      'もうともだちじゃない',
      'ともだちやめる',
      'こなくていい',
    ],
  },
  {
    category: 'insult',
    words: [
      'ばか',
      'あほ',
      'きもい',
      'うざい',
      'ぶす',
      'でぶ',
      'くそ',
      'まぬけ',
      'さいてい',
      'よわむし',
    ],
  },
];

/** 個人情報らしき文字列。保護者には通知せず、本人への注意喚起にとどめる。 */
export const personalInfoPatterns: { key: string; pattern: RegExp }[] = [
  // 電話番号（ハイフンあり・なし両方）
  { key: 'phone', pattern: /0\d{1,4}-?\d{1,4}-?\d{3,4}/ },
  // 郵便番号
  { key: 'postal', pattern: /〒?\d{3}-?\d{4}(?!\d)/ },
  // 住所らしき表記
  { key: 'address', pattern: /[0-9０-９]+(丁目|番地|号室)/ },
  // 学校名
  { key: 'school', pattern: /.{1,10}(小学校|しょうがっこう)/ },
  // メールアドレス
  { key: 'email', pattern: /[\w.+-]+@[\w-]+\.[\w.-]+/ },
  // URL
  { key: 'url', pattern: /https?:\/\/\S+/ },
  // SNS の ID 交換
  { key: 'sns_id', pattern: /(line|らいん|インスタ|いんすた|tiktok)\s*(id|ID|あいでぃー)?[:：]?\s*\S+/i },
];

/** カテゴリごとの扱い。`01-safety-and-privacy.md` の安全フロアに対応する。 */
export const categoryPolicy: Record<
  ModerationCategory,
  { severity: 'warn' | 'block'; notifyGuardian: boolean; message: string }
> = {
  violence: {
    severity: 'block',
    notifyGuardian: true,
    message: 'この ことばは、よまれた ひとが とても かなしく なっちゃうかも。べつの いいかたに してみよう。',
  },
  exclusion: {
    severity: 'block',
    notifyGuardian: true,
    message: 'なかまはずれに きこえる ことばが あるみたい。ほんとうに つたえたいことは なにかな？',
  },
  insult: {
    severity: 'warn',
    notifyGuardian: false,
    message: 'ちょっと きつい ことばが あるかも。やさしい いいかたに かえられそう？',
  },
  personal_info: {
    severity: 'warn',
    notifyGuardian: false,
    message:
      'でんわばんごう や じゅうしょ、がっこうの なまえは かかないほうが あんしんだよ。けしてから おくろう。',
  },
};
