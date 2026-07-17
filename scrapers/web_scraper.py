from __future__ import annotations
import hashlib
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from config.config_loader import AppConfig
from models import RawPost
from scrapers.base_scraper import BaseScraper

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; influencer-radar/1.0; +https://github.com/hcneema/-influencer-radar)"
}
_TIMEOUT = 15


class WebScraper(BaseScraper):
    def __init__(self, config: AppConfig, since: datetime | None = None):
        super().__init__(config)
        self._since = since

    def search(self, url: str) -> list[RawPost]:
        """Each 'keyword' is a URL — either an RSS feed or an HTML page."""
        time.sleep(1)  # be polite
        try:
            if _is_feed(url):
                return self._scrape_feed(url)
            else:
                post = self._scrape_page(url)
                return [post] if post else []
        except Exception:
            return []

    def get_author_details(self, author_id: str) -> dict:
        return {"subscriber_count": 0}

    # ── RSS / Atom ────────────────────────────────────────────────────────────

    def _scrape_feed(self, url: str) -> list[RawPost]:
        feed = feedparser.parse(url)
        site_name = feed.feed.get("title", _domain(url))
        posts = []
        for entry in feed.entries:
            pub = _parse_feed_date(entry)
            if self._since and pub and pub < self._since:
                continue
            post_url = entry.get("link", "")
            if not post_url:
                continue
            body = _strip_html(entry.get("summary", "") or entry.get("content", [{}])[0].get("value", ""))
            author_name = entry.get("author", site_name)
            author_id = _slug(author_name)
            posts.append(RawPost(
                platform=_domain(url),
                post_id=_url_hash(post_url),
                author_id=author_id,
                author_name=author_name,
                title=entry.get("title", ""),
                body=body[:3000],
                url=post_url,
                published_at=pub or datetime.now(timezone.utc),
                views=0,
                likes=0,
                comments_count=0,
            ))
        return posts

    # ── Plain HTML page ───────────────────────────────────────────────────────

    def _scrape_page(self, url: str) -> RawPost | None:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        title = _meta(soup, ["og:title", "twitter:title"]) or (soup.title.string.strip() if soup.title else "")
        author_name = _meta(soup, ["author", "article:author"]) or _domain(url)
        pub = _parse_html_date(soup)

        if self._since and pub and pub < self._since:
            return None

        body = _extract_body(soup)
        return RawPost(
            platform=_domain(url),
            post_id=_url_hash(url),
            author_id=_slug(author_name),
            author_name=author_name,
            title=title,
            body=body[:3000],
            url=url,
            published_at=pub or datetime.now(timezone.utc),
            views=0,
            likes=0,
            comments_count=0,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_feed(url: str) -> bool:
    """Detect RSS/Atom feeds by URL hints or content-type."""
    lower = url.lower()
    if any(x in lower for x in ["/feed", "/rss", "/atom", ".xml", "feed=rss"]):
        return True
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        ct = resp.headers.get("content-type", "")
        return any(x in ct for x in ["xml", "rss", "atom"])
    except Exception:
        return False


def _domain(url: str) -> str:
    host = urlparse(url).netloc
    return host.replace("www.", "")


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_")[:64]


def _strip_html(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()


def _meta(soup: BeautifulSoup, names: list[str]) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _parse_feed_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _parse_html_date(soup: BeautifulSoup) -> datetime | None:
    # try meta tags first
    for prop in ["article:published_time", "datePublished", "pubdate"]:
        val = _meta(soup, [prop])
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                pass
    # try <time> element
    tag = soup.find("time")
    if tag and tag.get("datetime"):
        try:
            return datetime.fromisoformat(tag["datetime"].replace("Z", "+00:00"))
        except Exception:
            pass
    return None


def _extract_body(soup: BeautifulSoup) -> str:
    """Extract main article text using common content selectors."""
    for selector in ["article", "main", "[role='main']", ".post-content",
                     ".article-body", ".entry-content", ".content"]:
        tag = soup.select_one(selector)
        if tag:
            return tag.get_text(separator=" ").strip()
    # fallback: all paragraphs
    return " ".join(p.get_text() for p in soup.find_all("p")).strip()
