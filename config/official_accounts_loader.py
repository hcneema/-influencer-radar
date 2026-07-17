from __future__ import annotations
from pathlib import Path
import yaml


def load_official_accounts(path: Path = Path("config/official_accounts.yaml")) -> dict[str, set[str]]:
    """
    Returns {platform: set_of_author_ids_or_usernames}.
    YouTube uses channel IDs; Reddit uses lowercased usernames.
    Returns empty sets if file is missing (graceful degradation).
    """
    if not path.exists():
        return {"youtube": set(), "reddit": set()}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    yt_ids = {entry["id"] for entry in data.get("youtube", []) if "id" in entry}
    rd_names = {entry["username"].lower() for entry in data.get("reddit", []) if "username" in entry}

    return {"youtube": yt_ids, "reddit": rd_names}


def get_author_type(platform: str, author_id: str, official_accounts: dict[str, set[str]]) -> str:
    ids = official_accounts.get(platform, set())
    check = author_id.lower() if platform == "reddit" else author_id
    return "official" if check in ids else "community"
