from __future__ import annotations
import time
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, retry_if_exception

from config.config_loader import AppConfig
from dateutil_helper import to_rfc3339
from models import RawPost
from scrapers.base_scraper import BaseScraper


_TRANSCRIPT_MAX_CHARS = 4000  # truncation limit to control classifier token cost


class YouTubeScraper(BaseScraper):
    def __init__(self, config: AppConfig, since: datetime | None = None, fetch_transcripts: bool = False):
        super().__init__(config)
        self._client = build("youtube", "v3", developerKey=config.youtube_api_key)
        self._channel_cache: dict[str, dict] = {}
        self._quota_exhausted = False
        self._published_after: str | None = to_rfc3339(since) if since else None
        self._fetch_transcripts = fetch_transcripts

    def search(self, keyword: str) -> list[RawPost]:
        if self._quota_exhausted:
            return []

        video_ids: list[str] = []
        search_items: dict[str, dict] = {}  # video_id -> search result item
        next_page = None
        fetched = 0
        max_results = self.config.youtube.max_results

        while fetched < max_results:
            batch_size = min(50, max_results - fetched)
            try:
                resp = self._search_page(keyword, batch_size, next_page)
            except HttpError as e:
                if e.resp.status in (403, 429):
                    self._quota_exhausted = True
                    return self._build_posts(video_ids, search_items)
                raise

            for item in resp.get("items", []):
                vid_id = item["id"].get("videoId")
                if vid_id:
                    video_ids.append(vid_id)
                    search_items[vid_id] = item

            fetched += len(resp.get("items", []))
            next_page = resp.get("nextPageToken")
            if not next_page:
                break

        return self._build_posts(video_ids, search_items)

    @retry(
        retry=retry_if_exception(lambda e: isinstance(e, HttpError) and e.resp.status == 429),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
    )
    def _search_page(self, keyword: str, max_results: int, page_token: str | None) -> dict:
        params = dict(
            part="snippet",
            q=keyword,
            type="video",
            maxResults=max_results,
            order=self.config.youtube.search_order,
            pageToken=page_token,
        )
        if self._published_after:
            params["publishedAfter"] = self._published_after
        return self._client.search().list(**params).execute()

    def _build_posts(self, video_ids: list[str], search_items: dict[str, dict]) -> list[RawPost]:
        if not video_ids:
            return []

        # batch fetch video statistics (up to 50 per call)
        stats_map: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                resp = self._fetch_video_stats(batch)
                for item in resp.get("items", []):
                    stats_map[item["id"]] = item.get("statistics", {})
            except HttpError:
                pass

        posts = []
        for vid_id in video_ids:
            item = search_items.get(vid_id, {})
            stats = stats_map.get(vid_id, {})
            snippet = item.get("snippet", {})
            channel_id = snippet.get("channelId", "")
            channel_info = self.get_author_details(channel_id)
            post = self._parse_video(vid_id, snippet, stats, channel_info)
            if self._fetch_transcripts:
                transcript = _fetch_transcript(vid_id)
                if transcript:
                    post.body = f"{post.body}\n\n[TRANSCRIPT]\n{transcript}"
            posts.append(post)

        return posts

    @retry(
        retry=retry_if_exception(lambda e: isinstance(e, HttpError) and e.resp.status == 429),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
    )
    def _fetch_video_stats(self, video_ids: list[str]) -> dict:
        return self._client.videos().list(
            part="statistics",
            id=",".join(video_ids),
        ).execute()

    def get_author_details(self, author_id: str) -> dict:
        if not author_id:
            return {"subscriber_count": 0}
        if author_id in self._channel_cache:
            return self._channel_cache[author_id]
        try:
            resp = self._client.channels().list(
                part="statistics,snippet",
                id=author_id,
            ).execute()
            items = resp.get("items", [])
            if items:
                stats = items[0].get("statistics", {})
                result = {
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                }
            else:
                result = {"subscriber_count": 0}
        except HttpError:
            result = {"subscriber_count": 0}
        self._channel_cache[author_id] = result
        return result

    def _parse_video(
        self,
        video_id: str,
        snippet: dict,
        stats: dict,
        channel_info: dict,
    ) -> RawPost:
        pub_str = snippet.get("publishedAt", "")
        try:
            published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published_at = datetime.utcnow()

        return RawPost(
            platform="youtube",
            post_id=video_id,
            author_id=snippet.get("channelId", ""),
            author_name=snippet.get("channelTitle", ""),
            title=snippet.get("title", ""),
            body=snippet.get("description", ""),
            url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=published_at,
            views=int(stats.get("viewCount", 0)),
            likes=int(stats.get("likeCount", 0)),
            comments_count=int(stats.get("commentCount", 0)),
            upvote_ratio=0.0,
            subscriber_count=channel_info.get("subscriber_count", 0),
            subreddit="",
        )


def _fetch_transcript(video_id: str) -> str:
    """
    Fetch auto-generated captions via youtube-transcript-api.
    Returns plain text truncated to _TRANSCRIPT_MAX_CHARS, or "" on any failure.
    Failures are silent — transcripts are optional enrichment, not critical.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        entries = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        text = " ".join(e["text"] for e in entries)
        return text[:_TRANSCRIPT_MAX_CHARS]
    except Exception:
        return ""
