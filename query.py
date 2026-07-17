"""
query.py — explore the influencer research database without writing SQL.

Examples:
  python query.py summary
  python query.py influencers
  python query.py influencers --platform youtube --type community --top 20
  python query.py posts --author "SomeChannel" --limit 10
  python query.py posts --category deep-technical --sentiment negative
  python query.py posts --search "pragma HLS pipeline"
  python query.py anomalies
  python query.py trends --period month --since 1y
  python query.py export --author "SomeChannel" --out my_export.json
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

load_dotenv()
console = Console()
DEFAULT_DB = Path("db/influencer_radar.db")


# ── helpers ──────────────────────────────────────────────────────────────────

def open_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        console.print("Run [bold]python main.py[/bold] first to populate it.")
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def since_clause(since_str: str | None) -> tuple[str, tuple]:
    """Return (WHERE fragment, params) for optional date filter on posts.published_at."""
    if since_str:
        from dateutil_helper import parse_since
        dt = parse_since(since_str)
        return "AND p.published_at > ?", (dt.isoformat(),)
    return "", ()


# ── sub-commands ─────────────────────────────────────────────────────────────

def cmd_summary(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """High-level database statistics."""
    stats = {
        "Total posts":        conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        "Classified posts":   conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0],
        "Unique authors":     conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0],
        "Official authors":   conn.execute("SELECT COUNT(*) FROM authors WHERE author_type='official'").fetchone()[0],
        "Community authors":  conn.execute("SELECT COUNT(*) FROM authors WHERE author_type='community'").fetchone()[0],
        "YouTube posts":      conn.execute("SELECT COUNT(*) FROM posts WHERE platform='youtube'").fetchone()[0],
        "Reddit posts":       conn.execute("SELECT COUNT(*) FROM posts WHERE platform='reddit'").fetchone()[0],
        "Scrape runs":        conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
    }

    sent = conn.execute(
        "SELECT sentiment, COUNT(*) n FROM classifications GROUP BY sentiment"
    ).fetchall()
    for r in sent:
        stats[f"Sentiment — {r['sentiment']}"] = r["n"]

    depth = conn.execute(
        "SELECT technical_depth, COUNT(*) n FROM classifications GROUP BY technical_depth"
    ).fetchall()
    for r in depth:
        stats[f"Depth — {r['technical_depth']}"] = r["n"]

    oldest = conn.execute("SELECT MIN(published_at) FROM posts").fetchone()[0]
    newest = conn.execute("SELECT MAX(published_at) FROM posts").fetchone()[0]
    stats["Date range"] = f"{(oldest or '?')[:10]}  to  {(newest or '?')[:10]}"

    t = Table(title="Database Summary", box=box.SIMPLE_HEAVY, show_header=False)
    t.add_column("Metric", style="bold cyan")
    t.add_column("Value", justify="right")
    for k, v in stats.items():
        t.add_row(k, str(v))
    console.print(t)


def cmd_influencers(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Ranked influencer list with optional filters."""
    import math

    where_parts = ["1=1"]
    params: list = []

    if args.platform:
        where_parts.append("a.platform = ?")
        params.append(args.platform)
    if args.type:
        where_parts.append("a.author_type = ?")
        params.append(args.type)
    if args.category:
        dim, val = _parse_category(args.category)
        if dim:
            where_parts.append(f"c.{dim} = ?")
            params.append(val)

    since_w, since_p = since_clause(args.since)
    where_parts.append(since_w.lstrip("AND ") or "1=1")
    params.extend(since_p)

    where = " AND ".join(where_parts)

    rows = conn.execute(
        f"""
        SELECT a.author_name, a.platform, a.author_type, a.subscriber_count,
               COUNT(DISTINCT p.post_id) AS post_count,
               SUM(p.views) AS total_views,
               SUM(p.likes) AS total_likes,
               SUM(p.comments_count) AS total_comments,
               MAX(c.technical_depth) AS top_depth,
               MAX(c.sentiment) AS top_sentiment
        FROM authors a
        JOIN posts p ON a.platform = p.platform AND a.author_id = p.author_id
        LEFT JOIN classifications c ON p.platform = c.platform AND p.post_id = c.post_id
        WHERE {where}
        GROUP BY a.platform, a.author_id
        HAVING post_count >= ?
        ORDER BY total_views + total_likes DESC
        LIMIT ?
        """,
        (*params, args.min_posts, args.top),
    ).fetchall()

    if not rows:
        console.print("[yellow]No influencers matched your filters.[/yellow]")
        return

    t = Table(
        title=f"Top {args.top} Influencers",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
    )
    t.add_column("#", justify="right", style="dim")
    t.add_column("Author", style="bold")
    t.add_column("Platform")
    t.add_column("Type")
    t.add_column("Subs/Karma", justify="right")
    t.add_column("Posts", justify="right")
    t.add_column("Total Views", justify="right")
    t.add_column("Total Likes", justify="right")

    for i, r in enumerate(rows, 1):
        subs = f"{r['subscriber_count']:,}" if r["subscriber_count"] else "—"
        type_style = "yellow" if r["author_type"] == "official" else "green"
        t.add_row(
            str(i),
            r["author_name"],
            r["platform"],
            f"[{type_style}]{r['author_type']}[/{type_style}]",
            subs,
            str(r["post_count"]),
            f"{r['total_views']:,}" if r["total_views"] else "—",
            f"{r['total_likes']:,}" if r["total_likes"] else "—",
        )
    console.print(t)


