"""動画データから傾向(頻出ワード・タグ・ハッシュタグ・サムネイル色)を集計する。"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from io import BytesIO

import pandas as pd
import requests
from janome.tokenizer import Tokenizer
from PIL import Image

_TOKENIZER = Tokenizer()
_TARGET_POS = {"名詞", "動詞", "形容詞"}
_STOPWORDS = {
    "する", "いる", "なる", "ある", "こと", "これ", "それ", "あれ", "the", "of", "in",
    "and", "to", "a", "is",
}
_HASHTAG_PATTERN = re.compile(r"#(\w+)")


def title_word_frequency(titles: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """タイトル群を形態素解析し、頻出する名詞・動詞・形容詞を集計する。"""
    counter: Counter[str] = Counter()
    for title in titles:
        for token in _TOKENIZER.tokenize(title):
            pos = token.part_of_speech.split(",")[0]
            if pos not in _TARGET_POS:
                continue
            base = token.base_form if token.base_form != "*" else token.surface
            base = base.strip().lower()
            if len(base) <= 1 or base in _STOPWORDS:
                continue
            counter[base] += 1
    return counter.most_common(top_n)


def tag_frequency(tags_lists: list[list[str]], top_n: int = 20) -> list[tuple[str, int]]:
    """動画タグの出現回数を集計する。"""
    counter: Counter[str] = Counter()
    for tags in tags_lists:
        for tag in tags:
            tag = tag.strip()
            if tag:
                counter[tag] += 1
    return counter.most_common(top_n)


def hashtag_frequency(descriptions: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """概要欄に含まれるハッシュタグの出現回数を集計する。"""
    counter: Counter[str] = Counter()
    for description in descriptions:
        for match in _HASHTAG_PATTERN.findall(description):
            counter[f"#{match}"] += 1
    return counter.most_common(top_n)


_WEEKDAY_JA = {
    "Monday": "月曜", "Tuesday": "火曜", "Wednesday": "水曜", "Thursday": "木曜",
    "Friday": "金曜", "Saturday": "土曜", "Sunday": "日曜",
}


def growth_insights(df: pd.DataFrame, top_ratio: float = 0.25, min_videos: int = 4) -> list[str]:
    """上位動画と残りの動画を比べ、統計的な差分から「伸びている要因」の仮説を言語化する。

    あくまで手元のデータから見える相関を並べたものであり、断定はしない。
    """
    if df is None or len(df) < min_videos:
        return []

    df = df.sort_values("view_count", ascending=False).reset_index(drop=True)
    cutoff = max(1, round(len(df) * top_ratio))
    top = df.iloc[:cutoff]
    rest = df.iloc[cutoff:]

    insights: list[str] = []

    median_all = df["view_count"].median()
    median_top = top["view_count"].median()
    if median_all and median_top:
        ratio = median_top / median_all
        if ratio >= 1.3:
            insights.append(
                f"上位{len(top)}本の再生数は全体の中央値の約{ratio:.1f}倍。少数の動画が全体を牽引している傾向"
            )

    if "title" in df.columns:
        top_words = dict(title_word_frequency(top["title"].tolist(), top_n=50))
        rest_words = dict(title_word_frequency(rest["title"].tolist(), top_n=50)) if len(rest) else {}
        scored = []
        for word, count in top_words.items():
            if count < 2:
                continue
            top_rate = count / len(top)
            rest_rate = rest_words.get(word, 0) / len(rest) if len(rest) else 0
            if top_rate > rest_rate * 1.5:
                scored.append((word, top_rate))
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored:
            words = "」「".join(w for w, _ in scored[:5])
            insights.append(f"上位動画のタイトルには「{words}」が他より高い頻度で登場")

    if "tags" in df.columns:
        top_tag_avg = top["tags"].apply(len).mean()
        rest_tag_avg = rest["tags"].apply(len).mean() if len(rest) else 0
        if top_tag_avg >= 3 and top_tag_avg > rest_tag_avg * 1.3:
            insights.append(
                f"上位動画は平均{top_tag_avg:.1f}個のタグを設定(それ以外は平均{rest_tag_avg:.1f}個)"
            )

    if "description" in df.columns:
        top_hash_avg = top["description"].apply(lambda d: len(_HASHTAG_PATTERN.findall(d or ""))).mean()
        rest_hash_avg = (
            rest["description"].apply(lambda d: len(_HASHTAG_PATTERN.findall(d or ""))).mean()
            if len(rest) else 0
        )
        if top_hash_avg >= 1 and top_hash_avg > rest_hash_avg * 1.3:
            insights.append(f"上位動画は概要欄のハッシュタグが多め(平均{top_hash_avg:.1f}個)")

    if "published_at" in df.columns and len(top) >= 3:
        top_days = pd.to_datetime(top["published_at"]).dt.day_name().map(_WEEKDAY_JA)
        counts = top_days.value_counts()
        if not counts.empty and counts.iloc[0] / len(top) >= 0.4:
            insights.append(f"上位動画は「{counts.index[0]}」の投稿が多い({counts.iloc[0]}/{len(top)}本)")

    return insights


JST = dt.timezone(dt.timedelta(hours=9))

_TIME_BANDS = [
    (0, 6, "深夜(0〜6時)"),
    (6, 12, "午前(6〜12時)"),
    (12, 18, "午後(12〜18時)"),
    (18, 24, "夜(18〜24時)"),
]


def _jst_hours(series: pd.Series) -> pd.Series:
    """UTCの投稿日時を日本時間の「時」に変換する。"""
    times = pd.to_datetime(series, utc=True)
    return times.dt.tz_convert(JST).dt.hour


def posting_hour_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """0〜23時それぞれの投稿本数を日本時間で集計する。"""
    if df is None or df.empty or "published_at" not in df.columns:
        return pd.DataFrame()
    hours = _jst_hours(df["published_at"])
    counts = hours.value_counts().reindex(range(24), fill_value=0).sort_index()
    return pd.DataFrame({"投稿数": counts.values}, index=[f"{h}時" for h in range(24)])


def posting_time_insights(df: pd.DataFrame, top_ratio: float = 0.25, min_videos: int = 4) -> list[str]:
    """投稿時間帯の偏りと、再生数との関係を言語化する。"""
    if df is None or len(df) < min_videos or "published_at" not in df.columns:
        return []

    df = df.sort_values("view_count", ascending=False).reset_index(drop=True)
    hours = _jst_hours(df["published_at"])
    insights: list[str] = []

    band_of = lambda h: next(name for lo, hi, name in _TIME_BANDS if lo <= h < hi)  # noqa: E731
    bands = hours.map(band_of)
    band_counts = bands.value_counts()
    if not band_counts.empty and band_counts.iloc[0] / len(df) >= 0.35:
        insights.append(
            f"投稿は「{band_counts.index[0]}」に集中({band_counts.iloc[0]}/{len(df)}本)"
        )

    hour_counts = hours.value_counts()
    if not hour_counts.empty and hour_counts.iloc[0] >= 2:
        insights.append(f"最も多い投稿時刻は{hour_counts.index[0]}時台({hour_counts.iloc[0]}本)")

    cutoff = max(1, round(len(df) * top_ratio))
    top_bands = bands.iloc[:cutoff]
    if len(top_bands) >= 2:
        top_band_counts = top_bands.value_counts()
        leader = top_band_counts.index[0]
        share = top_band_counts.iloc[0] / len(top_bands)
        overall_share = (bands == leader).sum() / len(bands)
        if share >= 0.5 and share > overall_share * 1.2:
            insights.append(
                f"再生数上位の動画は「{leader}」の投稿が多い"
                f"(上位の{share:.0%} / 全体では{overall_share:.0%})"
            )

    return insights


# コメントの感情分類に使うキーワード辞書。文脈は読まないため、あくまで傾向の目安。
_SENTIMENT_LEXICON: dict[str, tuple[str, ...]] = {
    "称賛・好意": (
        "すごい", "スゴい", "凄い", "最高", "神", "天才", "面白", "おもしろ", "好き",
        "素晴らし", "うまい", "上手", "かわい", "可愛", "かっこい", "カッコい", "感動",
        "優しい", "良い", "いいね", "美しい", "尊い",
    ),
    "笑い": ("www", "ｗｗｗ", "草", "笑った", "爆笑", "わろた", "笑う"),
    "感謝": ("ありがと", "感謝", "助かっ", "参考になっ", "勉強になっ", "為になっ", "ためになっ"),
    "共感": ("わかる", "分かる", "同じ", "私も", "俺も", "僕も", "それな", "共感", "あるある"),
    "驚き": ("びっくり", "驚い", "まじ", "マジ", "えぐ", "やば", "衝撃", "信じられ"),
    "応援・期待": ("頑張", "がんば", "応援", "期待", "楽しみ", "待って", "次回", "登録した"),
    "要望・質問": ("してほしい", "して欲しい", "教えて", "知りたい", "リクエスト", "お願い", "ですか"),
    "批判・不満": (
        "つまらな", "つまんな", "うざ", "嫌い", "最悪", "ひど", "下手", "残念",
        "微妙", "意味不明", "萎え", "がっかり",
    ),
}


def comment_sentiment(comments: list[str]) -> dict[str, int]:
    """コメントをキーワードで感情カテゴリに分類し、該当件数を数える。

    1つのコメントが複数カテゴリに該当することがある。
    """
    counts = {label: 0 for label in _SENTIMENT_LEXICON}
    for comment in comments:
        lowered = comment.lower()
        for label, keywords in _SENTIMENT_LEXICON.items():
            if any(kw.lower() in lowered for kw in keywords):
                counts[label] += 1
    return {k: v for k, v in counts.items() if v > 0}


def comment_word_frequency(comments: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """コメント本文の頻出ワードを集計する。"""
    return title_word_frequency(comments, top_n=top_n)


def comment_insights(comments: list[str], sentiment: dict[str, int]) -> list[str]:
    """感情の内訳から、視聴者の反応の傾向を言語化する。"""
    if not comments:
        return []

    total = len(comments)
    lines = [f"分析したコメント: {total}件"]

    if not sentiment:
        lines.append("目立った感情キーワードは検出されませんでした。")
        return lines

    ranked = sorted(sentiment.items(), key=lambda x: x[1], reverse=True)
    top_label, top_count = ranked[0]
    lines.append(f"最も多い反応は「{top_label}」({top_count}件 / 全体の{top_count/total:.0%})")

    positive = sum(
        sentiment.get(k, 0) for k in ("称賛・好意", "笑い", "感謝", "共感", "応援・期待")
    )
    negative = sentiment.get("批判・不満", 0)
    if positive or negative:
        if negative == 0:
            lines.append("否定的なコメントはほとんど見られません")
        elif positive >= negative * 3:
            lines.append(f"好意的な反応が優勢(好意{positive}件 / 批判{negative}件)")
        elif negative > positive:
            lines.append(f"批判的な反応が目立ちます(好意{positive}件 / 批判{negative}件)")
        else:
            lines.append(f"賛否が分かれています(好意{positive}件 / 批判{negative}件)")

    requests_count = sentiment.get("要望・質問", 0)
    if requests_count / total >= 0.15:
        lines.append(
            f"要望・質問が{requests_count}件。次の企画のネタとして拾える可能性があります"
        )

    return lines


def dominant_color(thumbnail_url: str, timeout: float = 5.0) -> str | None:
    """サムネイル画像から代表色(最頻出ピクセル色)を#RRGGBB形式で返す。取得失敗時はNone。"""
    if not thumbnail_url:
        return None
    try:
        resp = requests.get(thumbnail_url, timeout=timeout)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content)).convert("RGB")
        image = image.resize((32, 32))
        counter = Counter(image.getdata())
        r, g, b = counter.most_common(1)[0][0]
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # noqa: BLE001
        return None
