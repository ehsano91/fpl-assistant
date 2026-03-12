"""
qualitative.py  —  Qualitative Signal Scraper
-----------------------------------------------
Reads config/sources.json, fetches content from each enabled source,
extracts player mentions with surrounding context, and stores the
results in the qualitative_signals table in db/fpl.db.

Supported source types:
  rss          — standard RSS 2.0 feed (BBC, Guardian, etc.)
  youtube_rss  — YouTube Atom feed (same parsing logic as RSS)
  podcast_rss  — Podcast RSS feed (same parsing logic as RSS)
  web_scrape   — HTML page (BeautifulSoup text extraction)

If a source is unavailable (network error, bad URL, etc.) it is logged
and skipped — the rest of the pipeline continues unaffected.

Run from the project root:
    python3 engine/qualitative.py
"""

import sqlite3
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH      = os.path.join(os.path.dirname(__file__), "..", "db",     "fpl.db")
SOURCES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "sources.json")

# HTTP headers — some sites block requests without a browser User-Agent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# How many characters either side of a player mention to capture as context
CONTEXT_WINDOW = 200

# Seconds to wait between requests (be polite to servers)
REQUEST_DELAY = 1.5

# Maximum number of signals to store per source (keeps the DB trim)
MAX_SIGNALS_PER_SOURCE = 50


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_signals_table(conn):
    """Create the qualitative_signals table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qualitative_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   TEXT,          -- matches id in sources.json
            source_name TEXT,          -- human-readable source name
            player_id   INTEGER,       -- FK to players.id (NULL if no match)
            player_name TEXT,          -- the name as it appeared in the text
            context     TEXT,          -- surrounding text (±200 chars)
            signal_text TEXT,          -- the full article/video title + summary
            fetched_at  TEXT,          -- UTC timestamp
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)
    conn.commit()
    print("[DB]  qualitative_signals table ready.")


# ---------------------------------------------------------------------------
# Load player names from DB for mention detection
# ---------------------------------------------------------------------------

def load_player_lookup(conn):
    """
    Return a dict mapping every known player name variant → player_id.
    We index by: web_name (e.g. "Salah"), second_name, and full name.
    All keys are lowercased for case-insensitive matching.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, first_name, second_name, web_name FROM players
        WHERE status != 'u'   -- skip unavailable players
    """)

    lookup = {}   # {lowercase_name: player_id}
    for row in cur.fetchall():
        pid = row["id"]
        # Index by every useful variant of the name
        for name in [
            row["web_name"],
            row["second_name"],
            f"{row['first_name']} {row['second_name']}",
        ]:
            if name and len(name) > 2:   # skip very short names (noise)
                lookup[name.lower()] = (pid, name)
    return lookup


# ---------------------------------------------------------------------------
# Player mention extraction
# ---------------------------------------------------------------------------

def find_player_mentions(text, player_lookup):
    """
    Scan `text` for player name mentions.
    Returns a list of:
        { player_id, player_name, context }
    Each entry is a unique player (deduplicated within one piece of content).
    """
    if not text:
        return []

    found = {}   # player_id → entry (deduplicated)
    lower = text.lower()

    for name_lower, (pid, canonical_name) in player_lookup.items():
        # Find all character positions where this name appears
        start = 0
        while True:
            idx = lower.find(name_lower, start)
            if idx == -1:
                break

            # Make sure it's a word boundary (avoid "Mane" inside "management")
            before = lower[idx - 1] if idx > 0 else " "
            after  = lower[idx + len(name_lower)] if idx + len(name_lower) < len(lower) else " "
            if before.isalpha() or after.isalpha():
                start = idx + 1
                continue

            # Extract context window around the mention
            ctx_start = max(0, idx - CONTEXT_WINDOW)
            ctx_end   = min(len(text), idx + len(name_lower) + CONTEXT_WINDOW)
            context   = "…" + text[ctx_start:ctx_end].strip() + "…"

            if pid not in found:
                found[pid] = {
                    "player_id":   pid,
                    "player_name": canonical_name,
                    "context":     context,
                }
            start = idx + 1

    return list(found.values())


# ---------------------------------------------------------------------------
# Fetch helpers — one per source type
# ---------------------------------------------------------------------------

def fetch_rss(url):
    """
    Fetch an RSS 2.0 or Atom feed and extract (title, description) pairs.
    Works for standard RSS, YouTube Atom feeds, and podcast RSS.
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "xml")
    items = []

    # RSS 2.0: <item> elements
    for item in soup.find_all("item"):
        title = item.find("title")
        desc  = item.find("description") or item.find("summary")
        if title:
            items.append({
                "title": title.get_text(strip=True),
                "body":  desc.get_text(strip=True) if desc else "",
            })

    # Atom (YouTube): <entry> elements
    for entry in soup.find_all("entry"):
        title   = entry.find("title")
        summary = entry.find("media:description") or entry.find("summary") or entry.find("content")
        if title:
            items.append({
                "title": title.get_text(strip=True),
                "body":  summary.get_text(strip=True) if summary else "",
            })

    return items


