from __future__ import annotations
import hashlib
from abc import abstractmethod
from datetime import datetime, timezone

from apify_client import ApifyClient

from config.config_loader import AppConfig
from models import RawPost
from scrapers.base_scraper import BaseScraper


class ApifyBaseScraper(BaseScraper):
    def __init__(self, config: AppConfig, since: datetime | None = None):
        super().__init__(config)
        self._since = since
        self._client = ApifyClient(config.apify_api_token)

    def scrape_all_keywords(self, keywords: list[str]) -> list[RawPost]:
        try:
            items = self._run_actor(keywords)
        except Exception as e:
            print(f"  Apify run failed: {e}")
            return []

        posts = []
        for item in items:
            try:
                post = self._to_raw_post(item)
                if post and (self._since is None or post.published_at.replace(tzinfo=timezone.utc) >= self._since.replace(tzinfo=timezone.utc)):
                    posts.append(post)
            except Exception:
                continue

        seen: dict[str, RawPost] = {}
        for p in posts:
            key = f"{p.platform}::{p.post_id}"
            if key not in seen:
                seen[key] = p
        return list(seen.values())

    def search(self, keyword: str) -> list[RawPost]:
        return self.scrape_all_keywords([keyword])

    def get_author_details(self, author_id: str) -> dict:
        return {"subscriber_count": 0}

    @abstractmethod
    def _run_actor(self, keywords: list[str]) -> list[dict]:
        ...

    @abstractmethod
    def _to_raw_post(self, item: dict) -> RawPost | None:
        ...

    @staticmethod
    def _id_hash(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()[:16]

    @staticmethod
    def _parse_dt(value) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)


class TikTokScraper(ApifyBaseScraper):
    def _run_actor(self, keywords: list[str]) -> list[dict]:
        run = self._client.actor(self.config.tiktok.actor_id).call(run_input={
            "searchQueries": keywords,
            "maxResults": self.config.tiktok.max_results,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        })
        return list(self._client.dataset(run["defaultDatasetId"]).iterate_items())

    def _to_raw_post(self, item: dict) -> RawPost | None:
        author = item.get("authorMeta", {})
        video_id = str(item.get("id") or self._id_hash(item.get("webVideoUrl", "")))
        url = item.get("webVideoUrl", "")
        if not url:
            return None
        return RawPost(
            platform="tiktok",
            post_id=video_id,
            author_id=str(author.get("id") or author.get("name") or "unknown"),
            author_name=author.get("nickName") or author.get("name") or "",
            title=item.get("text", "")[:200],
            body=item.get("text", ""),
            url=url,
            published_at=self._parse_dt(item.get("createTime")),
            views=int(item.get("playCount") or 0),
            likes=int(item.get("diggCount") or 0),
            comments_count=int(item.get("commentCount") or 0),
            subscriber_count=int(author.get("fans") or 0),
        )


class TwitterScraper(ApifyBaseScraper):
    def _run_actor(self, keywords: list[str]) -> list[dict]:
        run_input: dict = {
            "searchTerms": keywords,
            "maxItems": self.config.twitter.max_results,
            "lang": "en",
        }
        if self._since:
            run_input["since"] = self._since.strftime("%Y-%m-%d")
        run = self._client.actor(self.config.twitter.actor_id).call(run_input=run_input)
        return list(self._client.dataset(run["defaultDatasetId"]).iterate_items())

    def _to_raw_post(self, item: dict) -> RawPost | None:
        author = item.get("author", {})
        tweet_id = str(item.get("id") or self._id_hash(item.get("url", "")))
        url = item.get("url") or f"https://x.com/i/web/status/{tweet_id}"
        text = item.get("text") or item.get("fullText") or ""
        if not text:
            return None
        return RawPost(
            platform="twitter",
            post_id=tweet_id,
            author_id=str(author.get("id") or author.get("userName") or "unknown"),
            author_name=author.get("name") or author.get("userName") or "",
            title=text[:200],
            body=text,
            url=url,
            published_at=self._parse_dt(item.get("createdAt")),
            views=int(item.get("viewCount") or 0),
            likes=int(item.get("likeCount") or 0),
            comments_count=int(item.get("replyCount") or 0),
            subscriber_count=int(author.get("followers") or 0),
        )


class InstagramScraper(ApifyBaseScraper):
    def _run_actor(self, keywords: list[str]) -> list[dict]:
        all_items: list[dict] = []
        per_kw = max(1, self.config.instagram.max_results // len(keywords))
        for kw in keywords:
            # Instagram hashtags have no spaces
            hashtag = kw.replace(" ", "").lower()
            run = self._client.actor(self.config.instagram.actor_id).call(run_input={
                "search": hashtag,
                "searchType": "hashtag",
                "resultsType": "posts",
                "resultsLimit": per_kw,
            })
            all_items.extend(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        return all_items

    def _to_raw_post(self, item: dict) -> RawPost | None:
        post_id = str(item.get("id") or self._id_hash(item.get("url", "")))
        url = item.get("url") or item.get("shortCode") and f"https://www.instagram.com/p/{item['shortCode']}/"
        if not url:
            return None
        caption = item.get("caption") or ""
        return RawPost(
            platform="instagram",
            post_id=post_id,
            author_id=str(item.get("ownerId") or item.get("ownerUsername") or "unknown"),
            author_name=item.get("ownerFullName") or item.get("ownerUsername") or "",
            title=caption[:200],
            body=caption,
            url=url,
            published_at=self._parse_dt(item.get("timestamp")),
            views=int(item.get("videoViewCount") or 0),
            likes=int(item.get("likesCount") or 0),
            comments_count=int(item.get("commentsCount") or 0),
            subscriber_count=0,
        )
