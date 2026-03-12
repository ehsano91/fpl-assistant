"""
explainer.py  —  Player xP Explanation Helper
----------------------------------------------
A small helper module that takes a player ID (and an optional gameweek)
and returns a 3-sentence plain-English explanation of:
  1. What their projected score is and the fixture context
  2. What's driving the score (form vs positional average)
  3. Fixture difficulty or availability concern

Import and use from other scripts:
    from engine.explainer import explain_player
    print(explain_player(233))  # Mo Salah, next GW

Or run directly to explain every player in your current squad:
    python engine/explainer.py
"""

import sqlite3
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")

# Human-readable labels for FPL element_type codes
POSITION_LABELS = {
    1: "Goalkeeper",
    2: "Defender",
    3: "Midfielder",
    4: "Forward",
}

# Human-readable availability descriptions for FPL status codes
STATUS_DESCRIPTIONS = {
    "a": "fully available",
    "d": "doubtful to play",
    "i": "injured",
    "u": "at risk of rotation",
    "s": "suspended",
    "n": "ineligible / not registered",
}


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def explain_player(player_id: int, gameweek: int = None) -> str:
    """
    Return a 3-sentence human-readable explanation of a player's xP score.

    Args:
        player_id : FPL element ID (the 'id' column in the players table)
        gameweek  : GW number to explain. Defaults to the next unfinished GW.

    Returns:
        A single string containing exactly 3 sentences, or an error message
        if data is missing.
    """
    # Open a fresh connection each time so this function is safe to call
    # from any script without sharing state
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # ------------------------------------------------------------------ #
    # Resolve gameweek
    # ------------------------------------------------------------------ #
    if gameweek is None:
        cur.execute("""
            SELECT id FROM gameweeks
            WHERE finished = 0
            ORDER BY id
            LIMIT 1
        """)
        gw_row = cur.fetchone()
        if not gw_row:
            conn.close()
            return "No upcoming gameweeks found. Run engine/fetch_fpl.py to refresh data."
        gameweek = gw_row["id"]

    # ------------------------------------------------------------------ #
    # Load player info
    # ------------------------------------------------------------------ #
    cur.execute("""
        SELECT p.*, t.name AS team_name, t.short_name AS team_short
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.id = ?
    """, (player_id,))
    player = cur.fetchone()

    if not player:
        conn.close()
        return (f"Player ID {player_id} not found in the database. "
                f"Run engine/fetch_fpl.py to refresh player data.")

    # ------------------------------------------------------------------ #
    # Load xP score
    # ------------------------------------------------------------------ #
    cur.execute("""
        SELECT x.*, t.name AS opp_name, t.short_name AS opp_short
        FROM xp_scores x
        LEFT JOIN teams t ON x.opponent_id = t.id
        WHERE x.player_id = ? AND x.gameweek = ?
    """, (player_id, gameweek))
    xp = cur.fetchone()
    conn.close()

    if not xp:
        return (
            f"No xP score found for {player['web_name']} in GW{gameweek}. "
            f"Run engine/model.py first to compute expected-points scores. "
            f"Once generated, re-run this function."
        )

    # Convenience aliases
    name    = player["web_name"]
    team    = player["team_name"]
    pos     = POSITION_LABELS.get(player["element_type"], "player")
    avail   = STATUS_DESCRIPTIONS.get(player["status"], "status unknown")
    score   = xp["xp_score"]
    ff      = xp["form_factor"]
    af      = xp["attack_factor"]
    dw      = xp["def_weakness"]
    cp      = xp["cs_prob"]
    mp      = xp["minutes_prob"]
    is_home = xp["is_home"]
    opp     = xp["opp_name"] or "their opponent"
    etype   = player["element_type"]

    # ================================================================== #
    # SENTENCE 1 — Overview: who is this player and what's their score?
    # ================================================================== #
    if not xp["has_fixture"]:
        s1 = (
            f"{name} ({team}, {pos}) has a projected score of {score:.1f} xP "
            f"for GW{gameweek} — their team has no fixture this week (blank gameweek), "
            f"so they are guaranteed to score zero points."
        )
    else:
        venue = "at home" if is_home else "away"
        s1 = (
            f"{name} ({team}, {pos}) is projected to score {score:.1f} expected points "
            f"in GW{gameweek}, playing {venue} against {opp}."
        )

    # ================================================================== #
    # SENTENCE 2 — Main driver: form (player quality relative to position)
    # ================================================================== #
    if ff >= 1.5:
        s2 = (
            f"Their season-long form is outstanding — they are accumulating points at "
            f"{ff:.1f}× the average rate for a {pos}, which is the biggest single driver "
            f"of their strong projection."
        )
    elif ff >= 1.1:
        s2 = (
            f"Their form is above average for a {pos} ({ff:.1f}× the positional baseline), "
            f"providing a solid points floor before even considering the fixture."
        )
    elif ff >= 0.8:
        s2 = (
            f"They are producing close to the positional average for a {pos} "
            f"({ff:.1f}× the baseline), so the fixture context plays a larger role "
            f"in determining their projection."
        )
    else:
        s2 = (
            f"Their season form is well below average for a {pos} "
            f"({ff:.1f}× the positional baseline), which significantly depresses "
            f"their expected return regardless of the fixture."
        )

    # ================================================================== #
    # SENTENCE 3 — Fixture difficulty, CS outlook, or availability risk
    # ================================================================== #
    # Priority: injury/suspension > blank GW > defensive outlook > attacking
    if player["status"] in ("i", "s", "n"):
        s3 = (
            f"Availability is a key concern — they are currently {avail} "
            f"(only a {mp*100:.0f}% chance of playing), "
            f"which sharply reduces their expected output."
        )
    elif not xp["has_fixture"]:
        s3 = (
            f"Without a fixture this week there is nothing to gain, "
            f"so they should sit on the bench or be considered for transfer "
            f"if a better-fixture alternative is available."
        )
    elif etype in (1, 2):
        # Defensive players — lead with clean-sheet chance
        if cp >= 0.40:
            s3 = (
                f"The clean-sheet outlook is encouraging (~{cp*100:.0f}% probability) "
                f"because {opp} have one of the weaker attacks in the league, "
                f"giving this {pos} a meaningful defensive bonus ceiling."
            )
        elif cp >= 0.25:
            s3 = (
                f"The clean-sheet chance is moderate (~{cp*100:.0f}%), "
                f"meaning defensive bonus points are possible but not reliable — "
                f"this {pos} is a decent, if not premium, pick."
            )
        else:
            s3 = (
                f"The clean-sheet prospect is slim (~{cp*100:.0f}%) as {opp} "
                f"carry a genuine attacking threat, limiting the upside "
                f"for this {pos} beyond basic appearance points."
            )
    else:
        # MID or FWD — lead with attacking fixture context
        combo = af * dw
        if combo >= 1.4:
            s3 = (
                f"The fixture is highly favourable from an attacking perspective — "
                f"{team}'s attack rates at {af:.2f}× the league average and "
                f"{opp} concede at {dw:.2f}× the average, "
                f"creating a genuine upside for goals and assists."
            )
        elif combo >= 0.9:
            s3 = (
                f"The fixture is broadly neutral — {team}'s attack ({af:.2f}×) and "
                f"{opp}'s defensive record ({dw:.2f}×) are both close to league average, "
                f"so the projection leans on the player's own form rather than a fixture edge."
            )
        else:
            s3 = (
                f"The fixture is tough — {opp} have a sound defence (conceding at "
                f"only {dw:.2f}× the average rate), which caps the attacking ceiling "
                f"and makes this a riskier captaincy or transfer option."
            )

    # ================================================================== #
    # Combine into one return string
    # ================================================================== #
    return f"{s1} {s2} {s3}"


