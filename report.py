"""分析結果を持ち出せるテキスト/CSV形式にまとめる。"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import analysis


def _format_count_ja(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"

    def trim(v: float) -> str:
        s = f"{v:.1f}"
        return s[:-2] if s.endswith(".0") else s

    if n >= 100_000_000:
        return f"{trim(n / 100_000_000)}億"
    if n >= 10_000:
        return f"{trim(n / 10_000)}万"
    return f"{n:,}"


def build_text_report(df: pd.DataFrame, title: str) -> str:
    """動画一覧と傾向分析をまとめた読み物としてのレポートを組み立てる。"""
    now = dt.datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        f"# {title}",
        f"作成日時: {now}",
        f"対象動画数: {len(df)}本",
        "",
    ]

    if df.empty:
        lines.append("(データがありません)")
        return "\n".join(lines)

    insights = analysis.growth_insights(df)
    if insights:
        lines.append("## 伸びている動画の共通点(推定)")
        lines.extend(f"- {line}" for line in insights)
        lines.append("※ データ上の相関から見える傾向であり、断定はできません。")
        lines.append("")

    time_insights = analysis.posting_time_insights(df)
    if time_insights:
        lines.append("## 投稿時間帯の傾向(日本時間)")
        lines.extend(f"- {line}" for line in time_insights)
        lines.append("")

    hour_dist = analysis.posting_hour_distribution(df)
    if not hour_dist.empty:
        active = hour_dist[hour_dist["投稿数"] > 0]
        lines.append("## 時間帯別の投稿本数(日本時間)")
        lines.extend(f"- {hour}: {row['投稿数']}本" for hour, row in active.iterrows())
        lines.append("")

    words = analysis.title_word_frequency(df["title"].tolist())
    if words:
        lines.append("## タイトルの頻出ワード")
        lines.extend(f"- {word}: {count}回" for word, count in words)
        lines.append("")

    tags = analysis.tag_frequency(df["tags"].tolist()) if "tags" in df.columns else []
    if tags:
        lines.append("## 頻出タグ")
        lines.extend(f"- {tag}: {count}回" for tag, count in tags)
        lines.append("")

    hashtags = (
        analysis.hashtag_frequency(df["description"].tolist())
        if "description" in df.columns else []
    )
    if hashtags:
        lines.append("## 概要欄の頻出ハッシュタグ")
        lines.extend(f"- {tag}: {count}回" for tag, count in hashtags)
        lines.append("")

    lines.append("## 動画一覧(再生数順)")
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        published = pd.to_datetime(row["published_at"]).strftime("%Y/%m/%d")
        lines.append(f"{i}. {row['title']}")
        lines.append(f"   チャンネル: {row.get('channel_title', '')}")
        lines.append(
            f"   再生 {_format_count_ja(row.get('view_count', 0))}回"
            f" / 高評価 {_format_count_ja(row.get('like_count', 0))}"
            f" / コメント {_format_count_ja(row.get('comment_count', 0))}"
            f" / 投稿 {published}"
        )
        lines.append(f"   https://www.youtube.com/watch?v={row.get('video_id', '')}")
        lines.append("")

    return "\n".join(lines)


def normalize_comments(comments: list) -> list[dict]:
    """文字列だけの古い保存形式も、辞書形式に揃えて扱えるようにする。"""
    normalized = []
    for c in comments or []:
        if isinstance(c, dict):
            normalized.append(c)
        else:
            normalized.append({"text": str(c)})
    return normalized


def build_comments_text(comments: list, label: str) -> str:
    """取得したコメントを本文そのままで書き出す。"""
    items = normalize_comments(comments)
    now = dt.datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        f"# {label} のコメント",
        f"作成日時: {now}",
        f"件数: {len(items)}件",
        "",
    ]
    if not items:
        lines.append("(コメントがありません)")
        return "\n".join(lines)

    sentiment = analysis.comment_sentiment([c.get("text", "") for c in items])
    insights = analysis.comment_insights([c.get("text", "") for c in items], sentiment)
    if insights:
        lines.append("## 反応の傾向")
        lines.extend(f"- {line}" for line in insights)
        lines.append("※ キーワードによる自動分類です。皮肉や文脈までは読み取れません。")
        lines.append("")

    lines.append("## コメント一覧")
    for i, c in enumerate(items, start=1):
        author = c.get("author", "")
        likes = c.get("like_count")
        header = f"{i}. {author}" if author else f"{i}."
        if likes:
            header += f"(👍 {likes})"
        lines.append(header)
        lines.append(f"   {c.get('text', '')}")
        video_id = c.get("video_id")
        if video_id:
            lines.append(f"   https://www.youtube.com/watch?v={video_id}")
        lines.append("")

    return "\n".join(lines)


def build_comments_csv(comments: list) -> str:
    """コメントを表計算ソフトで開ける形式にする。"""
    items = normalize_comments(comments)
    if not items:
        return ""
    out = pd.DataFrame({
        "コメント": [c.get("text", "") for c in items],
        "投稿者": [c.get("author", "") for c in items],
        "高評価数": [c.get("like_count", "") for c in items],
        "投稿日時": [c.get("published_at", "") for c in items],
        "動画URL": [
            f"https://www.youtube.com/watch?v={c['video_id']}" if c.get("video_id") else ""
            for c in items
        ],
    })
    return out.to_csv(index=False)


def build_csv(df: pd.DataFrame) -> str:
    """表計算ソフトで開ける形式に整えたCSVを返す。"""
    if df.empty:
        return ""
    out = pd.DataFrame({
        "タイトル": df["title"],
        "チャンネル": df.get("channel_title", ""),
        "再生数": df["view_count"],
        "高評価数": df.get("like_count", 0),
        "コメント数": df.get("comment_count", 0),
        "投稿日": pd.to_datetime(df["published_at"]).dt.strftime("%Y/%m/%d"),
        "タグ": df["tags"].apply(lambda t: ", ".join(t)) if "tags" in df.columns else "",
        "URL": df["video_id"].apply(lambda v: f"https://www.youtube.com/watch?v={v}"),
    })
    # Excelでの文字化けを避けるためBOM付きUTF-8を前提にする
    return out.to_csv(index=False)
