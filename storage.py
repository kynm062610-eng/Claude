"""競合チャンネルリストと直近の分析結果のローカル永続化。

Streamlit Cloudのディスクは再デプロイ・長期休止でリセットされる可能性があるため、
あくまで「稼働中の間だけ確実に残る」簡易的な保存として扱う。
分析結果を残しているのは、ファイル保存などで画面が再読み込みされたときに
結果が消えてしまわないようにするため。
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd

_DATA_DIR = Path(__file__).parent / "data"
_STORE_PATH = _DATA_DIR / "competitors.json"
_RESULTS_DIR = _DATA_DIR / "results"


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


# ----------------------------------------------------------------------
# 直近の分析結果
# ----------------------------------------------------------------------
def save_result(name: str, payload: dict) -> None:
    """分析結果(DataFrame + 付随情報)をJSONとして保存する。"""
    meta = {k: v for k, v in payload.items() if k != "df"}
    df: pd.DataFrame = payload.get("df")
    record = {
        "meta": meta,
        "df": df.to_json(orient="records", date_format="iso") if df is not None else None,
    }
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / f"{name}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # 保存できなくても画面表示は続行する


def load_result(name: str) -> dict | None:
    """保存済みの分析結果を復元する。無い・壊れている場合はNone。"""
    path = _RESULTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        df_json = record.get("df")
        df = pd.read_json(StringIO(df_json), orient="records") if df_json else pd.DataFrame()
        if "published_at" in df.columns and not df.empty:
            df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
        if "tags" in df.columns:
            df["tags"] = df["tags"].apply(lambda t: list(t) if isinstance(t, (list, tuple)) else [])
        payload = dict(record.get("meta", {}))
        payload["df"] = df
        return payload
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def save_comments(name: str, comments: list[str]) -> None:
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / f"comments_{name}.json").write_text(
            json.dumps(comments, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def load_comments(name: str) -> list[str] | None:
    path = _RESULTS_DIR / f"comments_{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
