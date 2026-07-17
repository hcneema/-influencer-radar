from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import IO

from models import RawPost


def open_cache(run_at: datetime, cache_dir: Path) -> IO[str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = run_at.strftime("%Y-%m-%dT%H%M%S") + "_run.jsonl"
    return open(cache_dir / filename, "a", encoding="utf-8")


def append_post(cache_file: IO[str], post: RawPost) -> None:
    record = {
        "platform": post.platform,
        "post_id": post.post_id,
        "author_id": post.author_id,
        "author_name": post.author_name,
        "title": post.title,
        "body": post.body[:2000],  # truncate to keep files manageable
        "url": post.url,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "views": post.views,
        "likes": post.likes,
        "comments_count": post.comments_count,
        "upvote_ratio": post.upvote_ratio,
        "subscriber_count": post.subscriber_count,
        "subreddit": post.subreddit,
    }
    cache_file.write(json.dumps(record) + "\n")
    cache_file.flush()