def cmd_posts(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """List individual posts with optional filters."""
    where_parts = ["1=1"]
    params: list = []

    if args.author:
        where_parts.append("(LOWER(a.author_name) LIKE ? OR LOWER(p.author_id) LIKE ?)")
        like = f"%{args.author.lower()}%"
        params.extend([like, like])
    if args.platform:
        where_parts.append("p.platform = ?")
        params.append(args.platform)
    if args.sentiment:
        where_parts.append("c.sentiment = ?")
        params.append(args.sentiment)
    if args.category:
        dim, val = _parse_category(args.category)
        if dim:
            where_parts.append(f"c.{dim} = ?")
            params.append(val)
    if args.search:
        where_parts.append("(LOWER(p.title) LIKE ? OR LOWER(p.body) LIKE ?)")
        like = f"%{args.search.lower()}%"
        params.extend([like, like])
    if args.type:
        where_parts.append("a.author_type = ?")
        params.append(args.type)

    since_w, since_p = since_clause(args.since)
    if since_w:
        where_parts.append(since_w.lstrip("AND "))
        params.extend(since_p)

    where = " AND ".join(where_parts)

    rows = conn.execute(
        f"""
        SELECT p.platform, p.title, p.url, p.published_at,
               a.author_name, a.author_type,
               p.views, p.likes, p.comments_count,
               c.technical_depth, c.content_type, c.sentiment, c.confidence
        FROM posts p
        LEFT JOIN authors a ON p.platform = a.platform AND p.author_id = a.author_id
        LEFT JOIN classifications c ON p.platform = c.platform AND p.post_id = c.post_id
        WHERE {where}
        ORDER BY (p.views + p.likes) DESC
        LIMIT ?
        """,
        (*params, args.limit),
    ).fetchall()

    if not rows:
        console.print("[yellow]No posts matched your filters.[/yellow]")
        return

    t = Table(
        title=f"Posts ({len(rows)} shown)",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )
    t.add_column("Date", style="dim", width=10)
    t.add_column("Author", width=18)
    t.add_column("Title", width=40)
    t.add_column("Depth")
    t.add_column("Type")
    t.add_column("Sent.")
    t.add_column("Eng.", justify="right")
    t.add_column("URL", width=30, no_wrap=True)

    for r in rows:
        date = (r["published_at"] or "")[:10]
        eng = (r["views"] or 0) + (r["likes"] or 0)
        title = (r["title"] or "")[:38]
        author = (r["author_name"] or r["platform"])[:16]
        sent_color = {"positive": "green", "negative": "red"}.get(r["sentiment"] or "", "white")
        t.add_row(
            date, author, title,
            r["technical_depth"] or "—",
            r["content_type"] or "—",
            f"[{sent_color}]{r['sentiment'] or '—'}[/{sent_color}]",
            f"{eng:,}",
            r["url"] or "",
        )
    console.print(t)


def cmd_anomalies(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Show engagement anomalies (posts far above platform average)."""
    from analyzer.trends import run_trends
    from dateutil_helper import parse_since

    since_dt = parse_since(args.since) if args.since else None
    report = run_trends(conn, since=since_dt, anomaly_z_threshold=args.z)

    if not report.anomalies:
        console.print("[yellow]No anomalies detected with current threshold.[/yellow]")
        return

    t = Table(title=f"Engagement Anomalies (z ≥ {args.z})", box=box.SIMPLE_HEAVY)
    t.add_column("Z-Score", justify="right", style="bold red")
    t.add_column("Platform")
    t.add_column("Author", width=18)
    t.add_column("Title", width=42)
    t.add_column("Date", width=10)
    t.add_column("URL", width=35)

    for a in report.anomalies[:args.top]:
        t.add_row(
            f"{a.z_score:.1f}σ",
            a.platform,
            a.author_name[:16],
            a.title[:40],
            a.published_at[:10] if a.published_at else "?",
            a.url,
        )
    console.print(t)


def cmd_trends(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Print post volume and sentiment trend table."""
    from analyzer.trends import run_trends
    from dateutil_helper import parse_since

    since_dt = parse_since(args.since) if args.since else None
    report = run_trends(conn, granularity=args.period, since=since_dt)

    if not report.buckets:
        console.print("[yellow]No data in DB yet — run a scrape first.[/yellow]")
        return

    t = Table(title=f"Post Volume by {args.period.title()}", box=box.SIMPLE_HEAVY)
    t.add_column("Period", style="bold")
    t.add_column("Posts", justify="right")
    t.add_column("Authors", justify="right")
    t.add_column("New Authors", justify="right")
    t.add_column("Avg Eng.", justify="right")
    t.add_column("😊 Pos", justify="right", style="green")
    t.add_column("😠 Neg", justify="right", style="red")
    t.add_column("😐 Neu", justify="right")

    for b in report.buckets:
        t.add_row(
            b.period,
            str(b.post_count),
            str(b.unique_authors),
            str(b.new_authors),
            f"{b.avg_engagement:.2f}",
            str(b.sentiment_pos),
            str(b.sentiment_neg),
            str(b.sentiment_neu),
        )
    console.print(t)

    if report.sentiment_shift:
        e = report.sentiment_shift["earliest"]
        l = report.sentiment_shift["latest"]
        console.print(
            f"\nSentiment shift  [dim]{e['period']}[/dim] to [bold]{l['period']}[/bold]:  "
            f"Positive [green]{e['positive_pct']}%[/green] to [green]{l['positive_pct']}%[/green]  "
            f"Negative [red]{e['negative_pct']}%[/red] to [red]{l['negative_pct']}%[/red]"
        )

    if report.rising_authors:
        period_label = report.rising_authors[0].get("period", "latest")
        console.print(f"\n[bold]Most active in {period_label}:[/bold]")
        for r in report.rising_authors[:5]:
            badge = " ⭐" if r["author_type"] == "official" else ""
            console.print(f"  {r['posts_in_period']:>3} posts — {r['author_name']}{badge} [{r['platform']}]")


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Export filtered posts to JSON."""
    where_parts = ["1=1"]
    params: list = []

    if args.author:
        where_parts.append("(LOWER(a.author_name) LIKE ? OR LOWER(p.author_id) LIKE ?)")
        like = f"%{args.author.lower()}%"
        params.extend([like, like])
    if args.platform:
        where_parts.append("p.platform = ?")
        params.append(args.platform)
    if args.category:
        dim, val = _parse_category(args.category)
        if dim:
            where_parts.append(f"c.{dim} = ?")
            params.append(val)

    since_w, since_p = since_clause(args.since)
    if since_w:
        where_parts.append(since_w.lstrip("AND "))
        params.extend(since_p)

    where = " AND ".join(where_parts)

    rows = conn.execute(
        f"""
        SELECT p.platform, p.post_id, p.title, p.url, p.published_at,
               a.author_name, a.author_type, a.subscriber_count,
               p.views, p.likes, p.comments_count, p.subreddit,
               c.technical_depth, c.content_type, c.sentiment,
               c.classification_method, c.confidence
        FROM posts p
        LEFT JOIN authors a ON p.platform = a.platform AND p.author_id = a.author_id
        LEFT JOIN classifications c ON p.platform = c.platform AND p.post_id = c.post_id
        WHERE {where}
        ORDER BY p.published_at DESC
        """,
        params,
    ).fetchall()

    data = [dict(r) for r in rows]
    out_path = Path(args.out)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Exported {len(data)} posts →[/green] {out_path}")


# ── category filter helper ────────────────────────────────────────────────────

def _parse_category(value: str) -> tuple[str, str]:
    """
    Parse --category argument into (db_column, value).
    Accepted values:
      deep-technical, general-technical, non-technical
      tutorial, question, announcement, showcase, opinion
      positive, negative, neutral
    """
    depth_vals = {"deep-technical", "general-technical", "non-technical"}
    type_vals = {"tutorial", "question", "announcement", "showcase", "opinion"}
    sent_vals = {"positive", "negative", "neutral"}

    v = value.lower()
    if v in depth_vals:
        return "technical_depth", v
    if v in type_vals:
        return "content_type", v
    if v in sent_vals:
        return "sentiment", v

    console.print(f"[yellow]Unknown category '[bold]{value}[/bold]'. "
                  f"Use one of: {', '.join(sorted(depth_vals | type_vals | sent_vals))}[/yellow]")
    return "", ""


# ── CLI wiring ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query.py",
        description="Explore the influencer research database",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)

    sub = parser.add_subparsers(dest="command", required=True)

    # summary
    sub.add_parser("summary", help="Overall database statistics")

    # influencers
    p_inf = sub.add_parser("influencers", help="Ranked influencer list")
    p_inf.add_argument("--platform", choices=["youtube", "reddit"])
    p_inf.add_argument("--type", choices=["official", "community"])
    p_inf.add_argument("--category", metavar="CATEGORY",
                       help="Filter by category value (e.g. deep-technical, tutorial, negative)")
    p_inf.add_argument("--since", metavar="DATE",
                       help="Only count posts since this date (3d, 2w, 6m, 1y, 2022-01-15)")
    p_inf.add_argument("--top", type=int, default=20)
    p_inf.add_argument("--min-posts", type=int, default=2, dest="min_posts")

    # posts
    p_posts = sub.add_parser("posts", help="Browse individual posts")
    p_posts.add_argument("--author", metavar="NAME")
    p_posts.add_argument("--platform", choices=["youtube", "reddit"])
    p_posts.add_argument("--type", choices=["official", "community"])
    p_posts.add_argument("--sentiment", choices=["positive", "negative", "neutral"])
    p_posts.add_argument("--category", metavar="CATEGORY")
    p_posts.add_argument("--search", metavar="KEYWORD",
                         help="Full-text search in post title and body")
    p_posts.add_argument("--since", metavar="DATE")
    p_posts.add_argument("--limit", type=int, default=25)

    # anomalies
    p_an = sub.add_parser("anomalies", help="Posts with unusually high engagement")
    p_an.add_argument("--since", metavar="DATE")
    p_an.add_argument("--z", type=float, default=2.0, metavar="ZSCORE",
                      help="Z-score threshold (default: 2.0)")
    p_an.add_argument("--top", type=int, default=20)

    # trends
    p_tr = sub.add_parser("trends", help="Post volume and sentiment over time")
    p_tr.add_argument("--period", choices=["week", "month"], default="week")
    p_tr.add_argument("--since", metavar="DATE")

    # export
    p_ex = sub.add_parser("export", help="Export filtered posts to JSON")
    p_ex.add_argument("--author", metavar="NAME")
    p_ex.add_argument("--platform", choices=["youtube", "reddit"])
    p_ex.add_argument("--category", metavar="CATEGORY")
    p_ex.add_argument("--since", metavar="DATE")
    p_ex.add_argument("--out", default="export.json", metavar="FILE")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    conn = open_db(args.db)

    dispatch = {
        "summary":     cmd_summary,
        "influencers": cmd_influencers,
        "posts":       cmd_posts,
        "anomalies":   cmd_anomalies,
        "trends":      cmd_trends,
        "export":      cmd_export,
    }
    dispatch[args.command](conn, args)


if __name__ == "__main__":
    main()
