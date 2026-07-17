from __future__ import annotations
from abc import ABC, abstractmethod

from config.config_loader import AppConfig
from models import RawPost


class BaseScraper(ABC):
    def __init__(self, config: AppConfig):
        self.config = config

    @abstractmethod
    def search(self, keyword: str) -> list[RawPost]:
        """Search for a single keyword. Must handle rate limiting internally."""
        ...

    @abstractmethod
    def get_author_details(self, author_id: str) -> dict:
        """Fetch author metadata. Returns dict with at least {'subscriber_count': int}."""
        ...

    def scrape_all_keywords(self, keywords: list[str]) -> list[RawPost]:
        """Run search for every keyword, deduplicate by post_id, return combined results."""
        seen: dict[str, RawPost] = {}
        for keyword in keywords:
            for post in self.search(keyword):
                key = f"{post.platform}::{post.post_id}"
                if key not in seen:
                    seen[key] = post
        return list(seen.values())
