from __future__ import annotations
from collections import Counter, defaultdict

from models import ClassifiedPost, InfluencerProfile, engagement_score


def run_analysis(
    posts: list[ClassifiedPost],
    min_posts: int,
) -> list[InfluencerProfile]:
    grouped = _group_posts_by_author(posts)
    profiles = []
    for author_key, author_posts in grouped.items():
        profile = _build_influencer_profile(author_key, author_posts, min_posts)
        if profile is not None:
            profiles.append(profile)
    profiles.sort(key=lambda p: p.engagement_score, reverse=True)
    return profiles


def _group_posts_by_author(posts: list[ClassifiedPost]) -> dict[str, list[ClassifiedPost]]:
    groups: dict[str, list[ClassifiedPost]] = defaultdict(list)
    for post in posts:
        key = f"{post.raw.platform}::{post.raw.author_id}"
        groups[key].append(post)
    return dict(groups)


def _build_influencer_profile(
    author_key: str,
    posts: list[ClassifiedPost],
    min_posts: int,
) -> InfluencerProfile | None:
    if len(posts) < min_posts:
        return None

    platform, author_id = author_key.split("::", 1)
    sample = posts[0].raw

    score = _score_author(posts)

    sorted_posts = sorted(posts, key=lambda p: engagement_score(p.raw), reverse=True)
    top_urls = [p.raw.url for p in sorted_posts[:3]]

    author_type = sample.author_type

    return InfluencerProfile(
        author_id=author_id,
        author_name=sample.author_name,
        platform=platform,
        subscriber_count=sample.subscriber_count,
        total_posts=len(posts),
        engagement_score=round(score, 3),
        author_type=author_type,
        top_post_urls=top_urls,
        category_breakdown=_compute_category_breakdown(posts),
        posts=posts,
    )


def _score_author(posts: list[ClassifiedPost]) -> float:
    import math
    total = sum(engagement_score(p.raw) for p in posts)
    # reward consistent posting without letting a single viral post dominate
    return total * math.log10(len(posts) + 1)


def _compute_category_breakdown(posts: list[ClassifiedPost]) -> dict[str, dict[str, int]]:
    depth_c: Counter = Counter()
    ctype_c: Counter = Counter()
    sent_c: Counter = Counter()

    for p in posts:
        depth_c[p.technical_depth] += 1
        ctype_c[p.content_type] += 1
        sent_c[p.sentiment] += 1

    return {
        "technical_depth": dict(depth_c),
        "content_type": dict(ctype_c),
        "sentiment": dict(sent_c),
    }
