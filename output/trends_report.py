from __future__ import annotations
from datetime import datetime
from pathlib import Path

from analyzer.trends import TrendsReport


def export_trends_markdown(report: TrendsReport, output_dir: Path, topic_slug: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y%m%d")
    out_path = output_dir / f"{topic_slug}_trends_{date_str}.md"

    sections = [
        f"# Trends Report\n",
        f"**Topic:** `{topic_slug}`  \n"
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  \n"
        f"**Granularity:** {report.granularity}  \n"
        f"**Since:** {report.since or 'all time'}\n",
        _render_volume_table(report),
        _render_sentiment_shift(report),
        _render_anomalies(report),
        _render_rising_authors(report),
    ]

    out_path.write_text("\n".join(sections), encoding="utf-8")
    return out_path


def _render_volume_table(report: TrendsReport) -> str:
    if not report.buckets:
        return "## Post Volume Over Time\n\n_No data._\n"

    lines = [
        "## Post Volume Over Time\n",
        f"| Period | Posts | Authors | New Authors | Avg Engagement | +Sentiment | -Sentiment |",
        f"|--------|-------|---------|-------------|----------------|------------|------------|",
    ]
    for b in report.buckets:
        lines.append(
            f"| {b.period} | {b.post_count} | {b.unique_authors} | {b.new_authors} "
            f"| {b.avg_engagement:.2f} | {b.sentiment_pos} | {b.sentiment_neg} |"
        )
    return "\n".join(lines) + "\n"


def _render_sentiment_shift(report: TrendsReport) -> str:
    s = report.sentiment_shift
    if not s:
        return ""

    e, l = s.get("earliest", {}), s.get("latest", {})
    pos_delta = l.get("positive_pct", 0) - e.get("positive_pct", 0)
    neg_delta = l.get("negative_pct", 0) - e.get("negative_pct", 0)
    pos_arrow = ("▲" if pos_delta > 0 else "▼") if abs(pos_delta) > 1 else "→"
    neg_arrow = ("▲" if neg_delta > 0 else "▼") if abs(neg_delta) > 1 else "→"

    return (
        "## Sentiment Shift\n\n"
        f"Comparing earliest period (`{e.get('period', '?')}`) to latest (`{l.get('period', '?')}`):\n\n"
        f"| Sentiment | Earliest | Latest | Trend |\n"
        f"|-----------|----------|--------|-------|\n"
        f"| Positive | {e.get('positive_pct', 0):.1f}% | {l.get('positive_pct', 0):.1f}% | {pos_arrow} {abs(pos_delta):.1f}pp |\n"
        f"| Negative | {e.get('negative_pct', 0):.1f}% | {l.get('negative_pct', 0):.1f}% | {neg_arrow} {abs(neg_delta):.1f}pp |\n"
        f"| Neutral  | {e.get('neutral_pct', 0):.1f}% | {l.get('neutral_pct', 0):.1f}% | — |\n"
    )


def _render_anomalies(report: TrendsReport) -> str:
    if not report.anomalies:
        return "## Engagement Anomalies\n\n_No anomalies detected (no posts significantly above platform mean)._\n"

    lines = [
        "## Engagement Anomalies\n",
        "_Posts with engagement significantly above the platform average (z-score ≥ threshold)._\n",
        "| Z-Score | Platform | Author | Title | Date | URL |",
        "|---------|----------|--------|-------|------|-----|",
    ]
    for a in report.anomalies[:20]:
        date = a.published_at[:10] if a.published_at else "?"
        title = a.title[:50] + ("…" if len(a.title) > 50 else "")
        lines.append(
            f"| {a.z_score:.1f}σ | {a.platform} | {a.author_name} "
            f"| {title} | {date} | [link]({a.url}) |"
        )
    return "\n".join(lines) + "\n"


def _render_rising_authors(report: TrendsReport) -> str:
    if not report.rising_authors:
        return ""

    period = report.rising_authors[0].get("period", "latest period")
    lines = [
        f"## Most Active Authors in `{period}`\n",
        "| Author | Platform | Type | Posts in Period |",
        "|--------|----------|------|-----------------|",
    ]
    for r in report.rising_authors:
        badge = " ⭐" if r["author_type"] == "official" else ""
        lines.append(
            f"| {r['author_name']}{badge} | {r['platform']} | {r['author_type']} | {r['posts_in_period']} |"
        )
    return "\n".join(lines) + "\n"
