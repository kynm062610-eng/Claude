import { normalizeForMatch } from './normalize.ts';
import {
  categoryPolicy,
  personalInfoPatterns,
  wordRules,
  type BilingualMessage,
  type ModerationCategory,
} from './rules.ts';

export type { BilingualMessage, ModerationCategory };

export type Finding = {
  category: ModerationCategory;
  /** 該当した語、または検出したパターンのキー */
  matched: string;
};

export type ModerationResult = {
  /** ok = そのまま投稿してよい / warn = 確認を出す / block = 直すまで投稿させない */
  severity: 'ok' | 'warn' | 'block';
  findings: Finding[];
  /** 子どもに見せる文言（ひらがな版・かんじ版）。責める言い方にしない。 */
  message: BilingualMessage | null;
  /**
   * 保護者へ通知すべきか。
   * 見まもりモードの値に関係なく作動する「安全フロア」に対応する。
   */
  notifyGuardian: boolean;
};

// 判定語は起動時に一度だけ正規化しておく
const normalizedWordRules = wordRules.map((rule) => ({
  category: rule.category,
  words: rule.words.map((word) => ({ raw: word, normalized: normalizeForMatch(word) })),
}));

const severityRank = { ok: 0, warn: 1, block: 2 } as const;

/**
 * 投稿前にテキストを検査する。
 *
 * 注意: これは一次フィルタであって、いじめの検出装置ではない。
 * 通り抜けるものは必ずある。通報導線と運営のモデレーションが本体。
 */
export function checkText(input: string): ModerationResult {
  const findings: Finding[] = [];
  const normalized = normalizeForMatch(input);

  for (const rule of normalizedWordRules) {
    for (const word of rule.words) {
      if (word.normalized.length > 0 && normalized.includes(word.normalized)) {
        findings.push({ category: rule.category, matched: word.raw });
        break; // 同じカテゴリで複数出しても子どもには意味がないので 1 件に絞る
      }
    }
  }

  for (const { key, pattern } of personalInfoPatterns) {
    if (pattern.test(input)) {
      findings.push({ category: 'personal_info', matched: key });
      break;
    }
  }

  if (findings.length === 0) {
    return { severity: 'ok', findings: [], message: null, notifyGuardian: false };
  }

  let severity: ModerationResult['severity'] = 'ok';
  let notifyGuardian = false;
  let message: BilingualMessage | null = null;

  for (const finding of findings) {
    const policy = categoryPolicy[finding.category];
    if (severityRank[policy.severity] > severityRank[severity]) {
      severity = policy.severity;
      message = policy.message;
    }
    notifyGuardian = notifyGuardian || policy.notifyGuardian;
  }

  return { severity, findings, message, notifyGuardian };
}

/** ページ全体（テキスト要素すべて）をまとめて検査する */
export function checkPageTexts(texts: string[]): ModerationResult {
  const results = texts.map(checkText);
  const worst = results.reduce<ModerationResult>(
    (acc, cur) => (severityRank[cur.severity] > severityRank[acc.severity] ? cur : acc),
    { severity: 'ok', findings: [], message: null, notifyGuardian: false },
  );
  return {
    ...worst,
    findings: results.flatMap((r) => r.findings),
    notifyGuardian: results.some((r) => r.notifyGuardian),
  };
}
