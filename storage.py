"""競合チャンネルリストのローカル永続化。

Streamlit Cloudのディスクは再デプロイ・長期休止でリセットされる可能性があるため、
あくまで「稼働中の間だけ確実に残る」簡易的な保存として扱う。
"""

from __future__ import annotations

import json
from pathlib import Path

_STORE_PATH = Path(__file__).parent / "data" / "competitors.json"


def load_competitors() -> list[dict]:
    if not _STORE_PATH.exists():
        return []
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_competitor(channel_id: str, title: str, query: str) -> list[dict]:
    items = load_competitors()
    if any(c["channel_id"] == channel_id for c in items):
        return items
    items.append({"channel_id": channel_id, "title": title, "query": query})
    _save(items)
    return items


def remove_competitor(channel_id: str) -> list[dict]:
    items = [c for c in load_competitors() if c["channel_id"] != channel_id]
    _save(items)
    return items
