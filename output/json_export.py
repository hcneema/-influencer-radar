from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from models import InfluencerProfile


def export_json(
    profiles: list[InfluencerProfile],
    output_dir: Path,
    topic_slug: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = output_dir / f"{topic_slug}_influencers_{date_str}.json"

    official = [p for p in profiles if p.author_type == "official"]
    community = [p for p in profiles if p.author_type == "community"]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic_slug,
        "total_influencers": len(profiles),
        "official_sources": [_profile_to_dict(p) for p in official],
        "community_influencers": [_profile_to_dict(p) for p in community],
    }
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _profile_to_dict(profile: InfluencerProfile) -> dict:
    return {
        "author_name": profile.author_name,
        "author_id": profile.author_id,
        "platform": profile.platform,
        "author_type": profile.author_type,
        "subscriber_count": profile.subscriber_count,
        "total_posts": profile.total_posts,
        "engagement_score": profile.engagement_score,
        "top_post_urls": profile.top_post_urls,
        "category_breakdown": profile.category_breakdown,
    }
