# Social Media Influencer Research Tool

A Python CLI that scrapes social media platforms for posts about any technical topic, identifies and ranks influencers, classifies content by type and sentiment, stores everything in a queryable database, and generates human-readable reports.

**Default topic:** AMD/Xilinx Vivado HLS and Vitis HLS (High Level Synthesis for FPGAs).  
**Change the topic:** edit `topics/hls_topic.txt` — no code changes needed.

---

## How It Works — Full Pipeline

```
topics/hls_topic.txt          config/platforms.yaml
        │                              │
        ▼                              ▼
 topic_expander.py            config_loader.py
 (reads topic file,           (loads platform
  generates search queries)    settings)
        │                              │
        └──────────┬───────────────────┘
                   ▼
          ┌─────────────────┐
          │    Scrapers      │
          │  youtube_scraper │──► YouTube Data API v3
          │  reddit_scraper  │──► Reddit API (PRAW)
          └────────┬────────┘
                   │  list[RawPost]
                   ▼
          ┌─────────────────┐
          │   Classifier     │
          │  categories.py   │  rule-based (fast, free)
          └────────┬────────┘
                   │  list[ClassifiedPost]
                   ▼
        ┌──────────────────────┐
        │       Storage         │
        │  db/hls_research.db   │  SQLite — 4 tables
        │  raw_cache/*.jsonl    │  append-only backup per run
        └──────────┬───────────┘
                   │
                   ▼
          ┌─────────────────┐
          │    Analyzer      │
          │  influencer.py   │  group → score → rank
          │  trends.py       │  volume, sentiment, anomalies
          └────────┬────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
   reports/*.json    reports/*.md
   reports/*_trends_*.md
```

---

## Project Structure

```
hls-research/
  main.py                     CLI entry point — run a full scrape
  query.py                    DB explorer — filter/view results without SQL
  check_keys.py               Verify API keys before first run
  models.py                   Shared dataclasses (RawPost, ClassifiedPost, InfluencerProfile)
  topic_expander.py           Reads topic file lines as search queries
  dateutil_helper.py          Parses --since date strings

  topics/
    hls_topic.txt             ← EDIT THIS to change research topic

  config/
    platforms.yaml            Platform settings, subreddits, thresholds
    official_accounts.yaml    Known official channel IDs (AMD, Xilinx, etc.)
    config_loader.py
    official_accounts_loader.py

  scrapers/
    base_scraper.py
    youtube_scraper.py        YouTube Data API v3 + optional transcript fetch
    reddit_scraper.py         PRAW

  classifier/
    categories.py             Rule-based: regex patterns for depth/type/sentiment

  analyzer/
    influencer.py             Group by author, compute engagement score, rank
    trends.py                 Volume buckets, anomaly detection, sentiment shift

  storage/
    db.py                     SQLite schema + CRUD
    jsonl_cache.py            Append-only raw post backup

  output/
    json_export.py            Structured JSON report
    markdown_report.py        Human-readable influencer cards
    trends_report.py          Trend tables in Markdown

  db/
    hls_research.db           SQLite database (created on first run)
  raw_cache/                  JSONL backup files, one per scrape run
  reports/                    Generated reports
```

---

## Prerequisites

- Python 3.10+
- API keys (see below)

```bash
pip install -r requirements.txt
cp .env.example .env
```

### Getting API Keys

**YouTube Data API v3** (free, 10,000 units/day):
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Credentials → Create API Key
4. Paste into `.env` as `YOUTUBE_API_KEY=...`

**Reddit API** (free):
1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Create app → choose **script** type
3. Note the client ID (under the app name) and client secret
4. Set `REDDIT_USER_AGENT` to something like `influencer-radar/1.0 by YourUsername`

Verify all keys before running:
```bash
python check_keys.py
```

Expected output:
```
=======================================================
  HLS Research Tool — API Key Check
=======================================================
YOUTUBE_API_KEY  OK  — sample result: "Vivado HLS Tutorial - #pragma Pipeline"
REDDIT credentials  OK  — sample result: "Why does my HLS synthesis fail on II=1?"

=======================================================
All keys verified. Ready to run:
  python main.py --topic topics/hls_topic.txt
=======================================================
```

---

## Changing the Research Topic

Two files control what gets searched and how it gets classified — both are in `topics/`:

