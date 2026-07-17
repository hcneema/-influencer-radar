from __future__ import annotations
from pathlib import Path


def expand_topic(topic_file: Path, num_queries: int = 12) -> tuple[list[str], list[str]]:
    """Read topic file and return (search_queries, web_urls) as two separate lists.

    Lines starting with http are treated as websites/feeds to scrape.
    All other non-blank, non-comment lines are search queries.
    """
    lines = _read_topic_lines(topic_file)
    queries = [l for l in lines if not l.lower().startswith("http")]
    urls = [l for l in lines if l.lower().startswith("http")]
    return queries, urls


def _read_topic_lines(topic_file: Path) -> list[str]:
    if not topic_file.exists():
        raise FileNotFoundError(f"Topic file not found: {topic_file}")
    lines = topic_file.read_text(encoding="utf-8").splitlines()
    return [
        l.strip()
        for l in lines
        if l.strip() and not l.strip().startswith("#") and len(l.strip()) > 3
    ]
