"""
Trend and anomaly analysis over the SQLite posts database.
All queries run directly on the DB so they work across all historical runs,
not just the current scrape session.
"""
from __future__ import annotations
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PeriodBucket:
    period: str          # e.g. "2024-W03" or "2024-06"
    post_count: int
    unique_authors: int
    avg_engagement: float
    sentiment_pos: int
    sentiment_neg: int
    sentiment_neu: int
    new_authors: int     # authors whose first post falls in this period


@dataclass
class EngagementAnomaly:
    platform: str
    post_id: str
    title: str
    url: str
    author_name: str
    published_at: str
    engagement_score: float
    z_score: float       # how many std devs above the platform mean


@dataclass
class TrendsReport:
    generated_at: str
    granularity: str                          # "week" | "month"
    since: str | None
    buckets: list[PeriodBucket]
    anomalies: list[EngagementAnomaly]
    rising_authors: list[dict]                # authors with most posts in latest period
    sentiment_shift: dict                     # earliest vs latest period sentiment comparison


def run_trends(
    conn: sqlite3.Connection,
    granularity: str = "week",
    since: datetime | None = None,
    anomaly_z_threshold: float = 2.0,
) -> TrendsReport:
    """
    Full trends analysis pipeline.
    granularity: "week" or "month"
    since: only include posts published after this datetime (None = all history)
    """
    since_str = since.isoformat() if since else None

    buckets = _compute_buckets(conn, granularity, since_str)
    anomalies = _detect_anomalies(conn, anomaly_z_threshold, since_str)
    rising = _rising_authors(conn, granularity, since_str)
    shift = _sentiment_shift(buckets)

    return TrendsReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        granularity=granularity,
        since=since_str,
        buckets=buckets,
        anomalies=anomalies,
        rising_authors=rising,
        sentiment_shift=shift,
    )


def _period_expr(granularity: str) -> str:
    """SQLite strftime expression for grouping."""
    if granularity == "week":
        return "strftime('%Y-W%W', published_at)"
    return "strftime('%Y-%m', published_at)"


def _compute_buckets(
    conn: sqlite3.Connection,
    granularity: str,
    since_str: str | None,
) -> list[PeriodBucket]:
    period = _period_expr(granularity)
    where = "WHERE p.published_at > ?" if since_str else ""
    params = (since_str,) if since_str else ()

    # fetch raw rows; compute engagement in Python (SQLite has no LOG10)
    raw_rows = conn.execute(
        f"""
        SELECT
            {period} AS period,
            p.platform, p.views, p.likes, p.comments_count,
            c.sentiment
        FROM posts p
        LEFT JOIN classifications c ON p.platform = c.platform AND p.post_id = c.post_id
        {where}
        ORDER BY period
        """,
        params,
    ).fetchall()

    # aggregate by period in Python
    import math
    from collections import defaultdict
    buckets_raw: dict[str, dict] = {}
    bare_where = "WHERE published_at > ?" if since_str else ""
    author_rows = conn.execute(
        f"SELECT {period} AS period, COUNT(DISTINCT author_id) AS ua, "
        f"COUNT(DISTINCT post_id) AS pc FROM posts {bare_where} GROUP BY period",
        params,
    ).fetchall()
    for r in author_rows:
        p = r["period"] or "unknown"
        buckets_raw[p] = {"post_count": r["pc"], "unique_authors": r["ua"],
                          "eng_sum": 0.0, "eng_n": 0,
                          "pos": 0, "neg": 0, "neu": 0}

    for r in raw_rows:
        p = r["period"] or "unknown"
        if p not in buckets_raw:
            continue
        # log-normalized engagement (same formula as models.py)
        v, l, c = r["views"] or 0, r["likes"] or 0, r["comments_count"] or 0
        if r["platform"] == "youtube":
            eng = 0.5 * math.log10(v + 1) + 0.3 * math.log10(l + 1) + 0.2 * math.log10(c + 1)
        else:
            eng = 0.6 * math.log10(max(l, 0) + 1) + 0.4 * math.log10(c + 1)
        buckets_raw[p]["eng_sum"] += eng
        buckets_raw[p]["eng_n"] += 1
        sent = r["sentiment"] or "neutral"
        if sent == "positive":
            buckets_raw[p]["pos"] += 1
        elif sent == "negative":
            buckets_raw[p]["neg"] += 1
        else:
            buckets_raw[p]["neu"] += 1

    # convert to list of Row-like dicts for the rest of the function
    rows = [
        {"period": p, **d,
         "avg_engagement": (d["eng_sum"] / d["eng_n"]) if d["eng_n"] else 0.0}
        for p, d in sorted(buckets_raw.items())
    ]

    # compute per-period new authors
    first_seen = _first_seen_per_author(conn, since_str)
    first_by_period: dict[str, int] = {}
    for fp in first_seen.values():
        if fp:
            key = _format_period(fp, granularity)
            first_by_period[key] = first_by_period.get(key, 0) + 1

    buckets = []
    for r in rows:
        p = r["period"] or "unknown"
        buckets.append(PeriodBucket(
            period=p,
            post_count=r["post_count"],
            unique_authors=r["unique_authors"],
            avg_engagement=round(r["avg_engagement"], 3),
            sentiment_pos=r["pos"],
            sentiment_neg=r["neg"],
            sentiment_neu=r["neu"],
            new_authors=first_by_period.get(p, 0),
        ))
    return buckets