| File | Purpose |
|---|---|
| `hls_topic.txt` | Lines used directly as search queries |
| `hls_technical_terms.yaml` | Regex patterns that detect "deep-technical" posts for this domain |

Edit both when switching topics. Lines starting with `#` are comments in both files.

**Example: HLS AMD (default)**
```
Vivado HLS and Vitis HLS — AMD/Xilinx high level synthesis tools for FPGA development.
People teaching, reviewing, demonstrating, or complaining about HLS tools.

Technical content:
- #pragma HLS directives (pipeline, unroll, array_partition, dataflow, interface)
- Synthesis reports, latency constraints, initiation interval (II) optimization
- ap_fixed, ap_int, hls_stream data types
- HLS IP cores, HLS testbenches, co-simulation
- Resource utilization: DSP, LUT, BRAM usage after HLS synthesis

Beginner tutorials and expert showcases of HLS-based IP cores.
Comparisons of HLS vs HDL (VHDL/Verilog) workflows.
```

**Example: Switching to RISC-V**

`topics/riscv_topic.txt`:
```
RISC-V open source processor architecture and ecosystem.
People building, teaching, or critiquing RISC-V cores and toolchains.
Technical content: RV32I/RV64GC ISA, VexRiscv, CVA6, PicoRV32, OpenOCD, SiFive.
```

`topics/riscv_technical_terms.yaml`:
```yaml
technical_patterns:
  - '\bRV32[A-Z]*\b'
  - '\bRV64[A-Z]*\b'
  - '\bVexRiscv\b'
  - '\bOpenOCD\b'
  - '\bmachine\s+mode\b'
  - '\bCSR\s+register'
  - '\bISA\s+extension'
```

Then run:
```bash
python main.py --topic topics/riscv_topic.txt --terms topics/riscv_technical_terms.yaml
```

The old HLS posts stay in the database under their previous run — the new scrape adds RISC-V posts alongside them.

---

## Running a Scrape

### Basic run (all time)
```bash
python main.py --topic topics/hls_topic.txt
```

### Limit to recent posts
```bash
python main.py --topic topics/hls_topic.txt --since 30d   # last 30 days
python main.py --topic topics/hls_topic.txt --since 1y    # last year
python main.py --topic topics/hls_topic.txt --since 2023-06-01  # from a date
```

`--since` accepts: `Nd` (days), `Nw` (weeks), `Nm` (months), `Ny` (years), or `YYYY-MM-DD`.

### With a custom terms file (for a different topic)
```bash
python main.py --topic topics/riscv_topic.txt --terms topics/riscv_technical_terms.yaml
```

### With YouTube transcripts (richer classification, slower)
```bash
python main.py --topic topics/hls_topic.txt --transcripts
```
Fetches auto-generated captions via `youtube-transcript-api` (no quota cost).
Useful when video titles are vague but transcripts contain dense technical content.

### Dry run — preview queries without calling any API
```bash
python main.py --topic topics/hls_topic.txt --dry-run
```

Expected output:
```
Date filter: (none — all time)
────────────────── Influencer Radar ──────────────────
Expanding topic file: topics/hls_topic.txt
Generated 12 search queries

Search queries:
  • vivado hls tutorial
  • vitis hls pragma pipeline
  • AMD high level synthesis FPGA
  • #pragma HLS array_partition
  • HLS synthesis report latency
  • xilinx hls ip core design
  • hls dataflow optimization
  • ap_fixed ap_int hls
  • FPGA high level synthesis beginners
  • vitis hls vs vivado hls
  • HLS initiation interval optimization
  • xilinx hls co-simulation

Dry run complete. No APIs were called.
```

### Re-run classifier on existing DB posts
```bash
python main.py --reclassify
```
Useful after adjusting `categories.py` patterns.

---

## Expected Output After a Full Run

Console:
```
Date filter: posts since 2026-06-16 00:00 UTC
────────────────── Influencer Radar ──────────────────
Expanding topic file: topics/hls_topic.txt
Generated 12 search queries

Scraping YouTube...  YouTube: 143 posts found
Scraping Reddit...   Reddit: 89 posts found
Scraped 232 posts total (198 new)
Classifying 198 posts...
Found 47 influencers

JSON report:    reports/hls_topic_influencers_20260716.json
Markdown report: reports/hls_topic_report_20260716.md
Trends report:  reports/hls_topic_trends_20260716.md
Database:       db/hls_research.db
────────────────────────── Done ──────────────────────────────────
```

