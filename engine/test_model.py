"""
test_model.py  —  Model Validation Tests
-----------------------------------------
Runs a small suite of sanity checks against the data in db/fpl.db.

Tests:
  1. All xP scores are in the valid range [0, 20]
  2. All 15 current squad players have an xP score for the next GW
  3. Blank-GW players always have xP = 0.0
  4. The explainer returns non-empty text for every squad player
  5. Players with status 'i' (injured) have a very low xP (< 1.5)

Run from the project root:
    python engine/test_model.py
"""

import sqlite3
import os
import sys

# ---------------------------------------------------------------------------
# Import the explainer module (it lives in the same engine/ folder)
# ---------------------------------------------------------------------------

# Add the engine/ directory to the Python path so we can import explainer
sys.path.insert(0, os.path.dirname(__file__))
from explainer import explain_player

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")

# Maximum sensible xP score — even Haaland in a DGW shouldn't exceed 20
XP_MAX = 20.0
XP_MIN = 0.0

# Injured players should score almost nothing (only residual from formula)
XP_INJURED_CAP = 1.5


# ---------------------------------------------------------------------------
# Helper: print PASS or FAIL
# ---------------------------------------------------------------------------

def check(label: str, passed: bool, detail: str = "") -> bool:
    """
    Print a single test result line and return the boolean outcome.

    Example output:
        [PASS] All xP scores in range [0, 20]  —  min=0.00, max=11.43
        [FAIL] All 15 squad players scored      —  only 14/15 found
    """
    status = "PASS" if passed else "FAIL"
    detail_str = f"  —  {detail}" if detail else ""
    print(f"  [{status}] {label}{detail_str}")
    return passed


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def get_conn():
    db_abs = os.path.abspath(DB_PATH)
    if not os.path.exists(db_abs):
        print(f"\n[ERROR] Database not found: {db_abs}")
        print("  Run engine/fetch_fpl.py then engine/model.py first.")
        sys.exit(1)
    conn = sqlite3.connect(db_abs)
    conn.row_factory = sqlite3.Row
    return conn


def get_next_gw(conn) -> int:
    """Return the ID of the next unfinished gameweek."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM gameweeks
        WHERE finished = 0
        ORDER BY id
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        print("[ERROR] No upcoming GWs found. Run fetch_fpl.py to refresh.")
        sys.exit(1)
    return row["id"]


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_xp_range(conn, next_gw) -> bool:
    """
    TEST 1: Every xP score stored in the table must be between 0 and 20.
    Values outside this range indicate a bug in the model formula.
    """
    cur = conn.cursor()

    # Count rows that violate the range
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM xp_scores
        WHERE xp_score < ? OR xp_score > ?
    """, (XP_MIN, XP_MAX))
    bad_count = cur.fetchone()["cnt"]

    # Also grab the actual min/max for the next GW to show in the output
    cur.execute("""
        SELECT MIN(xp_score) AS lo, MAX(xp_score) AS hi
        FROM xp_scores
        WHERE gameweek = ?
    """, (next_gw,))
    stats = cur.fetchone()

    return check(
        f"All xP scores are in range [{XP_MIN}, {XP_MAX}]",
        bad_count == 0,
        f"GW{next_gw} min={stats['lo']:.2f}, max={stats['hi']:.2f} "
        f"({'0 violations' if bad_count == 0 else str(bad_count) + ' violations'})"
    )


def test_squad_all_scored(conn, next_gw) -> bool:
    """
    TEST 2: All 15 of my current squad players must have an xP row
    in the xp_scores table for the next gameweek.
    """
    cur = conn.cursor()

    # How many squad players have a matching xP row?
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM my_picks mp
        JOIN xp_scores x
          ON x.player_id = mp.player_id
         AND x.gameweek  = ?
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks)
    """, (next_gw,))
    scored = cur.fetchone()["cnt"]

    # Total squad size
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM my_picks
        WHERE gameweek = (SELECT MAX(gameweek) FROM my_picks)
    """)
    total = cur.fetchone()["cnt"]

    return check(
        f"All {total} squad players have an xP score for GW{next_gw}",
        scored == total,
        f"{scored}/{total} players scored"
    )


def test_blank_gw_is_zero(conn) -> bool:
    """
    TEST 3: Whenever has_fixture = 0 (blank GW), xP must be exactly 0.0.
    A non-zero score for a player without a fixture is a modelling error.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM xp_scores
        WHERE has_fixture = 0 AND xp_score != 0.0
    """)
    bad = cur.fetchone()["cnt"]

    return check(
        "Blank-GW players always have xP = 0.0",
        bad == 0,
        f"{bad} exceptions found"
    )


def test_explainer_non_empty(conn, next_gw) -> bool:
    """
    TEST 4: The explain_player() function must return a non-empty string
    for every player in my current squad.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT player_id
        FROM my_picks
        WHERE gameweek = (SELECT MAX(gameweek) FROM my_picks)
    """)
    player_ids = [row["player_id"] for row in cur.fetchall()]

    empty_count = 0
    for pid in player_ids:
        text = explain_player(pid, gameweek=next_gw)
        if not text or len(text.strip()) == 0:
            empty_count += 1

    return check(
        "explainer returns non-empty text for all squad players",
        empty_count == 0,
        f"{empty_count} players returned empty explanation"
        if empty_count else "all 15 explanations populated"
    )


def test_injured_players_low_xp(conn, next_gw) -> bool:
    """
    TEST 5: Players with status 'i' (injured) should have a very low xP
    because their minutes_probability is set to 0.05 in the model.
    If an injured player has xP >= 1.5 something has gone wrong.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM xp_scores x
        JOIN players p ON x.player_id = p.id
        WHERE p.status = 'i'
          AND x.gameweek = ?
          AND x.xp_score >= ?
    """, (next_gw, XP_INJURED_CAP))
    bad = cur.fetchone()["cnt"]

    # Also show how many injured players exist for context
    cur.execute("SELECT COUNT(*) AS cnt FROM players WHERE status = 'i'")
    total_injured = cur.fetchone()["cnt"]

    return check(
        f"Injured players have xP < {XP_INJURED_CAP}",
        bad == 0,
        f"{total_injured} injured players found; {bad} exceeded cap"
    )


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FPL Assistant — Model Tests")
    print("=" * 60)

    conn    = get_conn()
    next_gw = get_next_gw(conn)

    print(f"\n  Testing against GW{next_gw} data...\n")

    # Run all tests and collect pass/fail results
    results = [
        test_xp_range(conn, next_gw),
        test_squad_all_scored(conn, next_gw),
        test_blank_gw_is_zero(conn),
        test_explainer_non_empty(conn, next_gw),
        test_injured_players_low_xp(conn, next_gw),
    ]

    conn.close()

    # ---- Summary ----
    passed = sum(1 for r in results if r)
    total  = len(results)

    print(f"\n  {'─'*40}")
    print(f"  Result: {passed}/{total} tests passed")

    if passed == total:
        print("  All tests passed ✓")
    else:
        failed = total - passed
        print(f"  {failed} test(s) FAILED — review the output above.")

    print(f"  {'─'*40}")

    # Exit with a non-zero code if any test failed
    # (useful if this is ever run inside CI or a Makefile)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
