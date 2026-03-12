"""
fetch_fpl.py
------------
Fetches data from the official Fantasy Premier League API and saves it to a
local SQLite database at db/fpl.db.

Data fetched:
  - Bootstrap static  → players, teams, gameweeks
  - Fixtures          → all matches for the season
  - My squad picks    → entry 140222's picks for the current gameweek

Run from the project root:
    python engine/fetch_fpl.py
"""

import sqlite3
import requests
import os
import json

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENTRY_ID   = 140222                          # Tiki Taka CF
DB_PATH    = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")

# FPL API base URL
API_BASE   = "https://fantasy.premierleague.com/api"

# HTTP headers — the FPL API requires a User-Agent, otherwise it returns 403
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Helper: open (or create) the database and return the connection
# ---------------------------------------------------------------------------

def get_connection():
    """Create the db/ directory if needed and return a sqlite3 connection."""
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Return dictionaries instead of plain tuples when fetching rows
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Helper: create all tables (runs every time; IF NOT EXISTS is safe to repeat)
# ---------------------------------------------------------------------------

def create_tables(conn):
    """Define the schema for every table we need."""
    cursor = conn.cursor()

    # --- Teams ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id         INTEGER PRIMARY KEY,
            name       TEXT,
            short_name TEXT
        )
    """)

    # --- Players (called 'elements' in the FPL API) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id                  INTEGER PRIMARY KEY,
            first_name          TEXT,
            second_name         TEXT,
            web_name            TEXT,          -- display name (e.g. "Salah")
            element_type        INTEGER,       -- 1=GKP 2=DEF 3=MID 4=FWD
            team_id             INTEGER,
            now_cost            INTEGER,       -- price in tenths of £ (e.g. 130 = £13.0m)
            total_points        INTEGER,
            status              TEXT,          -- 'a'=available, 'i'=injured, etc.
            goals_scored        INTEGER,
            assists             INTEGER,
            clean_sheets        INTEGER,
            yellow_cards        INTEGER,
            red_cards           INTEGER,
            bonus               INTEGER,
            bps                 INTEGER,
            minutes             INTEGER,
            ict_index           TEXT,
            selected_by_percent TEXT,
            form                TEXT,
            points_per_game     TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    # Migration: add new stat columns to existing databases
    new_cols = [
        ("goals_scored",        "INTEGER"),
        ("assists",             "INTEGER"),
        ("clean_sheets",        "INTEGER"),
        ("yellow_cards",        "INTEGER"),
        ("red_cards",           "INTEGER"),
        ("bonus",               "INTEGER"),
        ("bps",                 "INTEGER"),
        ("minutes",             "INTEGER"),
        ("ict_index",           "TEXT"),
        ("selected_by_percent", "TEXT"),
        ("form",                "TEXT"),
        ("points_per_game",     "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            cursor.execute(f"ALTER TABLE players ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass  # column already exists

    # --- Gameweeks (called 'events' in the FPL API) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gameweeks (
            id              INTEGER PRIMARY KEY,
            name            TEXT,
            deadline_time   TEXT,
            finished        INTEGER,       -- 1 if GW is over, 0 if upcoming
            is_current      INTEGER,       -- 1 for the live/active GW
            is_next         INTEGER        -- 1 for the upcoming GW
        )
    """)

    # --- Fixtures ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            id                  INTEGER PRIMARY KEY,
            gameweek            INTEGER,
            team_h              INTEGER,   -- home team id
            team_a              INTEGER,   -- away team id
            team_h_score        INTEGER,
            team_a_score        INTEGER,
            kickoff_time        TEXT,
            finished            INTEGER,
            team_h_difficulty   INTEGER,   -- official FPL FDR (1-5) for home team
            team_a_difficulty   INTEGER,   -- official FPL FDR (1-5) for away team
            FOREIGN KEY (team_h) REFERENCES teams(id),
            FOREIGN KEY (team_a) REFERENCES teams(id)
        )
    """)

    # Migration: add difficulty columns to existing fixtures tables
    for col in ["team_h_difficulty", "team_a_difficulty"]:
        try:
            cursor.execute(f"ALTER TABLE fixtures ADD COLUMN {col} INTEGER")
            conn.commit()
        except Exception:
            pass  # column already exists

    # --- My squad picks for the current gameweek ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS my_picks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id        INTEGER,       -- FPL entry ID (e.g. 140222) — never NULL
            gameweek        INTEGER,
            player_id       INTEGER,
            position        INTEGER,       -- 1–11 = starting XI; 12–15 = bench
            multiplier      INTEGER,       -- 2 if captained, 3 if triple captain
            is_captain      INTEGER,       -- 1 or 0
            is_vice_captain INTEGER,       -- 1 or 0
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    # ---- Migration: add entry_id to existing databases that pre-date this column ----
    # ALTER TABLE fails silently if the column already exists — safe to run every time.
    try:
        cursor.execute("ALTER TABLE my_picks ADD COLUMN entry_id INTEGER")
        conn.commit()
        print("[DB] Migration: added entry_id column to my_picks.")
    except Exception:
        pass  # column already exists — nothing to do

    conn.commit()
    print("[DB] Tables created (or already exist).")


# ---------------------------------------------------------------------------
# Step 1: Fetch bootstrap-static (players, teams, gameweeks)
# ---------------------------------------------------------------------------

def fetch_bootstrap(conn):
    """
    The bootstrap-static endpoint is the motherlode of FPL data.
    It contains every player, team, and gameweek in one big JSON blob.
    """
    url = f"{API_BASE}/bootstrap-static/"
    print(f"\n[FETCH] Downloading bootstrap data from:\n        {url}")

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()          # blow up loudly if the request failed
    data = response.json()

    cursor = conn.cursor()

    # --- Save teams ---
    teams = data["teams"]
    print(f"[DB]    Saving {len(teams)} teams...")
    for t in teams:
        cursor.execute("""
            INSERT OR REPLACE INTO teams (id, name, short_name)
            VALUES (?, ?, ?)
        """, (t["id"], t["name"], t["short_name"]))

    # --- Save players ---
    players = data["elements"]
    print(f"[DB]    Saving {len(players)} players...")
    for p in players:
        cursor.execute("""
            INSERT OR REPLACE INTO players
                (id, first_name, second_name, web_name,
                 element_type, team_id, now_cost, total_points, status,
                 goals_scored, assists, clean_sheets, yellow_cards, red_cards,
                 bonus, bps, minutes, ict_index, selected_by_percent,
                 form, points_per_game)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["id"], p["first_name"], p["second_name"], p["web_name"],
            p["element_type"], p["team"], p["now_cost"],
            p["total_points"], p["status"],
            p.get("goals_scored", 0), p.get("assists", 0),
            p.get("clean_sheets", 0), p.get("yellow_cards", 0),
            p.get("red_cards", 0), p.get("bonus", 0), p.get("bps", 0),
            p.get("minutes", 0), p.get("ict_index", "0"),
            p.get("selected_by_percent", "0"), p.get("form", "0"),
            p.get("points_per_game", "0"),
        ))

    # --- Save gameweeks ---
    gameweeks = data["events"]
    print(f"[DB]    Saving {len(gameweeks)} gameweeks...")
    for gw in gameweeks:
        cursor.execute("""
            INSERT OR REPLACE INTO gameweeks
                (id, name, deadline_time, finished, is_current, is_next)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            gw["id"], gw["name"], gw["deadline_time"],
            int(gw["finished"]),
            int(gw["is_current"]),
            int(gw["is_next"])
        ))

    conn.commit()
    print("[DB]    Bootstrap data saved.")

    # Return the current gameweek id so the picks fetch can use it
    current_gw = next(
        (gw["id"] for gw in gameweeks if gw["is_current"]),
        None
    )
    if current_gw is None:
        # If no GW is marked current (e.g. between seasons), fall back to next
        current_gw = next(
            (gw["id"] for gw in gameweeks if gw["is_next"]),
            1
        )
    print(f"[GW]    Current gameweek detected: GW{current_gw}")
    return current_gw


# ---------------------------------------------------------------------------
# Step 2: Fetch all fixtures
# ---------------------------------------------------------------------------

def fetch_fixtures(conn):
    """Download every fixture for the season and store it."""
    url = f"{API_BASE}/fixtures/"
    print(f"\n[FETCH] Downloading fixtures from:\n        {url}")

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    fixtures = response.json()

    cursor = conn.cursor()
    print(f"[DB]    Saving {len(fixtures)} fixtures...")

    for f in fixtures:
        cursor.execute("""
            INSERT OR REPLACE INTO fixtures
                (id, gameweek, team_h, team_a,
                 team_h_score, team_a_score, kickoff_time, finished,
                 team_h_difficulty, team_a_difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["id"],
            f.get("event"),          # 'event' is the GW number (can be None)
            f["team_h"],
            f["team_a"],
            f.get("team_h_score"),   # None until the match is played
            f.get("team_a_score"),
            f.get("kickoff_time"),
            int(f.get("finished", False)),
            f.get("team_h_difficulty"),
            f.get("team_a_difficulty"),
        ))

    conn.commit()
    print("[DB]    Fixtures saved.")