### JSON report structure (`reports/hls_topic_influencers_*.json`)
```json
{
  "generated_at": "2026-07-16T18:45:00",
  "topic": "hls_topic",
  "total_influencers": 47,
  "official_sources": [
    {
      "author_name": "AMD Developer Central",
      "author_id": "UC_7eBnRyBqSWZTMSJAf6u3w",
      "platform": "youtube",
      "author_type": "official",
      "subscriber_count": 84200,
      "total_posts": 12,
      "engagement_score": 18.4,
      "top_post_urls": [
        "https://www.youtube.com/watch?v=...",
        "https://www.youtube.com/watch?v=...",
        "https://www.youtube.com/watch?v=..."
      ],
      "category_breakdown": {
        "technical_depth": {"deep-technical": 9, "general-technical": 3},
        "content_type": {"tutorial": 7, "announcement": 3, "showcase": 2},
        "sentiment": {"positive": 10, "neutral": 2}
      }
    }
  ],
  "community_influencers": [
    {
      "author_name": "FPGAdeveloper",
      "author_id": "UCxxxxxx",
      "platform": "youtube",
      "author_type": "community",
      "subscriber_count": 12400,
      "total_posts": 8,
      "engagement_score": 11.2,
      "top_post_urls": [
        "https://www.youtube.com/watch?v=..."
      ],
      "category_breakdown": {
        "technical_depth": {"deep-technical": 6, "general-technical": 2},
        "content_type": {"tutorial": 5, "showcase": 2, "opinion": 1},
        "sentiment": {"positive": 5, "neutral": 2, "negative": 1}
      }
    }
  ]
}
```

### Markdown report structure (`reports/hls_topic_report_*.md`)

```markdown
# HLS Influencer Research Report

**Topic:** `hls_topic`
**Generated:** 2026-07-16 18:45 UTC
**Official sources:** 3
**Community influencers:** 44

## Official Sources (AMD / Xilinx)

| Rank | Name                  | Platform | Subscribers | Posts | Engagement Score |
|------|-----------------------|----------|-------------|-------|-----------------|
| 1    | AMD Developer Central | youtube  | 84,200      | 12    | 18.40           |
| 2    | Xilinx (official)     | youtube  | 210,000     | 6     | 15.70           |

## Community Influencers

| Rank | Name            | Platform | Subscribers | Posts | Engagement Score |
|------|-----------------|----------|-------------|-------|-----------------|
| 1    | FPGAdeveloper   | youtube  | 12,400      | 8         | 11.20           |
| 2    | hls_hobbyist    | reddit   | 4,100       | 5         | 6.80            |
| 3    | EmbeddedWizard  | youtube  | 8,900       | 4         | 5.40            |

## Category Distribution (Community Influencers)

### Technical Depth
| Category          | Posts | %   |
|-------------------|-------|-----|
| deep-technical    | 89    | 54% |
| general-technical | 52    | 32% |
| non-technical     | 23    | 14% |

### Content Type
| Category     | Posts | %   |
|--------------|-------|-----|
| tutorial     | 74    | 45% |
| question     | 38    | 23% |
| showcase     | 25    | 15% |
| opinion      | 18    | 11% |
| announcement | 9     | 6%  |

### Sentiment
| Category | Posts | %   |
|----------|-------|-----|
| positive | 98    | 60% |
| neutral  | 43    | 26% |
| negative | 23    | 14% |

---

## Community Influencer Detail Cards

### #1 — FPGAdeveloper `[youtube]`

| Field               | Value           |
|---------------------|-----------------|
| Subscribers/Karma   | 12,400          |
| Posts           | 8               |
| Engagement Score    | 11.20           |
| Dominant Depth      | deep-technical  |
| Dominant Type       | tutorial        |
| Dominant Sentiment  | positive        |

**Top Posts:**
- https://www.youtube.com/watch?v=abc123
- https://www.youtube.com/watch?v=def456
- https://www.youtube.com/watch?v=ghi789
```

---

## Querying the Database

Use `query.py` to explore results interactively without writing SQL.

