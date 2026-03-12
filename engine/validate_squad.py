"""
validate_squad.py  —  FPL Squad Validator
------------------------------------------
Checks any proposed 15-player squad against every official FPL rule.
Returns a list of plain-English violations, or an empty list if the
squad is fully legal.

The recommendation engine (api_server.py /recommend and ai_recommend.py)
calls this before outputting any suggestion so we never surface an
illegal squad to the user.

Usage (standalone):
    python3 engine/validate_squad.py          # validates your current DB squad
    python3 engine/validate_squad.py --help

Usage (from another module):
    from validate_squad import validate_squad

    violations = validate_squad(players)
    if violations:
        for v in violations:
            print(f"  ✗ {v}")
    else:
        print("  ✓ Valid squad")
"""

import sqlite3
import os
import sys

# Pull all the rule constants from fpl_rules.py so this file never has
# magic numbers — every constraint traces back to its named rule.
sys.path.insert(0, os.path.dirname(__file__))
from fpl_rules import (
    SQUAD_SIZE,
    STARTERS,
    BENCH_SIZE,
    BENCH_GK_SLOT,
    GKP, DEF, MID, FWD,
    POSITION_NAMES,
    REQUIRED_SQUAD_COUNTS,
    MAX_PLAYERS_PER_CLUB,
    MIN_STARTERS,
    EXACT_STARTERS,
)

# Path to the database — used when running this script directly.
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")
ENTRY_ID = 140222   # Tiki Taka CF


# ---------------------------------------------------------------------------
# Core validation function
# ---------------------------------------------------------------------------

def validate_squad(players: list[dict]) -> list[str]:
    """
    Validate a proposed squad against all FPL rules.

    Args:
        players: A list of 15 dicts, one per player.  Each dict must have:
            - "name"      (str)  : display name, e.g. "Haaland"
            - "position"  (int)  : 1=GKP 2=DEF 3=MID 4=FWD  (element_type)
            - "team"      (str)  : club short name, e.g. "MCI"
            - "squad_pos" (int)  : 1–11 = starting XI, 12–15 = bench

    Returns:
        A list of violation strings.  Empty list means the squad is valid.

    Example:
        violations = validate_squad(my_squad)
        if not violations:
            print("Valid squad!")
        else:
            for v in violations:
                print(f"  Problem: {v}")
    """
    violations = []

    # -----------------------------------------------------------------------
    # Check 1: Total squad size must be exactly 15
    # -----------------------------------------------------------------------
    if len(players) != SQUAD_SIZE:
        violations.append(
            f"Squad has {len(players)} player(s) — must be exactly {SQUAD_SIZE}."
        )
        # Can't run position or bench checks without the right number of players
        return violations

    # -----------------------------------------------------------------------
    # Check 2: Starter / bench split
    # -----------------------------------------------------------------------
    starters = [p for p in players if p["squad_pos"] <= STARTERS]
    bench    = [p for p in players if p["squad_pos"] >  STARTERS]

    if len(starters) != STARTERS:
        violations.append(
            f"Starting XI has {len(starters)} player(s) — must be exactly {STARTERS}."
        )
    if len(bench) != BENCH_SIZE:
        violations.append(
            f"Bench has {len(bench)} player(s) — must be exactly {BENCH_SIZE}."
        )

    # -----------------------------------------------------------------------
    # Check 3: Whole-squad position counts
    # FPL requires exactly: 2 GKPs, 5 DEFs, 5 MIDs, 3 FWDs
    # -----------------------------------------------------------------------
    squad_pos_counts = {GKP: 0, DEF: 0, MID: 0, FWD: 0}
    for p in players:
        pos = p["position"]
        if pos in squad_pos_counts:
            squad_pos_counts[pos] += 1
        else:
            violations.append(
                f"{p['name']} has an unknown position code ({pos}) — "
                f"expected 1=GKP, 2=DEF, 3=MID, 4=FWD."
            )

    for pos, required in REQUIRED_SQUAD_COUNTS.items():
        actual = squad_pos_counts.get(pos, 0)
        if actual != required:
            violations.append(
                f"Squad must contain exactly {required} {POSITION_NAMES[pos]}(s) "
                f"— found {actual}."
            )

    # -----------------------------------------------------------------------
    # Check 4: Maximum 3 players from the same Premier League club
    # -----------------------------------------------------------------------
    club_counts: dict[str, int] = {}
    for p in players:
        club = p["team"]
        club_counts[club] = club_counts.get(club, 0) + 1

    for club, count in club_counts.items():
        if count > MAX_PLAYERS_PER_CLUB:
            # Find the offending names for a helpful error message
            offenders = [p["name"] for p in players if p["team"] == club]
            violations.append(
                f"Club limit exceeded: {count} players from {club} "
                f"(max {MAX_PLAYERS_PER_CLUB}). "
                f"Players: {', '.join(offenders)}."
            )

    # -----------------------------------------------------------------------
    # Check 5: Starting XI formation rules
    # GKP: exactly 1 | DEF: at least 3 | MID: at least 2 | FWD: at least 1
    # -----------------------------------------------------------------------
    starter_pos_counts = {GKP: 0, DEF: 0, MID: 0, FWD: 0}
    for p in starters:
        pos = p["position"]
        if pos in starter_pos_counts:
            starter_pos_counts[pos] += 1

    # GKP must be exactly 1 in the starting XI
    for pos, exact in EXACT_STARTERS.items():
        actual = starter_pos_counts.get(pos, 0)
        if actual != exact:
            violations.append(
                f"Starting XI must have exactly {exact} {POSITION_NAMES[pos]} "
                f"— found {actual}."
            )

    # DEF, MID, FWD: check minimums
    for pos, minimum in MIN_STARTERS.items():
        if pos in EXACT_STARTERS:
            continue   # already handled above
        actual = starter_pos_counts.get(pos, 0)
        if actual < minimum:
            violations.append(
                f"Formation requires at least {minimum} {POSITION_NAMES[pos]}(s) "
                f"in the starting XI — found {actual}."
            )

    # -----------------------------------------------------------------------
    # Check 6: Bench order — first bench slot must be the emergency GKP
    # Squad position 12 is the first substitute and must be a goalkeeper.
    # -----------------------------------------------------------------------
    # Find the player sitting in bench slot 1 (squad_pos == 12)
    first_bench_player = next(
        (p for p in players if p["squad_pos"] == BENCH_GK_SLOT), None
    )
    bench_gkps = [p for p in bench if p["position"] == GKP]

    if bench_gkps:
        # There IS a bench GKP — make sure they're in slot 1
        if first_bench_player and first_bench_player["position"] != GKP:
            violations.append(
                f"Bench order error: the backup goalkeeper ({bench_gkps[0]['name']}) "
                f"must occupy bench slot 1 (squad position 12) as the emergency GK. "
                f"Currently slot 1 has {first_bench_player['name']} "
                f"({POSITION_NAMES.get(first_bench_player['position'], '?')})."
            )
    else:
        # No GKP on the bench at all — this only happens if there's already a
        # squad composition error (caught in Check 3), but flag it explicitly.
        violations.append(
            "No backup goalkeeper on the bench — the squad needs 2 GKPs in total."
        )

    return violations


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def is_valid(players: list[dict]) -> bool:
    """Return True if the squad passes all checks, False otherwise."""
    return len(validate_squad(players)) == 0


