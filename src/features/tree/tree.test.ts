import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  nextTreeStageOf,
  seasonOf,
  treeProgress,
  treeStageOf,
  treeStages,
} from './treeStage.ts';
import { buildTreeGeometry, seedFrom } from './treeGeometry.ts';

describe('treeStageOf', () => {
  it('0ページなら種', () => {
    assert.equal(treeStageOf(0).labelKanji, '種');
  });

  it('1ページで芽になる（最初の1歩で変化が見える）', () => {
    assert.equal(treeStageOf(1).labelKanji, '芽');
  });

  it('しきい値ちょうどでその段階に入る', () => {
    assert.equal(treeStageOf(100).labelKanji, '花の咲く木');
    assert.equal(treeStageOf(365).labelKanji, '大樹');
    assert.equal(treeStageOf(1000).labelKanji, '伝説の木');
  });

  it('しきい値の1つ前では前の段階のまま', () => {
    assert.equal(treeStageOf(99).labelKanji, '大きな木');
    assert.equal(treeStageOf(364).labelKanji, '花の咲く木');
  });

  it('最終段階を超えても最終段階のまま', () => {
    assert.equal(treeStageOf(99999).labelKanji, '伝説の木');
  });

  it('負の数やページ数の端数でも壊れない', () => {
    assert.equal(treeStageOf(-5).labelKanji, '種');
    assert.equal(treeStageOf(3.7).labelKanji, '若葉');
  });

  it('ページ数が増えて段階が下がることはない（枯れない設計）', () => {
    let previous = -1;
    for (let pages = 0; pages <= 1200; pages += 1) {
      const level = treeStageOf(pages).level;
      assert.ok(level >= previous, `pages=${pages} で段階が下がった`);
      previous = level;
    }
  });
});

describe('nextTreeStageOf', () => {
  it('次の段階を返す', () => {
    assert.equal(nextTreeStageOf(0)?.labelKanji, '芽');
    assert.equal(nextTreeStageOf(100)?.labelKanji, '大樹');
  });

  it('最終段階では null', () => {
    assert.equal(nextTreeStageOf(1000), null);
  });
});

describe('treeProgress', () => {
  it('段階に入った直後は ratio 0', () => {
    const p = treeProgress(100);
    assert.equal(p.ratio, 0);
    assert.equal(p.remaining, 265);
  });

  it('次の段階の1つ前では remaining 1', () => {
    assert.equal(treeProgress(364).remaining, 1);
  });

  it('中間ではおよそ半分', () => {
    // 若葉(3) 〜 若木(8) の中間 = 5.5 → 5ページ地点で 2/5
    const p = treeProgress(5);
    assert.ok(p.ratio > 0 && p.ratio < 1);
  });

  it('最終段階では ratio 1 / remaining 0', () => {
    const p = treeProgress(1000);
    assert.equal(p.ratio, 1);
    assert.equal(p.remaining, 0);
    assert.equal(p.next, null);
  });

  it('ratio は常に 0〜1 の範囲', () => {
    for (let pages = 0; pages <= 1200; pages += 7) {
      const { ratio } = treeProgress(pages);
      assert.ok(ratio >= 0 && ratio <= 1, `pages=${pages} ratio=${ratio}`);
    }
  });
});

describe('seasonOf', () => {
  it('月から季節を決める', () => {
    assert.equal(seasonOf(new Date(2026, 2, 15)), 'spring'); // 3月
    assert.equal(seasonOf(new Date(2026, 6, 15)), 'summer'); // 7月
    assert.equal(seasonOf(new Date(2026, 9, 15)), 'autumn'); // 10月
    assert.equal(seasonOf(new Date(2026, 0, 15)), 'winter'); // 1月
    assert.equal(seasonOf(new Date(2026, 11, 15)), 'winter'); // 12月
  });

  it('12か月すべてがどれかの季節に入る', () => {
    for (let month = 0; month < 12; month += 1) {
      const season = seasonOf(new Date(2026, month, 1));
      assert.ok(['spring', 'summer', 'autumn', 'winter'].includes(season));
    }
  });
});

describe('seedFrom', () => {
  it('同じ文字列なら同じ種', () => {
    assert.equal(seedFrom('notebook-1'), seedFrom('notebook-1'));
  });

  it('違う文字列なら違う種', () => {
    assert.notEqual(seedFrom('notebook-1'), seedFrom('notebook-2'));
  });
});

describe('buildTreeGeometry', () => {
  it('同じ入力なら毎回同じ形になる（開くたびに変わらない）', () => {
    const a = buildTreeGeometry(4, 'spring', 'note-abc');
    const b = buildTreeGeometry(4, 'spring', 'note-abc');
    assert.deepEqual(a, b);
  });

  it('種の段階では枝を持たない', () => {
    const g = buildTreeGeometry(0, 'spring', 'note-abc');
    assert.equal(g.branches.length, 0);
    assert.equal(g.foliage.length, 1);
  });

  it('段階が上がると枝が増える', () => {
    const small = buildTreeGeometry(2, 'summer', 'note-abc');
    const big = buildTreeGeometry(6, 'summer', 'note-abc');
    assert.ok(big.branches.length > small.branches.length);
  });

  it('冬は葉が少なくなる', () => {
    const summer = buildTreeGeometry(6, 'summer', 'note-abc');
    const winter = buildTreeGeometry(6, 'winter', 'note-abc');
    assert.ok(winter.foliage.length < summer.foliage.length);
  });

  it('花の咲く木以降は花が付く', () => {
    const g = buildTreeGeometry(6, 'spring', 'note-abc');
    assert.ok(g.foliage.some((f) => f.blossom));
  });

  it('若い木では花が付かない', () => {
    const g = buildTreeGeometry(3, 'summer', 'note-abc');
    assert.ok(g.foliage.every((f) => !f.blossom));
  });

  it('すべての段階・季節でエラーにならず座標が数値になる', () => {
    for (const stage of treeStages) {
      for (const season of ['spring', 'summer', 'autumn', 'winter'] as const) {
        const g = buildTreeGeometry(stage.level, season, `note-${stage.level}`);
        for (const b of g.branches) {
          assert.ok(Number.isFinite(b.x1) && Number.isFinite(b.y1));
          assert.ok(Number.isFinite(b.x2) && Number.isFinite(b.y2));
          assert.ok(b.width > 0);
        }
        for (const f of g.foliage) {
          assert.ok(Number.isFinite(f.x) && Number.isFinite(f.y));
          assert.ok(f.r > 0);
        }
      }
    }
  });
});
