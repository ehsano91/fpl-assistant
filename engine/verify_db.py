"""
verify_db.py
------------
Reads db/fpl.db and prints a human-readable summary:
  - Total number of players stored
  - Total number of fixtures stored
  - My current squad: player name, position label, and team

Run from the project root:
    python engine/verify_db.py
"""

import sqlite3
import os

# ---------------------------------------------------------------------------
# Configuration — must match the path used in fetch_fpl.py
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")

# Map the numeric element_type to a readable position label
POSITION_LABELS = {
    1: "GKP",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


def main():
    # Check the database file exists before trying to open it
    db_abs = os.path.abspath(DB_PATH)
    if not os.path.exists(db_abs):
        print(f"[ERROR] Database not found at: {db_abs}")
        print("        Run engine/fetch_fpl.py first.")
        return

    conn = sqlite3.connect(db_abs)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    cursor = conn.cursor()

    print("=" * 60)
    print("  FPL Assistant — Database Summary")
    print(f"  Database: {db_abs}")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. Total players
    # -----------------------------------------------------------------------
    cursor.execute("SELECT COUNT(*) AS cnt FROM players")
    total_players = cursor.fetchone()["cnt"]
    print(f"\n  Total players stored : {total_players}")

    # -----------------------------------------------------------------------
    # 2. Total fixtures
    # -----------------------------------------------------------------------
    cursor.execute("SELECT COUNT(*) AS cnt FROM fixtures")
    total_fixtures = cursor.fetchone()["cnt"]
    print(f"  Total fixtures stored: {total_fixtures}")

    # -----------------------------------------------------------------------
    # 3. Current gameweek
    # -----------------------------------------------------------------------
    cursor.execute("SELECT id, name FROM gameweeks WHERE is_current = 1")
    gw_row = cursor.fetchone()
    if gw_row:
        current_gw = gw_row["id"]
        print(f"  Current gameweek     : {gw_row['name']} (GW{current_gw})")
    else:
        # Fall back to the highest GW that has picks
        cursor.execute("SELECT MAX(gameweek) AS gw FROM my_picks")
        row = cursor.fetchone()
        current_gw = row["gw"] if row and row["gw"] else None
        print(f"  Current gameweek     : GW{current_gw} (detected from picks)")

    # -----------------------------------------------------------------------
    # 4. My squad for the current GW
    # -----------------------------------------------------------------------
    if current_gw is None:
        print("\n  [WARN] No picks found — run fetch_fpl.py first.")
        conn.close()
        return

    # Join picks → players → teams so we get names in one query
    cursor.execute("""
        SELECT
            p.web_name,
            p.first_name,
            p.second_name,
            p.element_type,
            t.short_name   AS team,
            mp.position    AS squad_position,
            mp.is_captain,
            mp.is_vice_captain,
            mp.multiplier
        FROM my_picks mp
        JOIN players p ON mp.player_id = p.id
        JOIN teams   t ON p.team_id    = t.id
        WHERE mp.gameweek = ?
        ORDER BY mp.position
    """, (current_gw,))

    picks = cursor.fetchall()

    if not picks:
        print(f"\n  [WARN] No picks saved for GW{current_gw}.")
        print("         Run fetch_fpl.py — the deadline may not have passed yet.")
        conn.close()
        return

    print(f"\n  My Squad — GW{current_gw} (Tiki Taka CF)")
    print("  " + "-" * 56)

    # Column header
    print(f"  {'#':<4} {'Pos':<5} {'Name':<22} {'Team':<6} {'Cap'}")
    print("  " + "-" * 56)

    for pick in picks:
        squad_pos  = pick["squad_position"]
        pos_label  = POSITION_LABELS.get(pick["element_type"], "?")
        name       = pick["web_name"]
        team       = pick["team"]

        # Build a flag string to show captain / vice-captain
        flags = []
        if pick["is_captain"]:
            flags.append("C")          # Captain (2x points)
        if pick["is_vice_captain"]:
            flags.append("V")          # Vice-captain
        if pick["multiplier"] == 3:
            flags.append("TC")         # Triple captain chip
        flag_str = " ".join(flags)

        # Draw a separator between the starting XI and the bench
        if squad_pos == 12:
            print("  " + "- " * 28 + "  (bench below)")

        print(f"  {squad_pos:<4} {pos_label:<5} {name:<22} {team:<6} {flag_str}")

    print("  " + "-" * 56)
    print(f"\n  Starting XI : players 1–11")
    print(f"  Bench       : players 12–15")

    conn.close()
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