def validate_and_print(players: list[dict]) -> bool:
    """
    Validate a squad and print a formatted result to the terminal.

    Returns True if valid, False if there are violations.
    """
    violations = validate_squad(players)

    if not violations:
        print("  ✓  Valid squad — all FPL rules pass.")
        return True

    print(f"  ✗  Squad has {len(violations)} violation(s):")
    for v in violations:
        print(f"       • {v}")
    return False


# ---------------------------------------------------------------------------
# DB helper: load current squad from fpl.db
# ---------------------------------------------------------------------------

def load_squad_from_db(conn, entry_id: int = ENTRY_ID) -> list[dict]:
    """
    Load the most recent squad picks from the database and return them
    in the format validate_squad() expects.

    Args:
        conn:     An open sqlite3 connection.
        entry_id: The FPL entry ID to load (default: 140222).

    Returns:
        A list of player dicts ready for validate_squad().
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT
            mp.position   AS squad_pos,
            p.web_name    AS name,
            p.element_type AS position,
            t.short_name  AS team,
            ROUND(p.now_cost / 10.0, 1) AS price
        FROM my_picks mp
        JOIN players p ON mp.player_id = p.id
        JOIN teams   t ON p.team_id    = t.id
        WHERE mp.gameweek = (
            SELECT MAX(gameweek) FROM my_picks
            WHERE entry_id = ? OR entry_id IS NULL
        )
          AND (mp.entry_id = ? OR mp.entry_id IS NULL)
        ORDER BY mp.position
    """, (entry_id, entry_id))

    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Main — run this script directly to validate your current DB squad
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print("  FPL Squad Validator")
    print(f"  Entry: {ENTRY_ID} (Tiki Taka CF)")
    print("=" * 55)

    if not os.path.exists(DB_PATH):
        print("\n[ERROR] db/fpl.db not found. Run engine/fetch_fpl.py first.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    players = load_squad_from_db(conn)
    conn.close()

    if not players:
        print("\n[ERROR] No squad found in the database.")
        print("        Run engine/fetch_fpl.py to fetch your picks.")
        sys.exit(1)

    # Print the squad being validated
    print(f"\n  Validating {len(players)}-player squad:\n")
    for p in players:
        slot = "Starter" if p["squad_pos"] <= STARTERS else "Bench  "
        pos  = POSITION_NAMES.get(p["position"], "?")
        print(f"    {slot} #{p['squad_pos']:2}  {p['name']:<22} {pos}  {p['team']}")

    print()
    valid = validate_and_print(players)
    print()
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
