"""動画データから傾向(頻出ワード・タグ・ハッシュタグ・サムネイル色)を集計する。"""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO

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
