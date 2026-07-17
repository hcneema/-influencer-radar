from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Social Media Influencer Research Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python main.py --topic topics/hls_topic.txt
  python main.py --topic topics/hls_topic.txt --since 30d
  python main.py --topic topics/hls_topic.txt --since 2023-01-01
  python main.py --topic topics/hls_topic.txt --dry-run
  python main.py --reclassify
  python main.py --trends
  python main.py --trends --since 1y --trends-period month
""",
    )
    parser.add_argument(
        "--topic",
        type=Path,
        default=Path("topics/hls_topic.txt"),
        help="Path to topic file — one search query per line (default: topics/hls_topic.txt)",
    )
    parser.add_argument(
        "--terms",
        type=Path,
        default=Path("topics/hls_technical_terms.yaml"),
        help="YAML file of domain-specific technical patterns for the rule-based classifier (default: topics/hls_technical_terms.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/"),
        help="Output directory for reports (default: reports/)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config/"),
        help="Directory containing platforms.yaml (default: config/)",
    )
    parser.add_argument(
        "--platforms",
        type=Path,
        default=None,
        metavar="FILE",
        help="Override path to platforms YAML file (e.g. config/platforms_test.yaml)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("db/influencer_radar.db"),
        help="SQLite database path (default: db/influencer_radar.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print expanded queries and config, do not call any scraping APIs",
    )
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="Re-run classifier on all posts already in the DB (no scraping)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="DATE",
        help="Only scrape posts after this date. Formats: 3d, 2w, 6m, 1y, 2022-01-15 (default: all time)",
    )
    parser.add_argument(
        "--trends",
        action="store_true",
        help="Generate a trends report from the database (no scraping). Can combine with --since.",
    )
    parser.add_argument(
        "--trends-period",
        choices=["week", "month"],
        default="week",
        help="Granularity for trends grouping: week or month (default: week)",
    )
    parser.add_argument(
        "--transcripts",
        action="store_true",
        help="Fetch YouTube auto-captions and append to post body before classification (slower, richer signal)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress information",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    # parse --since before anything else so we can fail fast on bad input
    since_dt = None
    if args.since:
        from dateutil_helper import parse_since
        try:
            since_dt = parse_since(args.since)
            console.print(f"Date filter: posts since [bold]{since_dt.strftime('%Y-%m-%d %H:%M UTC')}[/bold]")
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    from config.config_loader import load_config
    platforms_file = args.platforms if args.platforms else (args.config_dir / "platforms.yaml")
    config = load_config(platforms_file)

    # inject environment variables
    config.youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
    config.reddit_client_id = os.getenv("REDDIT_CLIENT_ID", "")
    config.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    config.reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "influencer-radar/1.0")

    console.rule("[bold blue]Influencer Radar")

    # --- Trends-only shortcut (no scraping) ---
    if args.trends:
        from storage.db import init_db
        from analyzer.trends import run_trends
        from output.trends_report import export_trends_markdown

        conn = init_db(args.db)
        report = run_trends(conn, granularity=args.trends_period, since=since_dt)
        topic_slug = args.topic.stem
        out = export_trends_markdown(report, args.output, topic_slug)
        console.print(f"[cyan]Trends report:[/cyan] {out}")
        console.print(f"  Periods: {len(report.buckets)}  |  Anomalies: {len(report.anomalies)}  |  Rising authors: {len(report.rising_authors)}")
        console.rule("[bold green]Done")
        return

    # --- Topic expansion ---
    from topic_expander import expand_topic

    queries = expand_topic(args.topic, num_queries=config.topic_expander.num_queries)
    console.print(f"Using {len(queries)} queries from topic file: [bold]{args.topic}[/bold]")

    if args.verbose or args.dry_run:
        console.print("\n[bold]Search queries:[/bold]")
        for q in queries:
            console.print(f"  • {q}")

    if args.dry_run:
        console.print("\n[yellow]Dry run complete. No APIs were called.[/yellow]")
        return

    # --- Storage setup ---
    from storage.db import init_db, create_run, update_run, upsert_author, upsert_post, upsert_classification, get_all_classified_posts, get_posts_without_classification
    from storage.jsonl_cache import open_cache, append_post as cache_append
    from config.official_accounts_loader import load_official_accounts, get_author_type

    conn = init_db(args.db)
    official_accounts = load_official_accounts(args.config_dir / "official_accounts.yaml")
    run_at = datetime.utcnow()

    platforms_used = []
    if config.youtube.enabled and config.youtube_api_key:
        platforms_used.append("youtube")
    if config.reddit.enabled and config.reddit_client_id:
        platforms_used.append("reddit")

    run_id = create_run(conn, {
        "run_at": run_at.isoformat(),
        "topic_file": str(args.topic),
        "topic_hash": _file_hash(args.topic),
        "platforms": platforms_used,
        "queries": queries,
    })

    # --- Scraping ---
    from models import RawPost
    all_raw: list[RawPost] = []

    if not args.reclassify:
        cache_file = open_cache(run_at, Path("raw_cache"))

        if "youtube" in platforms_used:
            console.print("Scraping YouTube...")
            from scrapers.youtube_scraper import YouTubeScraper
            yt = YouTubeScraper(config, since=since_dt, fetch_transcripts=args.transcripts)
            yt_posts = yt.scrape_all_keywords(queries)
            all_raw.extend(yt_posts)
            console.print(f"YouTube: {len(yt_posts)} posts found")

        if "reddit" in platforms_used:
            console.print("Scraping Reddit...")
            from scrapers.reddit_scraper import RedditScraper
            rd = RedditScraper(config, since=since_dt)
            rd_posts = rd.scrape_all_keywords(queries)
            all_raw.extend(rd_posts)
            console.print(f"Reddit: {len(rd_posts)} posts found")

        new_count = 0
        for post in all_raw:
            atype = get_author_type(post.platform, post.author_id, official_accounts)
            upsert_author(conn, post, author_type=atype)
            is_new = upsert_post(conn, post, run_id)
            if is_new:
                cache_append(cache_file, post)
                new_count += 1
        conn.commit()
        cache_file.close()
        console.print(f"[green]Scraped {len(all_raw)} posts total ({new_count} new)[/green]")

    # --- Classification ---
    # reload technical patterns from --terms file so the correct vocabulary is used
    from classifier import categories as _cat_module
    _cat_module._DEEP_TECHNICAL = _cat_module.load_technical_patterns(args.terms)
    from classifier.categories import classify_post
    from models import ClassifiedPost

    posts_to_classify = get_posts_without_classification(conn)
    console.print(f"Classifying {len(posts_to_classify)} posts...")

    classified: list[ClassifiedPost] = []
    for post in posts_to_classify:
        cp = classify_post(post, config.classifier.ambiguity_threshold)
        classified.append(cp)

    for cp in classified:
        upsert_classification(conn, cp)
    conn.commit()

    # --- Analysis ---
    all_classified = get_all_classified_posts(conn)
    from analyzer.influencer import run_analysis
    profiles = run_analysis(all_classified, config.influencer.min_posts_threshold)
    console.print(f"[green]Found {len(profiles)} influencers[/green]")

    update_run(conn, run_id, posts_scraped=len(all_raw), influencers_found=len(profiles))

    # --- Output ---
    topic_slug = args.topic.stem
    from output.json_export import export_json
    from output.markdown_report import export_markdown

    if config.output.format in ("json", "both"):
        out = export_json(profiles, args.output, topic_slug)
        console.print(f"[cyan]JSON report:[/cyan] {out}")

    if config.output.format in ("markdown", "both"):
        out = export_markdown(profiles, args.output, topic_slug)
        console.print(f"[cyan]Markdown report:[/cyan] {out}")

    # always generate a trends report if there's enough history (>=2 periods)
    from analyzer.trends import run_trends
    from output.trends_report import export_trends_markdown
    trends = run_trends(conn, granularity="week", since=since_dt)
    if len(trends.buckets) >= 2:
        out = export_trends_markdown(trends, args.output, topic_slug)
        console.print(f"[cyan]Trends report:[/cyan] {out}")

    console.print(f"[cyan]Database:[/cyan] {args.db}")
    console.rule("[bold green]Done")


def _file_hash(path: Path) -> str:
    import hashlib
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()[:10]


if __name__ == "__main__":
    main()
