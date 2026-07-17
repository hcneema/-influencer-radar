from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from models import ClassifiedPost, RawPost

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    topic_file TEXT NOT NULL,
    topic_hash TEXT NOT NULL,
    platforms TEXT NOT NULL,
    queries TEXT NOT NULL,
    posts_scraped INTEGER DEFAULT 0,
    influencers_found INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS authors (
    platform TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    subscriber_count INTEGER DEFAULT 0,
    author_type TEXT DEFAULT 'community',  -- 'official' | 'community'
    last_seen TEXT,
    PRIMARY KEY (platform, author_id)
);

CREATE TABLE IF NOT EXISTS posts (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    title TEXT,
    body TEXT,
    url TEXT NOT NULL,
    published_at TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    upvote_ratio REAL DEFAULT 0.0,
    subreddit TEXT DEFAULT '',
    first_seen_run INTEGER,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, author_id) REFERENCES authors(platform, author_id),
    FOREIGN KEY (first_seen_run) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS classifications (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    technical_depth TEXT,
    content_type TEXT,
    sentiment TEXT,
    classification_method TEXT,
    confidence REAL,
    classified_at TEXT,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id)
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def create_run(conn: sqlite3.Connection, meta: dict) -> int:
    cur = conn.execute(
        "INSERT INTO runs (run_at, topic_file, topic_hash, platforms, queries) VALUES (?,?,?,?,?)",
        (
            meta["run_at"],
            meta["topic_file"],
            meta["topic_hash"],
            json.dumps(meta["platforms"]),
            json.dumps(meta["queries"]),
        ),
    )
    conn.commit()
    return cur.lastrowid


def update_run(conn: sqlite3.Connection, run_id: int, posts_scraped: int, influencers_found: int) -> None:
    conn.execute(
        "UPDATE runs SET posts_scraped=?, influencers_found=? WHERE id=?",
        (posts_scraped, influencers_found, run_id),
    )
    conn.commit()


def upsert_author(conn: sqlite3.Connection, post: RawPost, author_type: str = "community") -> None:
    conn.execute(
        """INSERT INTO authors (platform, author_id, author_name, subscriber_count, author_type, last_seen)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(platform, author_id) DO UPDATE SET
               author_name=excluded.author_name,
               subscriber_count=excluded.subscriber_count,
               author_type=excluded.author_type,
               last_seen=excluded.last_seen""",
        (
            post.platform,
            post.author_id,
            post.author_name,
            post.subscriber_count,
            author_type,
            datetime.utcnow().isoformat(),
        ),
    )


def upsert_post(conn: sqlite3.Connection, post: RawPost, run_id: int) -> bool:
    """Returns True if the post was new (not previously in DB)."""
    existing = conn.execute(
        "SELECT 1 FROM posts WHERE platform=? AND post_id=?",
        (post.platform, post.post_id),
    ).fetchone()

    if existing:
        # update engagement counts (they change over time)
        conn.execute(
            """UPDATE posts SET views=?, likes=?, comments_count=?, upvote_ratio=?
               WHERE platform=? AND post_id=?""",
            (post.views, post.likes, post.comments_count, post.upvote_ratio,
             post.platform, post.post_id),
        )
        return False

    pub = post.published_at.isoformat() if post.published_at else None
    conn.execute(
        """INSERT INTO posts
           (platform, post_id, author_id, title, body, url, published_at,
            views, likes, comments_count, upvote_ratio, subreddit, first_seen_run)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            post.platform, post.post_id, post.author_id, post.title, post.body,
            post.url, pub, post.views, post.likes, post.comments_count,
            post.upvote_ratio, post.subreddit, run_id,
        ),
    )
    return True


def upsert_classification(conn: sqlite3.Connection, cp: ClassifiedPost) -> None:
    conn.execute(
        """INSERT INTO classifications
           (platform, post_id, technical_depth, content_type, sentiment,
            classification_method, confidence, classified_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(platform, post_id) DO UPDATE SET
               technical_depth=excluded.technical_depth,
               content_type=excluded.content_type,
               sentiment=excluded.sentiment,
               classification_method=excluded.classification_method,
               confidence=excluded.confidence,
               classified_at=excluded.classified_at""",
        (
            cp.raw.platform, cp.raw.post_id,
            cp.technical_depth, cp.content_type, cp.sentiment,
            cp.classification_method, cp.confidence,
            datetime.utcnow().isoformat(),
        ),
    )


def get_all_classified_posts(conn: sqlite3.Connection) -> list[ClassifiedPost]:
    rows = conn.execute(
        """SELECT p.*, a.author_name, a.subscriber_count, a.author_type,
                  c.technical_depth, c.content_type, c.sentiment,
                  c.classification_method, c.confidence
           FROM posts p
           JOIN classifications c ON p.platform=c.platform AND p.post_id=c.post_id
           LEFT JOIN authors a ON p.platform=a.platform AND p.author_id=a.author_id"""
    ).fetchall()
    return [_row_to_classified_post(r) for r in rows]


def get_posts_without_classification(conn: sqlite3.Connection) -> list[RawPost]:
    rows = conn.execute(
        """SELECT p.*, a.author_name, a.subscriber_count, a.author_type
           FROM posts p
           LEFT JOIN classifications c ON p.platform=c.platform AND p.post_id=c.post_id
           LEFT JOIN authors a ON p.platform=a.platform AND p.author_id=a.author_id
           WHERE c.post_id IS NULL"""
    ).fetchall()
    return [_row_to_raw_post(r) for r in rows]


def _row_to_raw_post(r: sqlite3.Row) -> RawPost:
    pub = datetime.fromisoformat(r["published_at"]) if r["published_at"] else datetime.utcnow()
    keys = r.keys()
    return RawPost(
        platform=r["platform"], post_id=r["post_id"], author_id=r["author_id"],
        author_name=r["author_name"] if "author_name" in keys else "",
        title=r["title"] or "", body=r["body"] or "",
        url=r["url"], published_at=pub,
        views=r["views"], likes=r["likes"], comments_count=r["comments_count"],
        upvote_ratio=r["upvote_ratio"],
        subscriber_count=r["subscriber_count"] if "subscriber_count" in keys else 0,
        subreddit=r["subreddit"] or "",
        author_type=r["author_type"] if "author_type" in keys else "community",
    )


def _row_to_classified_post(r: sqlite3.Row) -> ClassifiedPost:
    raw = _row_to_raw_post(r)
    return ClassifiedPost(
        raw=raw,
        technical_depth=r["technical_depth"] or "",
        content_type=r["content_type"] or "",
        sentiment=r["sentiment"] or "",
        classification_method=r["classification_method"] or "rule-based",
        confidence=r["confidence"] or 0.0,
    )
