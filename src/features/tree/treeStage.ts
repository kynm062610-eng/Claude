/**
 * みんなで育てる木。
 *
 * 設計の原則:
 *   - 育つ条件は「ノートのページが増えること」。誰が書いても育つ。
 *     このアプリは回覧制で自分の番は数回に 1 回しか来ないため、
 *     個人の連続記録（ストリーク）を条件にすると、ほとんどの日は何もできない。
 *   - **絶対に減らない・枯れない。** 書かない日が続いても後退させない。
 *     「パスする」を用意した設計と矛盾させないため。子どもに罪悪感を持たせない。
 *   - 課金と結びつけない。無料で最後まで育つ。
 */

export type Season = 'spring' | 'summer' | 'autumn' | 'winter';

export type TreeStage = {
  /** 0 から始まる成長段階 */
  level: number;
  /** この段階に入るのに必要なページ数 */
  from: number;
  labelKana: string;
  labelKanji: string;
};

/**
 * 成長段階のしきい値。
 * 序盤は少ないページ数で次の段階に進むようにして、始めたばかりでも変化が見えるようにする。
 * 後半は間隔を広げて、長く続けたグループだけが到達できる姿を残す。
 */
export const treeStages: TreeStage[] = [
  { level: 0, from: 0, labelKana: 'たね', labelKanji: '種' },
  { level: 1, from: 1, labelKana: 'め', labelKanji: '芽' },
  { level: 2, from: 3, labelKana: 'わかば', labelKanji: '若葉' },
  { level: 3, from: 8, labelKana: 'わかぎ', labelKanji: '若木' },
  { level: 4, from: 20, labelKana: 'き', labelKanji: '木' },
  { level: 5, from: 45, labelKana: 'おおきな き', labelKanji: '大きな木' },
  { level: 6, from: 100, labelKana: 'はなの さく き', labelKanji: '花の咲く木' },
  { level: 7, from: 365, labelKana: 'たいじゅ', labelKanji: '大樹' },
  { level: 8, from: 1000, labelKana: 'でんせつの き', labelKanji: '伝説の木' },
];

/** ページ数から今の段階を返す */
export function treeStageOf(pageCount: number): TreeStage {
  const pages = Math.max(0, Math.floor(pageCount));
  let current = treeStages[0];
  for (const stage of treeStages) {
    if (pages >= stage.from) current = stage;
    else break;
  }
  return current;
}

/** 次の段階（最終段階に到達済みなら null） */
export function nextTreeStageOf(pageCount: number): TreeStage | null {
  const current = treeStageOf(pageCount);
  return treeStages.find((s) => s.level === current.level + 1) ?? null;
}

/**
 * 次の段階までの進捗。
 * 最終段階に到達済みなら ratio = 1、remaining = 0 を返す。
 */
export function treeProgress(pageCount: number): {
  current: TreeStage;
  next: TreeStage | null;
  /** 0〜1 */
  ratio: number;
  /** 次の段階まであと何ページか */
  remaining: number;
} {
  const pages = Math.max(0, Math.floor(pageCount));
  const current = treeStageOf(pages);
  const next = nextTreeStageOf(pages);

  if (!next) {
    return { current, next: null, ratio: 1, remaining: 0 };
  }

  const span = next.from - current.from;
  const done = pages - current.from;
  return {
    current,
    next,
    ratio: span <= 0 ? 1 : Math.min(1, Math.max(0, done / span)),
    remaining: Math.max(0, next.from - pages),
  };
}

/** 日付から季節を決める。表示を変えるだけの用途なので月で割り切る。 */
export function seasonOf(date = new Date()): Season {
  const month = date.getMonth() + 1;
  if (month >= 3 && month <= 5) return 'spring';
  if (month >= 6 && month <= 8) return 'summer';
  if (month >= 9 && month <= 11) return 'autumn';
  return 'winter';
}

export const seasonLabels: Record<Season, { kana: string; kanji: string }> = {
  spring: { kana: 'はる', kanji: '春' },
  summer: { kana: 'なつ', kanji: '夏' },
  autumn: { kana: 'あき', kanji: '秋' },
  winter: { kana: 'ふゆ', kanji: '冬' },
};
