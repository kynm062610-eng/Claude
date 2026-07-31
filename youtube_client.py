"""YouTube Data API v3 のラッパー。

自分のチャンネル分析・トレンド調査・競合チャンネル分析に必要な
最小限の呼び出しをまとめたクライアント。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


@dataclass
class VideoStats:
    video_id: str
    title: str
    channel_title: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    thumbnail_url: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class ChannelStats:
    channel_id: str
    title: str
    description: str
    subscriber_count: int
    view_count: int
    video_count: int
    thumbnail_url: str = ""
    uploads_playlist_id: str = ""


class YouTubeClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YouTube Data API キーが設定されていません")
        self._youtube = build("youtube", "v3", developerKey=api_key)

    # ------------------------------------------------------------------
    # チャンネル解決
    # ------------------------------------------------------------------
    def resolve_channel_id(self, query: str) -> str | None:
        """チャンネルID・@ハンドル・チャンネル名のいずれかからチャンネルIDを取得する。"""
        query = query.strip()
        if query.startswith("UC") and len(query) == 24:
            return query

        handle = query if query.startswith("@") else f"@{query}"
        try:
            resp = self._youtube.channels().list(part="id", forHandle=handle).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["id"]
        except HttpError:
            pass

        resp = self._youtube.search().list(
            part="snippet", q=query, type="channel", maxResults=1
        ).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
        return None

    # ------------------------------------------------------------------
    # 自分のチャンネル / 競合チャンネル分析
    # ------------------------------------------------------------------
    def get_channel_stats(self, channel_id: str) -> ChannelStats | None:
        resp = self._youtube.channels().list(
            part="snippet,statistics,contentDetails", id=channel_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        snippet = item["snippet"]
        stats = item["statistics"]
        uploads_id = item["contentDetails"]["relatedPlaylists"]["uploads"]
        return ChannelStats(
            channel_id=item["id"],
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            subscriber_count=int(stats.get("subscriberCount", 0)),
            view_count=int(stats.get("viewCount", 0)),
            video_count=int(stats.get("videoCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            uploads_playlist_id=uploads_id,
        )

    def get_channel_videos(self, channel_id: str, max_results: int = 20) -> list[VideoStats]:
        stats = self.get_channel_stats(channel_id)
        if not stats or not stats.uploads_playlist_id:
            return []

        video_ids: list[str] = []
        page_token = None
        while len(video_ids) < max_results:
            resp = self._youtube.playlistItems().list(
                part="contentDetails",
                playlistId=stats.uploads_playlist_id,
                maxResults=min(50, max_results - len(video_ids)),
                pageToken=page_token,
            ).execute()
            video_ids.extend(
                item["contentDetails"]["videoId"] for item in resp.get("items", [])
            )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return self._get_videos_stats(video_ids)

    # ------------------------------------------------------------------
    # トレンド / キーワード調査
    # ------------------------------------------------------------------
    def search_trending_videos(
        self,
        query: str,
        max_results: int = 20,
        published_within_days: int | None = 30,
        order: str = "viewCount",
    ) -> list[VideoStats]:
        params = dict(
            part="id",
            q=query,
            type="video",
            order=order,
            maxResults=min(50, max_results),
        )
        if published_within_days:
            since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=published_within_days)
            params["publishedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = self._youtube.search().list(**params).execute()
        video_ids = [item["id"]["videoId"] for item in resp.get("items", [])]
        return self._get_videos_stats(video_ids)

    def get_most_popular(self, region_code: str = "JP", category_id: str | None = None,
                          max_results: int = 20) -> list[VideoStats]:
        params = dict(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode=region_code,
            maxResults=min(50, max_results),
        )
        if category_id:
            params["videoCategoryId"] = category_id
        resp = self._youtube.videos().list(**params).execute()
        return [self._video_from_item(item) for item in resp.get("items", [])]

    # ------------------------------------------------------------------
    # コメント取得
    # ------------------------------------------------------------------
    def get_video_comments(self, video_id: str, max_results: int = 50) -> list[dict]:
        """動画のトップレベルコメントを取得する。

        本文だけでなく投稿者・高評価数・投稿日時も返すため、そのまま書き出せる。
        コメント無効・限定公開などで取得できない動画は空リストを返す。
        """
        comments: list[dict] = []
        page_token = None
        try:
            while len(comments) < max_results:
                resp = self._youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=min(100, max_results - len(comments)),
                    order="relevance",
                    textFormat="plainText",
                    pageToken=page_token,
                ).execute()
                for item in resp.get("items", []):
                    snippet = item["snippet"]["topLevelComment"]["snippet"]
                    text = snippet.get("textDisplay", "").strip()
                    if not text:
                        continue
                    comments.append({
                        "text": text,
                        "author": snippet.get("authorDisplayName", ""),
                        "like_count": int(snippet.get("likeCount", 0)),
                        "published_at": snippet.get("publishedAt", ""),
                        "video_id": video_id,
                    })
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError:
            return comments
        return comments

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------
    def _get_videos_stats(self, video_ids: list[str]) -> list[VideoStats]:
        results: list[VideoStats] = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            if not batch:
                continue
            resp = self._youtube.videos().list(
                part="snippet,statistics", id=",".join(batch)
            ).execute()
            results.extend(self._video_from_item(item) for item in resp.get("items", []))
        return results

    @staticmethod
    def _video_from_item(item: dict) -> VideoStats:
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        return VideoStats(
            video_id=item["id"],
            title=snippet.get("title", ""),
            channel_title=snippet.get("channelTitle", ""),
            published_at=snippet.get("publishedAt", ""),
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats.get("likeCount", 0)),
            comment_count=int(stats.get("commentCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
            description=snippet.get("description", ""),
            tags=list(snippet.get("tags", [])),
        )
