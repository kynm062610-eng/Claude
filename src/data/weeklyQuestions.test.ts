import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { questionOfTheWeek, weekIndexOf, weeklyQuestions } from './weeklyQuestions.ts';

describe('weekIndexOf', () => {
  it('同じ週の日付は同じ週番号になる（月曜〜日曜）', () => {
    // 2026-07-27 は月曜
    const monday = weekIndexOf(new Date(2026, 6, 27));
    const wednesday = weekIndexOf(new Date(2026, 6, 29));
    const sunday = weekIndexOf(new Date(2026, 7, 2));
    assert.equal(monday, wednesday);
    assert.equal(monday, sunday);
  });

  it('週をまたぐと番号が1つ進む', () => {
    const thisMonday = weekIndexOf(new Date(2026, 6, 27));
    const nextMonday = weekIndexOf(new Date(2026, 7, 3));
    assert.equal(nextMonday, thisMonday + 1);
  });

  it('日曜と翌月曜は別の週になる', () => {
    const sunday = weekIndexOf(new Date(2026, 7, 2));
    const monday = weekIndexOf(new Date(2026, 7, 3));
    assert.notEqual(sunday, monday);
  });
});

describe('questionOfTheWeek', () => {
  it('同じ週なら同じ質問を返す', () => {
    const a = questionOfTheWeek(new Date(2026, 6, 27));
    const b = questionOfTheWeek(new Date(2026, 7, 1));
    assert.deepEqual(a, b);
  });

  it('翌週は別の質問になる', () => {
    const a = questionOfTheWeek(new Date(2026, 6, 27));
    const b = questionOfTheWeek(new Date(2026, 7, 3));
    assert.notDeepEqual(a, b);
  });

  it('質問プールの中から返し、両方の表記を持つ', () => {
    const picked = questionOfTheWeek(new Date(2026, 3, 15));
    assert.ok(weeklyQuestions.some((q) => q.kana === picked.kana && q.kanji === picked.kanji));
    assert.ok(picked.kana.length > 0);
    assert.ok(picked.kanji.length > 0);
  });

  it('どの日付でも必ず質問が返る（1年分ためす）', () => {
    for (let day = 0; day < 366; day += 1) {
      const date = new Date(2026, 0, 1 + day);
      const q = questionOfTheWeek(date);
      assert.ok(q.kana.length > 0, `${date.toDateString()} で質問が空`);
    }
  });

  it('1970年より前の日付でも壊れない', () => {
    const q = questionOfTheWeek(new Date(1965, 2, 10));
    assert.ok(q.kana.length > 0);
  });

  it('プール全体をひと巡りする（同じ質問ばかり出ない）', () => {
    const seen = new Set<string>();
    for (let week = 0; week < weeklyQuestions.length; week += 1) {
      const date = new Date(2026, 0, 5 + week * 7); // 2026-01-05 は月曜
      seen.add(questionOfTheWeek(date).kanji);
    }
    assert.equal(seen.size, weeklyQuestions.length);
  });
});

describe('週替わりの質問の内容', () => {
  it('写真を要求する質問を含まない（カメラを持たない設計のため）', () => {
    for (const q of weeklyQuestions) {
      assert.ok(!q.kanji.includes('写真'), `写真を求める質問がある: ${q.kanji}`);
      assert.ok(!q.kana.includes('しゃしん'), `写真を求める質問がある: ${q.kana}`);
    }
  });

  it('すべての質問がひらがな版とかんじ版を持つ', () => {
    for (const q of weeklyQuestions) {
      assert.ok(q.kana.length > 0);
      assert.ok(q.kanji.length > 0);
    }
  });
});
