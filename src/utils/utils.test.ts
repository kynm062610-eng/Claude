import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { isQuietHours } from './quietHours.ts';
import { canNudge, isMyTurn, nextTurnChildId } from './turn.ts';
import { promptOfTheDay, prompts } from '../data/prompts.ts';
import type { Membership, Notebook } from '../types.ts';

const at = (hour: number) => new Date(2026, 0, 15, hour, 0, 0);

describe('isQuietHours', () => {
  it('日をまたぐ時間帯を正しく判定する（21時〜6時）', () => {
    assert.equal(isQuietHours(at(22), 21, 6), true);
    assert.equal(isQuietHours(at(2), 21, 6), true);
    assert.equal(isQuietHours(at(5), 21, 6), true);
    assert.equal(isQuietHours(at(6), 21, 6), false);
    assert.equal(isQuietHours(at(15), 21, 6), false);
    assert.equal(isQuietHours(at(20), 21, 6), false);
  });

  it('日をまたがない時間帯も判定できる（1時〜6時）', () => {
    assert.equal(isQuietHours(at(3), 1, 6), true);
    assert.equal(isQuietHours(at(23), 1, 6), false);
  });

  it('開始と終了が同じなら制限なし', () => {
    assert.equal(isQuietHours(at(3), 0, 0), false);
  });
});

const notebook = (over: Partial<Notebook> = {}): Notebook => ({
  id: 'n1',
  group_id: 'g1',
  title: 'ノート',
  current_turn_child_id: 'c1',
  turn_started_at: new Date(2026, 0, 15).toISOString(),
  is_closed: false,
  ...over,
});

describe('isMyTurn', () => {
  it('自分の番なら true', () => {
    assert.equal(isMyTurn(notebook(), 'c1'), true);
  });

  it('他人の番なら false', () => {
    assert.equal(isMyTurn(notebook(), 'c2'), false);
  });

  it('閉じたノートでは false', () => {
    assert.equal(isMyTurn(notebook({ is_closed: true }), 'c1'), false);
  });
});

describe('canNudge', () => {
  const started = new Date(2026, 0, 15);

  it('3日たっていれば送れる', () => {
    const now = new Date(2026, 0, 18);
    assert.equal(canNudge(notebook({ turn_started_at: started.toISOString() }), 'c2', now), true);
  });

  it('3日たっていなければ送れない', () => {
    const now = new Date(2026, 0, 17);
    assert.equal(canNudge(notebook({ turn_started_at: started.toISOString() }), 'c2', now), false);
  });

  it('自分の番のときは送れない', () => {
    const now = new Date(2026, 0, 20);
    assert.equal(canNudge(notebook({ turn_started_at: started.toISOString() }), 'c1', now), false);
  });
});

describe('nextTurnChildId', () => {
  const memberships: Membership[] = [
    { id: 'm1', group_id: 'g1', child_id: 'c1', turn_order: 0, left_at: null },
    { id: 'm2', group_id: 'g1', child_id: 'c2', turn_order: 1, left_at: null },
    { id: 'm3', group_id: 'g1', child_id: 'c3', turn_order: 2, left_at: null },
  ];

  it('順番どおりに次の子を返す', () => {
    assert.equal(nextTurnChildId(memberships, 'c1'), 'c2');
    assert.equal(nextTurnChildId(memberships, 'c2'), 'c3');
  });

  it('最後の子のあとは先頭に戻る', () => {
    assert.equal(nextTurnChildId(memberships, 'c3'), 'c1');
  });

  it('退出した子は飛ばす', () => {
    const withLeft: Membership[] = [
      memberships[0],
      { ...memberships[1], left_at: '2026-01-10T00:00:00Z' },
      memberships[2],
    ];
    assert.equal(nextTurnChildId(withLeft, 'c1'), 'c3');
  });

  it('1人だけなら自分のまま', () => {
    assert.equal(nextTurnChildId([memberships[0]], 'c1'), 'c1');
  });

  it('参加者がいなければ null', () => {
    assert.equal(nextTurnChildId([], 'c1'), null);
  });
});

describe('promptOfTheDay', () => {
  it('同じ日なら同じお題を返す', () => {
    const a = promptOfTheDay(new Date(2026, 5, 1, 9));
    const b = promptOfTheDay(new Date(2026, 5, 1, 20));
    assert.equal(a, b);
  });

  it('お題プールの中から返す', () => {
    assert.ok(prompts.includes(promptOfTheDay(new Date(2026, 2, 3))));
  });
});
