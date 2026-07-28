"""動画データから傾向(頻出ワード・タグ・ハッシュタグ・サムネイル色)を集計する。"""

from __future__ import annotations

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
