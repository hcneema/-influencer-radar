from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import math


@dataclass
class RawPost:
    platform: str
    post_id: str
    author_id: str
    author_name: str
    title: str
    body: str
    url: str
    published_at: datetime
    views: int = 0
    likes: int = 0
    comments_count: int = 0
    upvote_ratio: float = 0.0
    subscriber_count: int = 0
    subreddit: str = ""
    author_type: str = "community"  # set from DB join; not scraped directly


@dataclass
class ClassifiedPost:
    raw: RawPost
    technical_depth: str = ""    # deep-technical | general-technical | non-technical
    content_type: str = ""       # tutorial | question | announcement | showcase | opinion
    sentiment: str = ""          # positive | negative | neutral
    classification_method: str = "rule-based"
    confidence: float = 0.0
    is_ambiguous: bool = False


@dataclass
class InfluencerProfile:
    author_id: str
    author_name: str
    platform: str
    subscriber_count: int
    total_posts: int
    engagement_score: float
    author_type: str = "community"   # "official" | "community"
    top_post_urls: list[str] = field(default_factory=list)
    category_breakdown: dict = field(default_factory=dict)
    posts: list[ClassifiedPost] = field(default_factory=list)


def engagement_score(post: RawPost) -> float:
    """Log-normalized engagement score comparable across YouTube and Reddit."""
    if post.platform == "youtube":
        return (
            math.log10(post.views + 1) * 0.5
            + math.log10(post.likes + 1) * 0.3
            + math.log10(post.comments_count + 1) * 0.2
        )
    else:  # reddit
        return (
            math.log10(max(post.likes, 0) + 1) * 0.6
            + math.log10(post.comments_count + 1) * 0.4
        )