### Overall statistics
```bash
python query.py summary
```
```
                     Database Summary
+----------------------------------------------------------+
| Total posts               |                         232 |
| Classified posts          |                         198 |
| Unique authors            |                          94 |
| Official authors          |                           3 |
| Community authors         |                          91 |
| YouTube posts             |                         143 |
| Reddit posts              |                          89 |
| Scrape runs               |                           4 |
| Sentiment — positive      |                         118 |
| Sentiment — neutral       |                          57 |
| Sentiment — negative      |                          23 |
| Depth — deep-technical    |                         107 |
| Depth — general-technical |                          62 |
| Depth — non-technical     |                          29 |
| Date range                | 2023-01-04  to  2026-07-16 |
+----------------------------------------------------------+
```

### Ranked influencers
```bash
python query.py influencers --top 10
python query.py influencers --platform youtube --type community --top 5
python query.py influencers --category deep-technical --since 6m
```
```
                        Top 5 Influencers
+-------------------------------------------------------------------+
| # | Author            | Platform | Type      | Subs   | Posts | Views    |
|---+-------------------+----------+-----------+--------+-------+----------|
| 1 | AMD Developer     | youtube  | official  | 84,200 |    12 | 482,000  |
| 2 | FPGAdeveloper     | youtube  | community |  12,400 |    8 | 198,000  |
| 3 | EmbeddedWizard    | youtube  | community |   8,900 |    4 |  94,000  |
| 4 | hls_hobbyist      | reddit   | community |   4,100 |    5 |      —   |
| 5 | fpga_engineer_42  | reddit   | community |   2,800 |    3 |      —   |
+-------------------------------------------------------------------+
```

### Browse posts with filters
```bash
# All deep-technical posts with negative sentiment
python query.py posts --category deep-technical --sentiment negative

# Posts mentioning a specific keyword
python query.py posts --search "initiation interval"

# All posts from a specific author
python query.py posts --author "FPGAdeveloper"

# Recent Reddit posts only
python query.py posts --platform reddit --since 30d --limit 15
```
```
                         Posts (3 shown)
+----------------------------------------------------------------------------+
| Date       | Author         | Title                           | Depth      | Type     | Sent.    | Eng.  |
|------------+----------------+---------------------------------+------------+----------+----------+-------|
| 2026-06-10 | fpga_eng_42    | HLS pipeline II constraint ...  | deep-tech  | question | negative | 1,240 |
| 2026-05-22 | hls_veteran    | Vitis HLS broken after upd...   | deep-tech  | opinion  | negative | 890   |
| 2026-04-08 | EmbeddedWizard | Why does HLS generate slow ...  | deep-tech  | question | negative | 640   |
+----------------------------------------------------------------------------+
```

### Engagement anomalies (viral / breakout posts)
```bash
python query.py anomalies
python query.py anomalies --z 3.0 --since 1y
```
```
              Engagement Anomalies (z >= 2.0)
+----------------------------------------------------------------------+
| Z-Score | Platform | Author          | Title                  | Date       |
|---------+----------+-----------------+------------------------+------------|
| 4.2σ    | youtube  | AMD Developer   | Vitis HLS 2024 Launch  | 2024-03-15 |
| 3.8σ    | youtube  | FPGAdeveloper   | HLS vs Verilog: Final  | 2025-11-02 |
| 3.1σ    | reddit   | hls_hobbyist    | Got II=1 on a 500MHz...| 2026-01-18 |
| 2.4σ    | youtube  | EmbeddedWizard  | HLS Dataflow Deep Dive | 2025-08-30 |
+----------------------------------------------------------------------+
```

### Trends over time
```bash
python query.py trends --period month
python query.py trends --period week --since 6m
```
```
                   Post Volume by Month
+---------------------------------------------------------------+
| Period  | Posts | Authors | New Authors | Avg Eng | Pos | Neg |
|---------+-------+---------+-------------+---------+-----+-----|
| 2025-10 |    18 |      12 |           5 |    3.40 |  11 |   2 |
| 2025-11 |    24 |      15 |           3 |    4.10 |  14 |   4 |
| 2025-12 |    31 |      19 |           7 |    3.90 |  17 |   6 |
| 2026-01 |    28 |      16 |           2 |    4.50 |  16 |   5 |
| 2026-02 |    22 |      14 |           1 |    3.70 |  13 |   4 |
| 2026-03 |    19 |      11 |           0 |    3.20 |  12 |   3 |
+---------------------------------------------------------------+

Sentiment shift  2025-10 to 2026-03:
  Positive 61% to 63%   Negative 11% to 16%

Most active in 2026-03:
   5 posts — AMD Developer ⭐ [youtube]
   4 posts — FPGAdeveloper [youtube]
   3 posts — hls_hobbyist [reddit]
```