def fetch_web(url):
    """
    Fetch a plain HTML page and extract readable text paragraphs.
    Returns a single item list (the full page as one text blob).
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")

    # Remove navigation, scripts, and styling noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Extract all paragraph text
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    full_text  = " ".join(paragraphs)

    # Also grab the page title as context
    page_title = soup.find("title")
    title_text = page_title.get_text(strip=True) if page_title else url

    return [{"title": title_text, "body": full_text}]


# ---------------------------------------------------------------------------
# Main scraping logic for one source
# ---------------------------------------------------------------------------

def process_source(source, player_lookup, conn, now):
    """
    Fetch one source, extract player mentions, and store signals in the DB.
    Returns the number of signals saved.
    """
    src_id   = source["id"]
    src_name = source["name"]
    src_type = source["type"]
    url      = source["url"]

    # Detect placeholder URLs that haven't been filled in yet
    if "REPLACE_WITH" in url:
        print(f"  [SKIP] {src_name}: URL not configured yet (see sources.json)")
        return 0

    print(f"  [FETCH] {src_name} ({src_type})")
    print(f"          {url}")

    try:
        # Choose the right fetcher
        if src_type in ("rss", "youtube_rss", "podcast_rss"):
            items = fetch_rss(url)
        elif src_type == "web_scrape":
            items = fetch_web(url)
        else:
            print(f"  [WARN]  Unknown source type '{src_type}' — skipping")
            return 0

        print(f"  [OK]    {len(items)} items fetched")

    except requests.exceptions.ConnectionError:
        print(f"  [FAIL]  Cannot reach {url} — no internet or site is down. Skipping.")
        return 0
    except requests.exceptions.Timeout:
        print(f"  [FAIL]  Request timed out for {src_name}. Skipping.")
        return 0
    except requests.exceptions.HTTPError as e:
        print(f"  [FAIL]  HTTP {e.response.status_code} from {src_name}. Skipping.")
        return 0
    except Exception as e:
        print(f"  [FAIL]  Unexpected error for {src_name}: {e}. Skipping.")
        return 0

    # Extract player mentions from each item
    signals_saved = 0
    cur = conn.cursor()

    for item in items[:MAX_SIGNALS_PER_SOURCE]:
        full_text   = f"{item['title']} {item['body']}"
        mentions    = find_player_mentions(full_text, player_lookup)

        for mention in mentions:
            cur.execute("""
                INSERT INTO qualitative_signals
                    (source_id, source_name, player_id, player_name,
                     context, signal_text, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                src_id,
                src_name,
                mention["player_id"],
                mention["player_name"],
                mention["context"],
                item["title"][:500],   # store the headline as a label
                now,
            ))
            signals_saved += 1

        if signals_saved >= MAX_SIGNALS_PER_SOURCE:
            break

    conn.commit()
    return signals_saved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FPL Assistant — Qualitative Signal Scraper")
    print("=" * 60)

    # Load sources config
    if not os.path.exists(SOURCES_PATH):
        print(f"[ERROR] config/sources.json not found at {SOURCES_PATH}")
        sys.exit(1)

    with open(SOURCES_PATH) as f:
        config = json.load(f)

    sources = [s for s in config["sources"] if s.get("enabled", False)]
    print(f"\n  {len(sources)} source(s) enabled out of {len(config['sources'])} total.")

    if not sources:
        print("\n  No sources enabled. Edit config/sources.json and set")
        print('  "enabled": true on the sources you want to use.\n')
        return

    # Open DB
    conn = get_conn()
    create_signals_table(conn)

    # Load player names for mention detection
    player_lookup = load_player_lookup(conn)
    print(f"  {len(player_lookup)} player name variants loaded for matching.\n")

    now = datetime.now(timezone.utc).isoformat()
    total_signals = 0

    for i, source in enumerate(sources):
        if i > 0:
            time.sleep(REQUEST_DELAY)   # be polite between requests

        signals = process_source(source, player_lookup, conn, now)
        total_signals += signals
        print(f"          → {signals} player mention(s) stored\n")

    conn.close()

    print("=" * 60)
    print(f"  Done. {total_signals} total signal(s) stored in qualitative_signals.")
    print("=" * 60)


if __name__ == "__main__":
    main()
