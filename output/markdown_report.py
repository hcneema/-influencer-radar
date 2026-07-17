from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from models import InfluencerProfile


def export_markdown(
    profiles: list[InfluencerProfile],
    output_dir: Path,
    topic_slug: str,
    top_n: int = 30,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = output_dir / f"{topic_slug}_report_{date_str}.md"

    official = [p for p in profiles if p.author_type == "official"]
    community = [p for p in profiles if p.author_type == "community"]

    sections = [
        f"# Influencer Research Report\n",
        f"**Topic:** `{topic_slug}`  \n"
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  \n"
        f"**Official sources:** {len(official)}  \n"
        f"**Community influencers:** {len(community)}\n",
    ]

    if official:
        sections.append("## Official Sources\n")
        sections.append(_render_leaderboard_table(official, top_n))
        sections.append("---\n\n## Official Source Detail Cards\n")
        for i, p in enumerate(official[:top_n], start=1):
            sections.append(_render_profile_card(p, i, badge="OFFICIAL"))

    sections.append("## Community Influencers\n")
    sections.append(_render_leaderboard_table(community, top_n))
    sections.append(_render_category_distribution(community))
    sections.append("---\n\n## Community Influencer Detail Cards\n")
    for i, p in enumerate(community[:top_n], start=1):
        sections.append(_render_profile_card(p, i))

    out_path.write_text("\n".join(sections), encoding="utf-8")
    return out_path


def _render_leaderboard_table(profiles: list[InfluencerProfile], top_n: int) -> str:
    lines = [
        "## Top Influencers\n",
        "| Rank | Name | Platform | Subscribers | Posts | Engagement Score |",
        "|------|------|----------|-------------|-------|-----------------|",
    ]
    for i, p in enumerate(profiles[:top_n], start=1):
        subs = f"{p.subscriber_count:,}" if p.subscriber_count else "—"
        lines.append(
            f"| {i} | {p.author_name} | {p.platform} | {subs} | {p.total_posts} | {p.engagement_score:.2f} |"
        )
    return "\n".join(lines) + "\n"


def _render_category_distribution(profiles: list[InfluencerProfile]) -> str:
    depth_total: Counter = Counter()
    ctype_total: Counter = Counter()
    sent_total: Counter = Counter()

    for p in profiles:
        bd = p.category_breakdown
        depth_total.update(bd.get("technical_depth", {}))
        ctype_total.update(bd.get("content_type", {}))
        sent_total.update(bd.get("sentiment", {}))

    def _table(counter: Counter, title: str) -> str:
        total = sum(counter.values()) or 1
        rows = [f"| {label} | {count} | {count/total*100:.0f}% |"
                for label, count in counter.most_common()]
        return (
            f"### {title}\n\n"
            "| Category | Posts | % |\n"
            "|----------|-------|---|\n"
            + "\n".join(rows)
        )

    return (
        "## Category Distribution (All Influencers)\n\n"
        + _table(depth_total, "Technical Depth") + "\n\n"
        + _table(ctype_total, "Content Type") + "\n\n"
        + _table(sent_total, "Sentiment") + "\n"
    )


def _dominant(d: dict) -> str:
    """Return the key with the highest value, or '—' for empty/missing dicts."""
    if not d:
        return "—"
    return max(d, key=d.get)


def _render_profile_card(profile: InfluencerProfile, rank: int, badge: str = "") -> str:
    subs = f"{profile.subscriber_count:,}" if profile.subscriber_count else "—"
    bd = profile.category_breakdown

    dominant_depth = _dominant(bd.get("technical_depth", {}))
    dominant_type  = _dominant(bd.get("content_type", {}))
    dominant_sent  = _dominant(bd.get("sentiment", {}))

    links = "\n".join(f"- {url}" for url in profile.top_post_urls) or "— none —"

    badge_str = f" `[{badge}]`" if badge else ""
    return (
        f"### #{rank} — {profile.author_name} `[{profile.platform}]`{badge_str}\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| Subscribers/Karma | {subs} |\n"
        f"| Posts | {profile.total_posts} |\n"
        f"| Engagement Score | {profile.engagement_score:.2f} |\n"
        f"| Dominant Depth | {dominant_depth} |\n"
        f"| Dominant Type | {dominant_type} |\n"
        f"| Dominant Sentiment | {dominant_sent} |\n\n"
        f"**Top Posts:**\n{links}\n\n"
        f"**Category Breakdown:** `{bd}`\n\n---\n"
    )
