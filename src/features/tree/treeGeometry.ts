import type { Season } from './treeStage';

/**
 * 木の形を計算する。画像素材を持たず、線（枝）と円（葉・花）だけで描くため。
 *
 * 同じノートなら毎回同じ形になるよう、乱数は使わずノート ID から作った種で
 * 決定的に揺らぎを出す。開くたびに形が変わると「育てている感」が壊れる。
 */

export type Branch = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
};

export type Foliage = {
  x: number;
  y: number;
  r: number;
  /** 花にするか（葉ではなく） */
  blossom: boolean;
};

export type TreeGeometry = {
  branches: Branch[];
  foliage: Foliage[];
};

/** 描画に使う論理キャンバス。表示時に実際の幅へスケールする。 */
export const TREE_CANVAS_WIDTH = 300;
export const TREE_CANVAS_HEIGHT = 260;
const GROUND_Y = 236;

/** 文字列から決定的な数値の種を作る */
export function seedFrom(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/** 種から 0〜1 の値を順に取り出す、決定的な擬似乱数 */
function makeRandom(seed: number): () => number {
  let state = seed || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    state >>>= 0;
    return state / 0xffffffff;
  };
}

/** 段階ごとの枝分かれの深さ。level 0（種）と 1（芽）は枝を持たない。 */
function depthForLevel(level: number): number {
  if (level <= 1) return 0;
  return Math.min(5, level - 1);
}

/** 段階ごとの幹の長さ */
function trunkLengthForLevel(level: number): number {
  if (level === 0) return 0;
  if (level === 1) return 22;
  return Math.min(96, 30 + (level - 1) * 14);
}

export function buildTreeGeometry(level: number, season: Season, seed: string): TreeGeometry {
  const branches: Branch[] = [];
  const foliage: Foliage[] = [];
  const random = makeRandom(seedFrom(seed));

  const trunkLength = trunkLengthForLevel(level);
  const maxDepth = depthForLevel(level);

  // level 0（種）は地面に小さな粒だけ置く
  if (level === 0) {
    foliage.push({ x: TREE_CANVAS_WIDTH / 2, y: GROUND_Y - 4, r: 5, blossom: false });
    return { branches, foliage };
  }

  const baseWidth = Math.max(3, 3 + level * 1.6);
  // 冬は葉を落とすが、常緑に見えない程度には残す
  const foliageDensity = season === 'winter' ? 0.35 : 1;
  // 「花の咲く木」以降は花を主役にする
  const blossomChance = level >= 6 ? (season === 'spring' ? 0.85 : 0.45) : season === 'spring' ? 0.25 : 0;

  const grow = (
    x: number,
    y: number,
    angle: number,
    length: number,
    width: number,
    depth: number,
  ) => {
    const x2 = x + Math.sin(angle) * length;
    const y2 = y - Math.cos(angle) * length;
    branches.push({ x1: x, y1: y, x2, y2, width });

    if (depth <= 0) {
      // 枝の先に葉（または花）を付ける
      if (random() <= foliageDensity) {
        foliage.push({
          x: x2,
          y: y2,
          r: 7 + random() * 6 + level * 0.6,
          blossom: random() < blossomChance,
        });
      }
      return;
    }

    const childCount = depth >= 3 ? 2 : 2 + (random() < 0.35 ? 1 : 0);
    for (let i = 0; i < childCount; i += 1) {
      // 左右に開く角度。種によって少し揺らす
      const spread = 0.5 + random() * 0.35;
      const direction = childCount === 2 ? (i === 0 ? -1 : 1) : i - 1;
      const childAngle = angle + spread * direction * 0.9;
      grow(x2, y2, childAngle, length * (0.68 + random() * 0.14), width * 0.66, depth - 1);
    }
  };

  grow(TREE_CANVAS_WIDTH / 2, GROUND_Y, 0, trunkLength, baseWidth, maxDepth);

  return { branches, foliage };
}

/** 季節ごとの色 */
export const seasonColors: Record<
  Season,
  { leaf: string; blossom: string; trunk: string; sky: string; ground: string }
> = {
  spring: { leaf: '#7CC576', blossom: '#F7A8C4', trunk: '#8B6144', sky: '#EAF7FF', ground: '#BFE3A6' },
  summer: { leaf: '#3E9B4F', blossom: '#FFFFFF', trunk: '#7D563C', sky: '#DFF3FF', ground: '#9FD98C' },
  autumn: { leaf: '#E0913C', blossom: '#D2593B', trunk: '#6F4A34', sky: '#FFF3E0', ground: '#D9C48B' },
  winter: { leaf: '#BBD4E0', blossom: '#FFFFFF', trunk: '#5F4635', sky: '#F0F6FA', ground: '#E8EFF3' },
};

export const TREE_GROUND_Y = GROUND_Y;
