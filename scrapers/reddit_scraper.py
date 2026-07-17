from __future__ import annotations
from datetime import datetime, timezone

import praw
import prawcore
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.config_loader import AppConfig
from dateutil_helper import reddit_time_filter
from models import RawPost
from scrapers.base_scraper import BaseScraper


class RedditScraper(BaseScraper):
    def __init__(self, config: AppConfig, since: datetime | None = None):
        super().__init__(config)
        self._reddit = praw.Reddit(
            client_id=config.reddit_client_id,
            client_secret=config.reddit_client_secret,
            user_agent=config.reddit_user_agent,
        )
        self._author_cache: dict[str, int] = {}
        # Reddit only supports preset buckets; pick nearest that covers the range
        self._time_filter = reddit_time_filter(since)
        # exact cutoff for post-fetch filtering (since Reddit buckets are coarse)
        self._since_ts: float | None = since.timestamp() if since else None

    def search(self, keyword: str) -> list[RawPost]:
        posts: dict[str, RawPost] = {}

        for sub_name in self.config.reddit.subreddits:
            for submission in self._fetch_subreddit_results(sub_name, keyword):
                post = self._parse_submission(submission)
                if post.post_id not in posts:
                    posts[post.post_id] = post

        # fallback: also search r/all if we got fewer than 5 results across all subreddits
        if len(posts) < 5:
            for submission in self._fetch_subreddit_results("all", keyword):
                post = self._parse_submission(submission)
                if post.post_id not in posts:
                    posts[post.post_id] = post

        return list(posts.values())

    @retry(
        retry=retry_if_exception_type(prawcore.exceptions.TooManyRequests),
        wait=wait_exponential(multiplier=1, min=2, max=120),
        stop=stop_after_attempt(6),
    )
    def _fetch_subreddit_results(
        self, subreddit_name: str, keyword: str
    ) -> list[praw.models.Submission]:
        try:
            sub = self._reddit.subreddit(subreddit_name)
            results = sub.search(
                keyword,
                sort=self.config.reddit.sort,
                time_filter=self._time_filter,
                limit=self.config.reddit.max_results,
            )
            submissions = list(results)
            # secondary filter: drop posts outside the exact since cutoff
            if self._since_ts is not None:
                submissions = [s for s in submissions if s.created_utc >= self._since_ts]
            return submissions
        except (prawcore.exceptions.Forbidden, prawcore.exceptions.NotFound):
            return []
        except prawcore.exceptions.TooManyRequests:
            raise  # let tenacity handle it

    def get_author_details(self, author_id: str) -> dict:
        if not author_id or author_id == "[deleted]":
            return {"subscriber_count": 0}
        if author_id in self._author_cache:
            return {"subscriber_count": self._author_cache[author_id]}
        try:
            redditor = self._reddit.redditor(author_id)
            karma = (redditor.link_karma or 0) + (redditor.comment_karma or 0)
        except Exception:
            karma = 0
        self._author_cache[author_id] = karma
        return {"subscriber_count": karma}

    def _parse_submission(self, submission: praw.models.Submission) -> RawPost:
        author_name = str(submission.author) if submission.author else "[deleted]"

        # fetch author karma (cached)
        author_info = self.get_author_details(author_name)

        return RawPost(
            platform="reddit",
            post_id=submission.id,
            author_id=author_name,
            author_name=author_name,
            title=submission.title,
            body=submission.selftext or "",
            url=f"https://www.reddit.com{submission.permalink}",
            published_at=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
            views=0,  # Reddit does not expose view counts
            likes=submission.score,
            comments_count=submission.num_comments,
            upvote_ratio=submission.upvote_ratio,
            subscriber_count=author_info.get("subscriber_count", 0),
            subreddit=submission.subreddit.display_name,
        )
