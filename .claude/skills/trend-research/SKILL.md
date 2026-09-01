---
name: trend-research
description: Use when the user wants to find trending topics, viral content ideas, or "what's growing right now" for video/SNS content. Triggers on "伸びてるネタ", "トレンド調査", "バズってるもの", "今のトレンド", "ネタ探し" などのリクエスト。
---

# トレンド・ネタ調査スキル（2026年9月時点の情報ベース）

コンテンツのネタ探しをする時の考え方とツール一覧。ツールの多くはこの環境から直接は
使えない（ブラウザ操作が必要なものが多い）ので、基本は`WebSearch`で代用しつつ、
ユーザー本人がパソコン/スマホで使うツールとして案内する。

## 調査の頻度の目安

- 戦略的な企画出しは週1回、時事ネタ・SNSトレンドのような即応性が必要なものは毎日チェック、
  というのが一般的な運用。

## 代表的なツール（ユーザー自身が使うもの）

- **Exploding Topics** — ピークを迎える前の急上昇トピックを見つけるのに強い
- **BuzzSumo** — トピックのシェア数・話題性のトラッキング
- **Answer Socrates** — トレンドトピック＋「みんなが実際に検索してる質問」を同時に拾える
- **TikTok Creator Search Insights** — TikTok公式のネタ探しツール。ユーザーが実際に検索してる語句が見える
- **ChatGPT / Perplexity** — ブレストや切り口の壁打ち用

## Claude Code側でできること

- `WebSearch`でその時点のニュース・トレンドワードを直接調べる
- 集めたネタを元に、`video-script`や`sns-writing`スキルと組み合わせて構成案・投稿文まで一気に作る

## 出典（2026年9月時点）
- [13 Top Trend Tracking Tools for 2026 (Free and Paid)](https://explodingtopics.com/blog/trend-tools)
- [Best Viral Content Research Tools for Creators (2026)](https://www.octupie.com/blog/best-viral-content-research-tools-2026)
- [What is TikTok Creator Search Insights (And How To Use It)](https://www.advancedcreativemedia.co/post/what-is-tiktok-creator-search-insights-and-how-to-use-it)