### Export filtered posts to JSON
```bash
# Export all official posts for LLM summarization
python query.py export --type official --out amd_official_posts.json

# Export community negative posts for analysis
python query.py export --category negative --out negative_posts.json

# Export one author's full history
python query.py export --author "FPGAdeveloper" --out fpga_dev_posts.json
```

Each exported record looks like:
```json
{
  "platform": "youtube",
  "post_id": "dQw4w9WgXcQ",
  "title": "Vivado HLS Tutorial: Pipeline Optimization",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "published_at": "2025-11-02T14:30:00",
  "author_name": "FPGAdeveloper",
  "author_type": "community",
  "subscriber_count": 12400,
  "views": 41200,
  "likes": 1840,
  "comments_count": 93,
  "subreddit": "",
  "technical_depth": "deep-technical",
  "content_type": "tutorial",
  "sentiment": "positive",
  "classification_method": "rule-based",
  "confidence": 0.74
}
```

---

## Web-Based Database Viewer (Datasette)

For a browser-based interface with table browsing, filtering, and a live SQL editor, use [Datasette](https://datasette.io/):

```bash
pip install datasette
python -m datasette db/hls_research.db --metadata datasette_metadata.json --open
```

This opens `http://localhost:8001` in your browser. Keep the terminal open while using it; press `Ctrl+C` to stop.

### Navigating the UI

| What you want | Where to go |
|---|---|
| Browse all posts | `localhost:8001/hls_research/posts` |
| Browse authors | `localhost:8001/hls_research/authors` |
| Browse classifications | `localhost:8001/hls_research/classifications` |
| Run pre-built queries | `localhost:8001/hls_research` → scroll to **Queries** |
| Write custom SQL | `localhost:8001/hls_research` → **Custom SQL query** (top right) |

### Pre-built queries (available in the UI under Queries)

| Query name | What it shows |
|---|---|
| Top Influencers by Engagement | Authors ranked by total views + likes |
| All Posts with Classifications | Every post with depth, type, sentiment |
| Deep Technical Posts | Only `deep-technical` posts, sorted by views |
| Sentiment by Platform | Count of positive/negative/neutral per platform |
| Official vs Community Authors | Author type breakdown |
| Scrape Run History | When each run happened, how many posts were found |

### Useful custom SQL queries to try in the browser

```sql
-- All posts with clickable YouTube links
SELECT title, url, author_name, views, likes, technical_depth, content_type
FROM posts JOIN classifications USING (platform, post_id)
           JOIN authors USING (platform, author_id)
ORDER BY views DESC;

-- Posts from the last 30 days
SELECT title, url, published_at, author_name, sentiment
FROM posts JOIN classifications USING (platform, post_id)
           JOIN authors USING (platform, author_id)
WHERE published_at > date('now', '-30 days')
ORDER BY published_at DESC;

-- Authors with the most posts
SELECT author_name, platform, author_type, subscriber_count, COUNT(*) AS post_count
FROM authors JOIN posts USING (platform, author_id)
GROUP BY platform, author_id
ORDER BY post_count DESC;
```

Results can be exported as CSV or JSON using the links at the bottom of any result page.

---

## Generating a Standalone Trends Report

```bash
# Trends across all DB history, grouped by week
python main.py --trends

# Trends for the last year, grouped by month
python main.py --trends --since 1y --trends-period month
```

Output file: `reports/hls_topic_trends_20260716.md`

The trends report includes:
- **Post Volume Over Time** — posts, unique authors, new authors, avg engagement per period
- **Sentiment Shift** — earliest vs latest period positive/negative percentages with direction arrows
- **Engagement Anomalies** — posts statistically far above the platform average
- **Most Active Authors** — per-period leaderboard of most prolific posters

---

## Classification Categories

Every post is classified on three dimensions:

| Dimension | Values |
|---|---|
| **Technical depth** | `deep-technical` · `general-technical` · `non-technical` |
| **Content type** | `tutorial` · `question` · `announcement` · `showcase` · `opinion` |
| **Sentiment** | `positive` · `negative` · `neutral` |

**How classification works:**

1. **Rule-based** (fast, free, always runs): regex pattern sets match `#pragma HLS`, `II=N`, `ap_fixed`, tutorial phrases, sentiment keywords, etc. Assigns a confidence score 0–1.
2. **With `--transcripts`**: YouTube auto-captions are appended to `post.body` before step 1, giving the rule-based classifier access to spoken technical content — not just the title and description.

---

## Adding Known Official Accounts

Edit `config/official_accounts.yaml` to tag known brand accounts:

```yaml
youtube:
  - id: UCZRmgCNaKkFWFxFJBpBQqYg
    name: AMD (official)
  - id: UC_7eBnRyBqSWZTMSJAf6u3w
    name: AMD Developer Central

reddit:
  - username: AMD
  - username: Xilinx
```

To find a YouTube channel ID: go to the channel page, view source, search for `channelId`. Or use a lookup tool like `commentpicker.com/youtube-channel-id.php`.

Posts from listed accounts are tagged `author_type=official` in the DB and appear in a separate section of every report.

---

## Database Schema (SQLite)

Direct SQL is always available for custom queries:

```bash
sqlite3 db/hls_research.db
```

```sql
-- Top 10 community influencers by total engagement
SELECT a.author_name, a.platform, COUNT(*) AS posts,
       SUM(p.views + p.likes) AS total_engagement
FROM posts p JOIN authors a USING (platform, author_id)
WHERE a.author_type = 'community'
GROUP BY a.platform, a.author_id
ORDER BY total_engagement DESC LIMIT 10;

-- Negative deep-technical posts in the last 6 months
SELECT p.title, p.url, p.published_at
FROM posts p
JOIN classifications c USING (platform, post_id)
WHERE c.technical_depth = 'deep-technical'
  AND c.sentiment = 'negative'
  AND p.published_at > date('now', '-6 months')
ORDER BY p.published_at DESC;

-- Monthly post volume trend
SELECT strftime('%Y-%m', published_at) AS month,
       COUNT(*) AS posts,
       COUNT(DISTINCT author_id) AS unique_authors
FROM posts
GROUP BY month ORDER BY month;

-- Sentiment breakdown by platform
SELECT platform, sentiment, COUNT(*) AS n
FROM posts JOIN classifications USING (platform, post_id)
GROUP BY platform, sentiment;
```

**Tables:**

| Table | Key columns |
|---|---|
| `runs` | `id`, `run_at`, `topic_file`, `queries` (JSON), `posts_scraped` |
| `authors` | `(platform, author_id)` PK, `author_name`, `subscriber_count`, `author_type` |
| `posts` | `(platform, post_id)` PK, `title`, `body`, `url`, `published_at`, `views`, `likes` |
| `classifications` | `(platform, post_id)` PK, `technical_depth`, `content_type`, `sentiment`, `confidence` |

---

## Configuration Reference

### `config/platforms.yaml`

```yaml
platforms:
  youtube:
    enabled: true
    search_order: relevance   # relevance | date | viewCount
    max_results: 50           # per keyword (YouTube API max is 50)
  reddit:
    enabled: true
    subreddits: [fpga, xilinx, ECE, hardware, embedded]
    sort: relevance
    time_filter: all          # overridden by --since at runtime
    max_results: 100

classifier:
  ambiguity_threshold: 0.4   # posts below this confidence are still kept as rule-based

influencer:
  min_posts_threshold: 2     # minimum posts to appear as influencer

topic_expander:
  num_queries: 12            # lines from topic file used as search queries
```

### `.env`

```
YOUTUBE_API_KEY=AIza...
REDDIT_CLIENT_ID=abc123
REDDIT_CLIENT_SECRET=xyz789
REDDIT_USER_AGENT=influencer-radar/1.0 by YourUsername
```

---

## Platforms — Status and Roadmap

| Platform | Status | Notes |
|---|---|---|
| YouTube | ✅ Supported | Free API, 10k units/day. Transcripts optional. |
| Reddit | ✅ Supported | Free API via PRAW. |
| X / Twitter | 🔜 Phase 2 | Requires paid API ($100+/mo for useful search volume) |
| LinkedIn | 🔜 Phase 2 | Restricted API |
| Instagram / Facebook | ⛔ Blocked | No viable public API; scraping violates ToS |

---

## Cost Summary

| Operation | Cost |
|---|---|
| YouTube scrape | Free (API quota: 10,000 units/day) |
| Reddit scrape | Free |
| YouTube transcripts | Free (not YouTube quota) |

All classification is rule-based and free. No LLM API required.
