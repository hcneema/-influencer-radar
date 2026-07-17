from __future__ import annotations
from pathlib import Path


def expand_topic(topic_file: Path, num_queries: int = 12) -> list[str]:
    """Read topic file and return non-comment, non-blank lines as search queries."""
    return _read_topic_lines(topic_file)


def _read_topic_lines(topic_file: Path) -> list[str]:
    if not topic_file.exists():
        raise FileNotFoundError(f"Topic file not found: {topic_file}")
    lines = topic_file.read_text(encoding="utf-8").splitlines()
    return [
        l.strip()
        for l in lines
        if l.strip() and not l.strip().startswith("#") and len(l.strip()) > 3
    ]
