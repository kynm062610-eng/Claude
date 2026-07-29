/**
 * プロフィールの質問。
 *
 * あえて用意しない項目（docs/01-safety-and-privacy.md の方針）:
 *   - 居住地・生年月日（個人特定につながる）
 *   - 写真（カメラ・画像アップロードを持たない設計そのもの）
 *   - 恋愛・デートに関する質問（悪意ある大人を引き寄せる要因になる）
 *   - 「一番恥ずかしかった出来事」のような、答えを引き出す圧力が
 *     いじめの材料になりうる質問
 *
 * 全問 任意回答。空欄のままでよい。
 */
export type ProfileQuestion = {
  id: string;
  category: string;
  kana: string;
  kanji: string;
  /** 選択肢式（options あり）の質問には不要 */
  placeholder?: { kana: string; kanji: string };
  /** これがある質問は選択肢式（自由入力より安全で、答えやすい） */
  options?: string[];
};

export const profileCategories: { key: string; kana: string; kanji: string }[] = [
  { key: 'basic', kana: 'きほん', kanji: '基本' },
  { key: 'personality', kana: 'せいかく', kanji: '性格' },
  { key: 'likes', kana: 'すきなもの', kanji: '好きなもの' },
  { key: 'diary', kana: 'にっきが たのしくなる しつもん', kanji: '日記が楽しくなる質問' },
  { key: 'fun', kana: 'おもしろい しつもん', kanji: '面白い質問' },
  { key: 'friend', kana: 'なかよくなる しつもん', kanji: '仲良くなる質問' },
];

export const profileQuestions: ProfileQuestion[] = [
  // きほん
  {
    id: 'nickname_call',
    category: 'basic',
    kana: 'よんでほしい なまえ',
    kanji: '呼んでほしい名前',
    placeholder: { kana: 'たとえば：〇〇ちゃん', kanji: '例：〇〇ちゃん' },
  },
  {
    id: 'comment',
    category: 'basic',
    kana: 'ひとこと コメント',
    kanji: 'ひとことコメント',
    placeholder: { kana: 'じこしょうかい を どうぞ！', kanji: '自己紹介をどうぞ！' },
  },

  // せいかく
  {
    id: 'three_words',
    category: 'personality',
    kana: 'じぶんを 3つの ことばで あらわすなら？',
    kanji: '自分を3つの言葉で表すなら？',
    placeholder: { kana: 'たとえば：げんき・のんびり・わらいじょうご', kanji: '例：元気・のんびり・笑い上戸' },
  },
  {
    id: 'morning_or_night',
    category: 'personality',
    kana: 'あさがた？ よるがた？',
    kanji: '朝型？夜型？',
    options: ['あさがた', 'よるがた', 'どちらでもない'],
  },
  {
    id: 'indoor_or_outdoor',
    category: 'personality',
    kana: 'インドアは？ アウトドアは？',
    kanji: 'インドア派？アウトドア派？',
    options: ['インドア', 'アウトドア', 'どちらもすき'],
  },
  {
    id: 'shy',
    category: 'personality',
    kana: 'ひとみしり する？',
    kanji: '人見知りする？',
    options: ['する', 'しない', 'すこしする'],
  },

  // すきなもの
  {
    id: 'favorite_food',
    category: 'likes',
    kana: 'すきな たべもの',
    kanji: '好きな食べ物',
    placeholder: { kana: 'なんでも かいてね', kanji: '何でも書いてね' },
  },
  {
    id: 'favorite_music',
    category: 'likes',
    kana: 'すきな おんがく',
    kanji: '好きな音楽',
    placeholder: { kana: 'きょくめい や アーティスト', kanji: '曲名やアーティスト' },
  },
  {
    id: 'favorite_movie',
    category: 'likes',
    kana: 'すきな えいが・アニメ',
    kanji: '好きな映画・アニメ',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'favorite_season',
    category: 'likes',
    kana: 'すきな きせつ',
    kanji: '好きな季節',
    options: ['はる', 'なつ', 'あき', 'ふゆ'],
  },
  {
    id: 'hobby',
    category: 'likes',
    kana: 'しゅみ',
    kanji: '趣味',
    placeholder: { kana: '', kanji: '' },
  },

  // にっきが たのしくなる しつもん
  {
    id: 'happiest_today',
    category: 'diary',
    kana: 'きょう いちばん うれしかったことは？',
    kanji: '今日一番嬉しかったことは？',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'into_lately',
    category: 'diary',
    kana: 'さいきん はまっていること',
    kanji: '最近ハマっていること',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'dream_now',
    category: 'diary',
    kana: 'いま かなえたい ゆめ',
    kanji: '今叶えたい夢',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'want_to_visit',
    category: 'diary',
    kana: 'いってみたい くに',
    kanji: '行ってみたい国',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'childhood_dream',
    category: 'diary',
    kana: 'こどもの ころの ゆめ',
    kanji: '子どもの頃の夢',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'value_most',
    category: 'diary',
    kana: 'いちばん たいせつに していること',
    kanji: '一番大切にしていること',
    placeholder: { kana: '', kanji: '' },
  },

  // おもしろい しつもん
  {
    id: 'desert_island',
    category: 'fun',
    kana: 'むじんとうに 1つ もっていくなら？',
    kanji: '無人島に1つ持っていくなら？',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'superpower',
    category: 'fun',
    kana: 'ちょうのうりょくが 1つ つかえるなら？',
    kanji: '超能力が1つ使えるなら？',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'time_machine',
    category: 'fun',
    kana: 'タイムマシンが あれば かこ？ みらい？',
    kanji: 'タイムマシンがあれば過去？未来？',
    options: ['かこ', 'みらい', 'どちらも'],
  },
  {
    id: 'week_off',
    category: 'fun',
    kana: '1しゅうかん やすみが あったら なにを する？',
    kanji: '一週間休みがあったら何をする？',
    placeholder: { kana: '', kanji: '' },
  },
  {
    id: 'reborn_as',
    category: 'fun',
    kana: 'うまれかわるなら なにに なりたい？',
    kanji: '生まれ変わるなら何になりたい？',
    placeholder: { kana: '', kanji: '' },
  },

  // なかよくなる しつもん
  {
    id: 'reply_speed',
    category: 'friend',
    kana: 'へんしんの ペース',
    kanji: '返信のペース',
    options: ['はやい', 'ふつう', 'ゆっくり'],
  },
  {
    id: 'like_being_talked_to',
    category: 'friend',
    kana: 'はなしかけられるのは うれしい？',
    kanji: '話しかけられるのは嬉しい？',
    options: ['うれしい', 'ときどき', 'そっとしておいてほしい'],
  },
  {
    id: 'like_listening',
    category: 'friend',
    kana: 'ぐちを きくのは すき？',
    kanji: '愚痴を聞くのは好き？',
    options: ['すき', 'ふつう', 'にがて'],
  },
];

export function questionsByCategory(categoryKey: string): ProfileQuestion[] {
  return profileQuestions.filter((q) => q.category === categoryKey);
}