# ---------------------------------------------------------------------------
# Convenience: run directly to explain the full current squad
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  FPL Assistant — Player Explainer")
    print("=" * 70)

    db_abs = os.path.abspath(DB_PATH)
    if not os.path.exists(db_abs):
        print(f"\n[ERROR] Database not found at {db_abs}")
        print("  Run engine/fetch_fpl.py then engine/model.py first.")
        sys.exit(1)

    conn = sqlite3.connect(db_abs)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # Find the next GW
    cur.execute("SELECT id FROM gameweeks WHERE finished=0 ORDER BY id LIMIT 1")
    gw_row = cur.fetchone()
    if not gw_row:
        print("[ERROR] No upcoming GWs in DB. Re-run fetch_fpl.py.")
        conn.close()
        sys.exit(1)
    next_gw = gw_row["id"]

    # Grab my squad (ordered by squad position)
    cur.execute("""
        SELECT mp.player_id, p.web_name, mp.position
        FROM my_picks mp
        JOIN players p ON mp.player_id = p.id
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks)
        ORDER BY mp.position
    """)
    picks = cur.fetchall()
    conn.close()

    print(f"\n  Explaining GW{next_gw} xP scores for Tiki Taka CF ({len(picks)} players)\n")

    for pick in picks:
        print(f"  {'─'*68}")
        print(f"  #{pick['position']}  {pick['web_name']}")
        print(f"  {'─'*68}")
        explanation = explain_player(pick["player_id"], gameweek=next_gw)
        # Wrap at ~70 chars for readability
        import textwrap
        for line in textwrap.wrap(explanation, width=68):
            print(f"  {line}")
        print()

    print("=" * 70)


if __name__ == "__main__":
    main()
