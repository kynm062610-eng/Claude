/**
 * NG ワードと個人情報パターンの定義。
 *
 * 語彙リストは完全ではないし、完全にはなりえない。これは「言い直す機会を作る」ための
 * 仕組みであって、いじめを検出しきる装置ではない。通報導線と運営のモデレーションが本体で、
 * ここはその手前の一次フィルタ。
 */

export type ModerationCategory =
  | 'violence' // 死ね・殺す など、人に向けた攻撃的な表現
  | 'self_harm' // 死にたい・消えたい など、本人の自傷リスクを示す表現
  | 'exclusion' // なかまはずれ・グループ抜けて など
  | 'insult' // ばか・きもい など
  | 'personal_info'; // 電話番号・住所・学校名 など

/**
 * 判定語。素の日本語で書いてよい。
 * 照合時に `normalizeForMatch` を通してから比較するため、ここで正規化しておく必要はない。
 */
export const wordRules: { category: ModerationCategory; words: string[] }[] = [
  {
    // 単独の「死ん」「しん」を語根登録すると「おじいちゃんが死んでかなしかった」
    // のような、いじめでも自傷でもない文章まで誤ってブロックしてしまう。
    // なので活用形は「攻撃的な言い回しのまとまり」でのみ拾う。
    category: 'violence',
    words: [
      'しね',
      '死ね',
      'しねよ',
      '死ねよ',
      'しねばいいのに',
      '死ねばいいのに',
      'しんでしまえ',
      '死んでしまえ',
      'しんじゃえ',
      '死んじゃえ',
      'しんでほしい',
      '死んでほしい',
      'ころす',
      '殺す',
      'ぶっころす',
      'きえろ',
      '消えろ',
      'きえてほしい',
      '消えてほしい',
      'きえてしまえ',
      '消えてしまえ',
      'なぐる',
      '殴る',
    ],
  },
  {
    // 「死にたい」などは他人への攻撃ではなく、本人が助けを求めているサイン。
    // 「言い直そう」という扱いにはせず、別カテゴリとして必ず保護者に伝える。
    category: 'self_harm',
    words: [
      'しにたい',
      '死にたい',
      'しのう',
      '死のう',
      'きえたい',
      '消えたい',
      'いなくなりたい',
      'じさつ',
      'いきてるいみない',
      'いきているいみがない',
    ],
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
      // 「死んでは」のような断片は、それ単体では攻撃とも自傷とも言い切れず、
      // 「おじいちゃんが死んでかなしかった」のような文章とも地続きになる。
      // 強制ブロックにはせず、いったん立ち止まって確認できる warn 止まりにする。
      // 明確に攻撃的な言い回し（死んでしまえ 等）は上の violence 側で block される。
      'しんで',
      '死んで',
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
  self_harm: {
    severity: 'block',
    notifyGuardian: true,
    message:
      'つらい きもちを かかえて いるのかな。ひとりで がんばらなくて だいじょうぶだよ。\nおうちの人や せんせいに、いま の きもちを はなしてみてね。',
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
