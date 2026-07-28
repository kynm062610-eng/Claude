import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { checkPageTexts, checkText } from './index.ts';
import { normalizeForMatch } from './normalize.ts';

describe('normalizeForMatch', () => {
  it('カタカナをひらがなに揃える', () => {
    assert.equal(normalizeForMatch('シネ'), 'しね');
  });

  it('空白と記号を落とす', () => {
    assert.equal(normalizeForMatch('し ね'), 'しね');
    assert.equal(normalizeForMatch('し・ね'), 'しね');
  });

  it('長音を落とす', () => {
    assert.equal(normalizeForMatch('しーーーね'), 'しね');
  });

  it('3回以上の繰り返しは1文字に潰す（判定語が部分一致で残る）', () => {
    assert.equal(normalizeForMatch('ばかああああ'), 'ばかあ');
    assert.ok(normalizeForMatch('ばかああああ').includes('ばか'));
  });

  it('全角英数を半角に揃える', () => {
    assert.equal(normalizeForMatch('ＡＢＣ１２３'), 'abc123');
  });
});

describe('checkText', () => {
  it('ふつうの文はそのまま通す', () => {
    const result = checkText('きょうの きゅうしょくは カレーでした！');
    assert.equal(result.severity, 'ok');
    assert.equal(result.findings.length, 0);
    assert.equal(result.notifyGuardian, false);
  });

  it('危険を示す語は block にして保護者へ通知する', () => {
    const result = checkText('しね');
    assert.equal(result.severity, 'block');
    assert.equal(result.notifyGuardian, true);
    assert.ok(result.message);
  });

  it('書き換えによる回避を拾う', () => {
    for (const input of ['シ ネ', 'しーーね', 'シネ']) {
      assert.equal(checkText(input).severity, 'block', input);
    }
  });

  it('仲間はずれを示す語も block にする', () => {
    const result = checkText('もう なかまはずれに しよう');
    assert.equal(result.severity, 'block');
    assert.equal(result.findings[0].category, 'exclusion');
  });

  it('きつい語は warn にとどめ、保護者には通知しない', () => {
    const result = checkText('ばかっていわれた');
    assert.equal(result.severity, 'warn');
    assert.equal(result.notifyGuardian, false);
  });

  it('電話番号を個人情報として検知する', () => {
    const result = checkText('でんわは 090-1234-5678 だよ');
    assert.equal(result.severity, 'warn');
    assert.ok(result.findings.some((f) => f.category === 'personal_info'));
  });

  it('学校名を個人情報として検知する', () => {
    const result = checkText('さくら小学校に かよってます');
    assert.ok(result.findings.some((f) => f.category === 'personal_info'));
  });

  it('個人情報の検知では保護者に通知しない（本人への注意にとどめる）', () => {
    const result = checkText('じゅうしょは 3丁目 だよ');
    assert.equal(result.notifyGuardian, false);
  });

  it('重い方の判定を採用する', () => {
    const result = checkText('ばか、しね、090-1234-5678');
    assert.equal(result.severity, 'block');
    assert.equal(result.notifyGuardian, true);
  });
});

describe('checkPageTexts', () => {
  it('ページ内のどれか一つでも block なら block にする', () => {
    const result = checkPageTexts(['たのしかった', 'きえろ']);
    assert.equal(result.severity, 'block');
    assert.equal(result.notifyGuardian, true);
  });

  it('すべて問題なければ ok', () => {
    const result = checkPageTexts(['おはよう', 'またあした']);
    assert.equal(result.severity, 'ok');
  });

  it('テキストがなければ ok', () => {
    assert.equal(checkPageTexts([]).severity, 'ok');
  });
});
