"""
integration_test.py  —  Full Pipeline Integration Test
--------------------------------------------------------
Runs the complete pipeline end-to-end and asserts that each stage
produced the expected output.

Stages:
  1. fetch_fpl.py     → players, fixtures, squad picks
  2. model.py         → xP scores
  3. qualitative.py   → qualitative signals  (may be 0 if sources are offline)
  4. ai_recommend.py  → AI recommendations

Assertions:
  ✓  Squad has exactly 15 players in my_picks
  ✓  xp_scores table is populated for the next GW
  ✓  ai_recommendations table has at least one row for the next GW
  ✓  All xP scores are in the valid range [0, 20]
  ✓  AI recommendation contains a non-empty daily_briefing

Usage:
  python3 engine/integration_test.py            # run full pipeline then check
  python3 engine/integration_test.py --check    # only check DB (skip pipeline)
"""

import sqlite3
import subprocess
import sys
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH      = os.path.join(PROJECT_ROOT, "db", "fpl.db")

PIPELINE = [
    os.path.join(PROJECT_ROOT, "engine", "fetch_fpl.py"),
    os.path.join(PROJECT_ROOT, "engine", "model.py"),
    os.path.join(PROJECT_ROOT, "engine", "qualitative.py"),
    os.path.join(PROJECT_ROOT, "engine", "ai_recommend.py"),
]


# ---------------------------------------------------------------------------
# Helper: print PASS / FAIL
# ---------------------------------------------------------------------------

def check(label: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    detail_str = f"  —  {detail}" if detail else ""
    print(f"  [{status}] {label}{detail_str}")
    return passed


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_stage(script_path):
    """Run one pipeline stage. Returns True if it succeeded."""
    label  = os.path.basename(script_path)
    python = sys.executable

    print(f"\n  ▶  Running {label}...")
    result = subprocess.run(
        [python, script_path],
        cwd=PROJECT_ROOT,
    )
    success = result.returncode == 0
    status  = "OK" if success else f"FAILED (exit {result.returncode})"
    print(f"     └─ {status}")
    return success


def run_pipeline():
    """Run every stage in order. Stop on first hard failure (except qualitative)."""
    print("\n" + "─" * 60)
    print("  STAGE 1 — Running pipeline")
    print("─" * 60)

    for script in PIPELINE:
        if not os.path.exists(script):
            print(f"  [ERROR] Script not found: {script}")
            sys.exit(1)

        success = run_stage(script)

        # qualitative.py failing (e.g. all sources offline) is not fatal
        if not success and "qualitative" in script:
            print("  (qualitative.py failure is non-fatal — continuing)")
            continue

        if not success:
            print(f"\n  [ABORT] Pipeline stopped at {os.path.basename(script)}")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_next_gw(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM gameweeks WHERE finished=0 ORDER BY id LIMIT 1")
    row = cur.fetchone()
    return row["id"] if row else None


def run_assertions():
    print("\n" + "─" * 60)
    print("  STAGE 2 — Assertions")
    print("─" * 60 + "\n")

    # Guard: DB must exist
    if not os.path.exists(DB_PATH):
        print("  [FAIL] db/fpl.db does not exist — run fetch_fpl.py first")
        return False

    conn    = get_conn()
    next_gw = get_next_gw(conn)
    results = []

    # ---- Test 1: players table has data ----
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM players")
    n_players = cur.fetchone()["n"]
    results.append(check(
        "Players table is populated",
        n_players > 0,
        f"{n_players} players",
    ))

    # ---- Test 2: Squad has exactly 15 picks ----
    cur.execute("""
        SELECT COUNT(*) AS n FROM my_picks
        WHERE gameweek = (SELECT MAX(gameweek) FROM my_picks)
    """)
    n_picks = cur.fetchone()["n"]
    results.append(check(
        "Squad has 15 players in my_picks",
        n_picks == 15,
        f"{n_picks}/15 found",
    ))

    # ---- Test 3: xp_scores populated for next GW ----
    if next_gw:
        cur.execute(
            "SELECT COUNT(*) AS n FROM xp_scores WHERE gameweek=?", (next_gw,)
        )
        n_xp = cur.fetchone()["n"]
        results.append(check(
            f"xp_scores populated for GW{next_gw}",
            n_xp > 0,
            f"{n_xp} rows",
        ))

        # ---- Test 4: All xP scores in valid range ----
        cur.execute(
            "SELECT COUNT(*) AS n FROM xp_scores WHERE xp_score < 0 OR xp_score > 20"
        )
        bad_xp = cur.fetchone()["n"]
        cur.execute(
            "SELECT MIN(xp_score) AS lo, MAX(xp_score) AS hi FROM xp_scores WHERE gameweek=?",
            (next_gw,),
        )
        xp_stats = cur.fetchone()
        results.append(check(
            "All xP scores are in range [0, 20]",
            bad_xp == 0,
            f"min={xp_stats['lo']:.2f}, max={xp_stats['hi']:.2f}",
        ))
    else:
        results.append(check("Next GW detected", False, "no upcoming GW in DB"))

    # ---- Test 5: AI recommendations table has a row ----
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_recommendations'")
    table_exists = cur.fetchone() is not None

    if table_exists and next_gw:
        cur.execute(
            "SELECT daily_briefing, transfer_in FROM ai_recommendations WHERE gameweek=?",
            (next_gw,),
        )
        rec_row = cur.fetchone()
        has_rec = rec_row is not None
        results.append(check(
            f"ai_recommendations has a row for GW{next_gw}",
            has_rec,
            "found" if has_rec else "not found — run ai_recommend.py",
        ))

        # ---- Test 6: Daily briefing is non-empty ----
        if has_rec:
            briefing = rec_row["daily_briefing"] or ""
            results.append(check(
                "Daily briefing text is non-empty",
                len(briefing.strip()) > 10,
                f"{len(briefing)} characters",
            ))
        else:
            results.append(check(
                "Daily briefing text is non-empty",
                False,
                "no recommendation row to check",
            ))
    else:
        results.append(check(
            "ai_recommendations table exists",
            table_exists,
            "run ai_recommend.py first" if not table_exists else "",
        ))
        results.append(check(
            "Daily briefing text is non-empty",
            False,
            "depends on previous test passing",
        ))

    # ---- Test 7: qualitative_signals table exists (may be empty) ----
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='qualitative_signals'"
    )
    sig_table = cur.fetchone() is not None
    if sig_table:
        cur.execute("SELECT COUNT(*) AS n FROM qualitative_signals")
        n_sigs = cur.fetchone()["n"]
        results.append(check(
            "qualitative_signals table exists",
            True,
            f"{n_sigs} signal(s) stored (0 is OK if all sources are offline)",
        ))
    else:
        results.append(check(
            "qualitative_signals table exists",
            False,
            "run qualitative.py first",
        ))

    conn.close()
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FPL Assistant — Integration Tests")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    check_only = "--check" in sys.argv

    if check_only:
        print("\n  Mode: --check (skipping pipeline, checking DB only)")
    else:
        print("\n  Mode: full pipeline + assertions")
        print("  (Use --check to skip the pipeline and only assert)")
        run_pipeline()

    results = run_assertions()

    # ---- Summary ----
    passed = sum(1 for r in results if r)
    total  = len(results)

    print(f"\n  {'─' * 40}")
    print(f"  Result: {passed}/{total} assertions passed")

    if passed == total:
        print("  All tests passed ✓")
    else:
        failed = total - passed
        print(f"  {failed} assertion(s) FAILED — review output above")

    print(f"  {'─' * 40}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
