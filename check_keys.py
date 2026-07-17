"""
Run this script to verify your API keys before a full scrape.
Usage:  python check_keys.py
"""
from __future__ import annotations
import os
import sys
from dotenv import load_dotenv

load_dotenv()

OK = "\033[32m OK\033[0m"
FAIL = "\033[31m FAIL\033[0m"
SKIP = "\033[33m SKIP\033[0m"

_TEST_QUERY = "open source FPGA tutorial"


def check_youtube() -> bool:
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        print(f"YOUTUBE_API_KEY{SKIP}  (not set — YouTube scraping disabled)")
        return False
    try:
        from googleapiclient.discovery import build
        client = build("youtube", "v3", developerKey=key)
        resp = client.search().list(part="snippet", q=_TEST_QUERY, type="video", maxResults=1).execute()
        title = resp["items"][0]["snippet"]["title"] if resp.get("items") else "(no results)"
        print(f"YOUTUBE_API_KEY{OK}  — sample result: \"{title[:60]}\"")
        return True
    except Exception as e:
        print(f"YOUTUBE_API_KEY{FAIL}  — {e}")
        return False


def check_reddit() -> bool:
    cid = os.getenv("REDDIT_CLIENT_ID", "")
    csec = os.getenv("REDDIT_CLIENT_SECRET", "")
    agent = os.getenv("REDDIT_USER_AGENT", "influencer-radar/1.0")
    if not cid or not csec:
        print(f"REDDIT credentials{SKIP}  (not set — Reddit scraping disabled)")
        return False
    try:
        import praw
        reddit = praw.Reddit(client_id=cid, client_secret=csec, user_agent=agent)
        posts = list(reddit.subreddit("all").search(_TEST_QUERY, limit=1))
        title = posts[0].title if posts else "(no results)"
        print(f"REDDIT credentials{OK}  — sample result: \"{title[:60]}\"")
        return True
    except Exception as e:
        print(f"REDDIT credentials{FAIL}  — {e}")
        return False


def check_apify() -> bool:
    token = os.getenv("APIFY_API_TOKEN", "")
    if not token:
        print(f"APIFY_API_TOKEN{SKIP}  (not set — TikTok/Twitter/Instagram scraping disabled)")
        return False
    try:
        from apify_client import ApifyClient
        client = ApifyClient(token)
        me = client.user("me").get()
        username = me.get("username", "unknown") if me else "unknown"
        print(f"APIFY_API_TOKEN{OK}  — authenticated as '{username}'")
        return True
    except Exception as e:
        print(f"APIFY_API_TOKEN{FAIL}  — {e}")
        return False


def main() -> None:
    print("=" * 55)
    print("  Influencer Radar — API Key Check")
    print("=" * 55)

    results = {
        "youtube": check_youtube(),
        "reddit":  check_reddit(),
        "apify":   check_apify(),
    }

    print()
    print("=" * 55)
    if not any(results.values()):
        print("ERROR: No scraping APIs configured. Fill in at least")
        print("       one set of credentials in .env")
        sys.exit(1)
    else:
        print("Keys verified. Ready to run:")
        print("  python main.py --topic topics/my_topic.txt")
    print("=" * 55)


if __name__ == "__main__":
    main()