def _first_seen_per_author(
    conn: sqlite3.Connection, since_str: str | None
) -> dict[str, str | None]:
    where = "WHERE published_at > ?" if since_str else ""
    params = (since_str,) if since_str else ()
    rows = conn.execute(
        f"SELECT author_id, MIN(published_at) AS first FROM posts {where} GROUP BY author_id",
        params,
    ).fetchall()
    return {r["author_id"]: r["first"] for r in rows}


def _format_period(iso_str: str, granularity: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if granularity == "week":
            return dt.strftime("%Y-W%W")
        return dt.strftime("%Y-%m")
    except (ValueError, AttributeError):
        return "unknown"


def _detect_anomalies(
    conn: sqlite3.Connection,
    z_threshold: float,
    since_str: str | None,
) -> list[EngagementAnomaly]:
    where = "WHERE p.published_at > ?" if since_str else ""
    params = (since_str,) if since_str else ()

    rows = conn.execute(
        f"""
        SELECT p.platform, p.post_id, p.title, p.url, p.author_id,
               a.author_name, p.published_at,
               p.views, p.likes, p.comments_count
        FROM posts p
        LEFT JOIN authors a ON p.platform = a.platform AND p.author_id = a.author_id
        {where}
        """,
        params,
    ).fetchall()

    if not rows:
        return []

    # compute engagement scores per platform
    from models import RawPost
    from datetime import datetime as dt_cls

    platform_scores: dict[str, list[tuple]] = {}
    for r in rows:
        from models import engagement_score as _eng
        post = RawPost(
            platform=r["platform"], post_id=r["post_id"], author_id=r["author_id"],
            author_name=r["author_name"] or "", title=r["title"] or "", body="",
            url=r["url"], published_at=dt_cls.utcnow(),
            views=r["views"], likes=r["likes"], comments_count=r["comments_count"],
        )
        score = _eng(post)
        platform_scores.setdefault(r["platform"], []).append((r, score))

    anomalies: list[EngagementAnomaly] = []
    for platform, items in platform_scores.items():
        scores = [s for _, s in items]
        if len(scores) < 3:
            continue
        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores)
        if stdev == 0:
            continue
        for r, score in items:
            z = (score - mean) / stdev
            if z >= z_threshold:
                anomalies.append(EngagementAnomaly(
                    platform=platform,
                    post_id=r["post_id"],
                    title=(r["title"] or "")[:80],
                    url=r["url"],
                    author_name=r["author_name"] or r["author_id"],
                    published_at=r["published_at"] or "",
                    engagement_score=round(score, 3),
                    z_score=round(z, 2),
                ))

    anomalies.sort(key=lambda a: a.z_score, reverse=True)
    return anomalies


def _rising_authors(
    conn: sqlite3.Connection,
    granularity: str,
    since_str: str | None,
    top_n: int = 10,
) -> list[dict]:
    """Authors with the most posts in the most recent period."""
    period = _period_expr(granularity)
    where = "WHERE published_at > ?" if since_str else ""
    params = (since_str,) if since_str else ()

    latest_period = conn.execute(
        f"SELECT {period} AS p FROM posts {where} ORDER BY published_at DESC LIMIT 1",
        params,
    ).fetchone()

    if not latest_period or not latest_period["p"]:
        return []

    lp = latest_period["p"]
    rows = conn.execute(
        f"""
        SELECT p.author_id, a.author_name, a.platform, a.author_type,
               COUNT(*) AS post_count
        FROM posts p
        LEFT JOIN authors a ON p.platform = a.platform AND p.author_id = a.author_id
        WHERE {period} = ?
        GROUP BY p.author_id
        ORDER BY post_count DESC
        LIMIT ?
        """,
        (lp, top_n),
    ).fetchall()

    return [
        {
            "author_name": r["author_name"] or r["author_id"],
            "platform": r["platform"],
            "author_type": r["author_type"] or "community",
            "posts_in_period": r["post_count"],
            "period": lp,
        }
        for r in rows
    ]


def _sentiment_shift(buckets: list[PeriodBucket]) -> dict:
    """Compare sentiment distribution of earliest vs latest period."""
    if len(buckets) < 2:
        return {}

    def _pct(b: PeriodBucket) -> dict:
        total = b.sentiment_pos + b.sentiment_neg + b.sentiment_neu or 1
        return {
            "positive_pct": round(b.sentiment_pos / total * 100, 1),
            "negative_pct": round(b.sentiment_neg / total * 100, 1),
            "neutral_pct": round(b.sentiment_neu / total * 100, 1),
            "period": b.period,
        }

    return {"earliest": _pct(buckets[0]), "latest": _pct(buckets[-1])}