# ---------------------------------------------------------------------------
# Step 3: Fetch my squad picks for the current gameweek
# ---------------------------------------------------------------------------

def fetch_my_picks(conn, current_gw):
    """
    Download Tiki Taka CF's 15-player squad for the current GW.
    The 'picks' endpoint requires a gameweek number.
    """
    url = f"{API_BASE}/entry/{ENTRY_ID}/event/{current_gw}/picks/"
    print(f"\n[FETCH] Downloading my GW{current_gw} picks from:\n        {url}")

    response = requests.get(url, headers=HEADERS, timeout=30)

    # A 404 here usually means the GW hasn't started yet (no picks submitted)
    if response.status_code == 404:
        print(f"[WARN]  No picks found for GW{current_gw} "
              f"(deadline may not have passed yet).")
        return

    response.raise_for_status()
    data = response.json()
    picks = data.get("picks", [])

    if not picks:
        print("[WARN]  The picks list is empty.")
        return

    cursor = conn.cursor()

    # Remove old picks for this GW + this entry so we always have a fresh set.
    # Filtering by entry_id ensures we never accidentally delete another user's picks
    # if this tool were ever extended to support multiple FPL accounts.
    cursor.execute(
        "DELETE FROM my_picks WHERE gameweek = ? AND (entry_id = ? OR entry_id IS NULL)",
        (current_gw, ENTRY_ID),
    )

    print(f"[DB]    Saving {len(picks)} picks for GW{current_gw} (entry {ENTRY_ID})...")
    for pick in picks:
        cursor.execute("""
            INSERT INTO my_picks
                (entry_id, gameweek, player_id, position,
                 multiplier, is_captain, is_vice_captain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ENTRY_ID,
            current_gw,
            pick["element"],
            pick["position"],
            pick["multiplier"],
            int(pick["is_captain"]),
            int(pick["is_vice_captain"])
        ))

    conn.commit()
    print("[DB]    My picks saved.")


# ---------------------------------------------------------------------------
# Step 4: Store picks for all completed historical GWs (idempotent)
# ---------------------------------------------------------------------------

def store_historical_picks(conn, cursor):
    """
    For every finished gameweek, check if picks are already stored.
    If not, fetch from the FPL API and insert them.
    Skips any GW that already has rows in my_picks (idempotent).
    """
    cursor.execute("SELECT id FROM gameweeks WHERE finished=1 ORDER BY id")
    finished_gws = [row["id"] for row in cursor.fetchall()]

    if not finished_gws:
        print("[HIST]  No finished gameweeks found — nothing to backfill.")
        return

    stored = 0
    skipped = 0
    for gw in finished_gws:
        cursor.execute(
            "SELECT COUNT(*) AS n FROM my_picks WHERE gameweek=? AND (entry_id=? OR entry_id IS NULL)",
            (gw, ENTRY_ID),
        )
        if cursor.fetchone()["n"] > 0:
            skipped += 1
            continue

        url = f"{API_BASE}/entry/{ENTRY_ID}/event/{gw}/picks/"
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 404:
            print(f"[HIST]  GW{gw}: no picks available (404) — skipping.")
            continue
        response.raise_for_status()
        picks = response.json().get("picks", [])

        if not picks:
            print(f"[HIST]  GW{gw}: empty picks list — skipping.")
            continue

        for pick in picks:
            cursor.execute("""
                INSERT INTO my_picks
                    (entry_id, gameweek, player_id, position,
                     multiplier, is_captain, is_vice_captain)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ENTRY_ID,
                gw,
                pick["element"],
                pick["position"],
                pick["multiplier"],
                int(pick["is_captain"]),
                int(pick["is_vice_captain"]),
            ))
        conn.commit()
        stored += 1
        print(f"[HIST]  GW{gw}: stored {len(picks)} picks.")

    print(f"[HIST]  Backfill complete — {stored} GWs stored, {skipped} already present.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FPL Assistant — Data Fetcher")
    print(f"  Entry: {ENTRY_ID} (Tiki Taka CF)")
    print(f"  Database: {os.path.abspath(DB_PATH)}")
    print("=" * 60)

    # 1. Open (or create) the database and set up tables
    conn = get_connection()
    cursor = conn.cursor()
    create_tables(conn)

    # 2. Pull bootstrap data and discover the current GW
    current_gw = fetch_bootstrap(conn)

    # 3. Pull all fixtures
    fetch_fixtures(conn)

    # 4. Pull my squad picks for the current GW
    fetch_my_picks(conn, current_gw)

    # 5. Backfill picks for all completed historical GWs
    store_historical_picks(conn, cursor)

    conn.close()

    print("\n" + "=" * 60)
    print("  All done! Run engine/verify_db.py to inspect the data.")
    print("=" * 60)


if __name__ == "__main__":
    main()
