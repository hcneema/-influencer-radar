from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class YoutubeConfig:
    enabled: bool
    search_order: str
    max_results: int


@dataclass
class RedditConfig:
    enabled: bool
    subreddits: list[str]
    sort: str
    time_filter: str
    max_results: int


@dataclass
class OutputConfig:
    format: str
    directory: Path


@dataclass
class ClassifierConfig:
    ambiguity_threshold: float


@dataclass
class InfluencerConfig:
    min_posts_threshold: int


@dataclass
class TopicExpanderConfig:
    num_queries: int


@dataclass
class ApifyPlatformConfig:
    enabled: bool
    max_results: int
    actor_id: str


@dataclass
class AppConfig:
    youtube: YoutubeConfig
    reddit: RedditConfig
    output: OutputConfig
    classifier: ClassifierConfig
    influencer: InfluencerConfig
    topic_expander: TopicExpanderConfig
    tiktok: ApifyPlatformConfig | None = None
    twitter: ApifyPlatformConfig | None = None
    instagram: ApifyPlatformConfig | None = None
    # injected from environment by main.py, not from YAML
    youtube_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = ""
    apify_api_token: str = ""


def load_config(platforms_path: Path = Path("config/platforms.yaml")) -> AppConfig:
    data = _load_yaml(platforms_path)
    p = data.get("platforms", {})
    yt_raw = p.get("youtube", {})
    rd_raw = p.get("reddit", {})
    out_raw = data.get("output", {})
    cl_raw = data.get("classifier", {})
    inf_raw = data.get("influencer", {})
    te_raw = data.get("topic_expander", {})

    return AppConfig(
        youtube=YoutubeConfig(
            enabled=yt_raw.get("enabled", True),
            search_order=yt_raw.get("search_order", "relevance"),
            max_results=int(yt_raw.get("max_results", 50)),
        ),
        reddit=RedditConfig(
            enabled=rd_raw.get("enabled", True),
            subreddits=rd_raw.get("subreddits", ["fpga"]),
            sort=rd_raw.get("sort", "relevance"),
            time_filter=rd_raw.get("time_filter", "all"),
            max_results=int(rd_raw.get("max_results", 100)),
        ),
        output=OutputConfig(
            format=out_raw.get("format", "both"),
            directory=Path(out_raw.get("directory", "reports/")),
        ),
        classifier=ClassifierConfig(
            ambiguity_threshold=float(cl_raw.get("ambiguity_threshold", 0.4)),
        ),
        influencer=InfluencerConfig(
            min_posts_threshold=int(inf_raw.get("min_posts_threshold", 2)),
        ),
        topic_expander=TopicExpanderConfig(
            num_queries=int(te_raw.get("num_queries", 12)),
        ),
        tiktok=_apify_platform(data.get("tiktok", {}), "clockworks/tiktok-scraper", 50),
        twitter=_apify_platform(data.get("twitter", {}), "apidojo/tweet-scraper", 50),
        instagram=_apify_platform(data.get("instagram", {}), "apify/instagram-scraper", 50),
    )


def _apify_platform(raw: dict, default_actor: str, default_max: int) -> ApifyPlatformConfig:
    return ApifyPlatformConfig(
        enabled=raw.get("enabled", True),
        max_results=int(raw.get("max_results", default_max)),
        actor_id=raw.get("actor_id", default_actor),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
