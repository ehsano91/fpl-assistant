"""
model.py  —  Expected Points (xP) Model v1
-------------------------------------------
Calculates how many FPL points each player is likely to score over the
next 1–6 gameweeks, using data already stored in db/fpl.db.

Model inputs (all derived from the local DB, no extra downloads needed):
  • minutes_probability  — how likely the player is to play, based on status
  • team_attack_strength — how well the player's team scores, vs league average
  • opponent_def_weakness— how many goals the opponent concedes, vs league avg
  • clean_sheet_prob     — chance the player's team keeps a clean sheet
  • form_factor          — player's actual PPG vs the average for their position
  • bonus_baseline       — small bonus-point expectation per position

Results are saved to the xp_scores table in db/fpl.db.

Run from the project root:
    python engine/model.py
"""

import sqlite3
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH    = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")
ENTRY_ID   = 140222          # Tiki Taka CF
GWS_AHEAD  = 6               # how many upcoming gameweeks to score

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

# Probability the player plays 60+ minutes, keyed by FPL status code
STATUS_PROB = {
    "a": 0.90,   # available
    "d": 0.50,   # doubtful
    "i": 0.05,   # injured
    "u": 0.10,   # unavailable / squad rotation risk
    "s": 0.05,   # suspended
    "n": 0.00,   # not registered
}

# Expected "attacking contribution units" per 90 minutes, by position.
# 1 unit is worth roughly 5 FPL points (blend of goals + assists).
# Calibrated so that an elite FWD (form_factor ~1.5) in a great fixture
# reaches ~10 xP — still safely below the 20-point hard cap.
#   GKP barely touches the ball in attack → 0
#   DEF scores ~0.08 attacking units per game on average
#   MID scores ~0.25 goals+assists per game
#   FWD scores ~0.55 goals+assists per game
ATTACK_BASE = {1: 0.00, 2: 0.08, 3: 0.25, 4: 0.55}
ATTACK_PTS_PER_UNIT = 5.0      # FPL pts per attacking unit

# Hard ceiling on xP — even a DGW elite player shouldn't exceed this
XP_HARD_CAP = 20.0

# Clean-sheet bonus points awarded by the game by position
CS_PTS = {1: 4.0, 2: 4.0, 3: 1.0, 4: 0.0}

# Average save-point yield per game for a goalkeeper (3 saves = 1 pt)
GKP_SAVE_BONUS = 1.0

# Bonus point expectation per game — attackers tend to feature more in BPS
BONUS_BASE = {1: 0.10, 2: 0.20, 3: 0.40, 4: 0.40}

# Season-average PPG per position (used to measure a player's relative form)
POSITION_AVG_PPG = {1: 3.5, 2: 3.5, 3: 4.5, 4: 4.5}

# Human-readable position labels
POS_LABEL = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # access columns by name
    return conn


def create_xp_table(conn):
    """Create the xp_scores table (safe to call repeatedly)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xp_scores (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id     INTEGER NOT NULL,
            gameweek      INTEGER NOT NULL,
            xp_score      REAL,          -- total expected points for this GW
            minutes_prob  REAL,          -- probability of playing
            attack_factor REAL,          -- team attack vs league avg (1.0 = average)
            def_weakness  REAL,          -- opponent defence weakness (1.0 = average)
            cs_prob       REAL,          -- estimated clean-sheet probability
            form_factor   REAL,          -- player's PPG vs positional average
            has_fixture   INTEGER,       -- 1 if team plays; 0 if blank GW
            opponent_id   INTEGER,       -- NULL if blank GW
            is_home       INTEGER,       -- 1 = home; 0 = away; NULL = blank
            computed_at   TEXT,          -- UTC timestamp of last run
            UNIQUE(player_id, gameweek) ON CONFLICT REPLACE
        )
    """)
    conn.commit()
    print("[DB]  xp_scores table ready.")


# ---------------------------------------------------------------------------
# Step 1 — Build team-level attack / defence stats
# ---------------------------------------------------------------------------

def load_team_stats(conn):
    """
    Calculate each team's goals-per-game (attack) and goals-conceded-per-game
    (defence) from finished fixtures.

    Returns:
        stats        — dict {team_id: {'attack_per_game', 'concede_per_game', 'games'}}
        league_avg   — float, league-average goals per team per game
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id,
            -- goals this team scored across all home AND away games
            SUM(CASE WHEN f.team_h = t.id
                     THEN f.team_h_score
                     ELSE f.team_a_score END)  AS scored,
            -- goals this team conceded across all games
            SUM(CASE WHEN f.team_h = t.id
                     THEN f.team_a_score
                     ELSE f.team_h_score END)  AS conceded,
            COUNT(*)                           AS games
        FROM teams t
        JOIN fixtures f ON (f.team_h = t.id OR f.team_a = t.id)
        WHERE f.finished = 1
        GROUP BY t.id
    """)

    stats = {}
    total_goals = 0
    total_game_slots = 0   # each fixture = 2 slots (one per team)

    for row in cur.fetchall():
        scored   = row["scored"]   or 0
        conceded = row["conceded"] or 0
        games    = row["games"]    or 1
        stats[row["id"]] = {
            "attack_per_game":  scored   / games,
            "concede_per_game": conceded / games,
            "games":            games,
        }
        total_goals      += scored
        total_game_slots += games

    # League average: total goals across all team-appearances divided by appearances
    league_avg = total_goals / total_game_slots if total_game_slots else 1.5
    return stats, league_avg


# ---------------------------------------------------------------------------
# Step 2 — Identify upcoming gameweeks and their fixtures
# ---------------------------------------------------------------------------

def get_upcoming_gws(conn):
    """Return the IDs of the next GWS_AHEAD unfinished gameweeks."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM gameweeks
        WHERE finished = 0
        ORDER BY id
        LIMIT ?
    """, (GWS_AHEAD,))
    return [row["id"] for row in cur.fetchall()]


def get_fixtures_by_gw(conn, gw_ids):
    """
    For a list of GW ids, return a dict:
        {gw_id: [{'fixture': row, 'is_home': bool}, ...]}
    Each fixture appears twice — once for the home team, once for the away team.
    """
    placeholders = ",".join("?" for _ in gw_ids)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, gameweek, team_h, team_a
        FROM fixtures
        WHERE gameweek IN ({placeholders})
        AND finished = 0
    """, gw_ids)

    # Build a team-centric view: which games does each team play in each GW?
    gw_map = {}   # {gw_id: {team_id: [fixture_entries]}}
    for row in cur.fetchall():
        gw = row["gameweek"]
        gw_map.setdefault(gw, {})
        fixture = dict(row)
        # Register for the home team
        gw_map[gw].setdefault(row["team_h"], []).append(
            {"fixture": fixture, "is_home": True}
        )
        # Register for the away team
        gw_map[gw].setdefault(row["team_a"], []).append(
            {"fixture": fixture, "is_home": False}
        )
    return gw_map


# ---------------------------------------------------------------------------
# Step 3 — xP calculation for a single fixture
# ---------------------------------------------------------------------------

def calc_xp_one_fixture(player, team_stats, league_avg, fixture_entry):
    """
    Calculate expected FPL points for one player in one fixture.

    Returns a dict of all model components (useful for explanations later).
    """
    team_id  = player["team_id"]
    is_home  = fixture_entry["is_home"]
    fix      = fixture_entry["fixture"]
    opp_id   = fix["team_a"] if is_home else fix["team_h"]

    # Fallback stats if a team somehow isn't in our DB
    fallback = {"attack_per_game": league_avg, "concede_per_game": league_avg, "games": 29}
    my_stats  = team_stats.get(team_id, fallback)
    opp_stats = team_stats.get(opp_id,  fallback)

    # ------------------------------------------------------------------ #
    # Input variables
    # ------------------------------------------------------------------ #

    # 1. Minutes probability — from player's availability status
    minutes_prob = STATUS_PROB.get(player["status"], 0.5)

    # 2. Form factor — how good is this player vs the average at their position?
    #    Uses the full-season PPG as a proxy for quality.
    games_so_far = my_stats["games"] or 29
    ppg          = player["total_points"] / games_so_far
    pos_avg      = POSITION_AVG_PPG[player["element_type"]]
    form_factor  = ppg / pos_avg if pos_avg else 1.0
    form_factor  = max(0.25, min(2.0, form_factor))   # clamp outliers

    # 3. Team attack strength (vs league average)
    #    e.g. Man City (2.0 gpg) vs league avg (1.4 gpg) → factor = 1.43
    attack_factor = my_stats["attack_per_game"] / league_avg
    attack_factor = max(0.5, min(2.0, attack_factor))

    # 4. Opponent defensive weakness (vs league average)
    #    e.g. Wolves concede 1.7 gpg vs avg 1.4 → weakness = 1.21
    def_weakness = opp_stats["concede_per_game"] / league_avg
    def_weakness = max(0.5, min(2.0, def_weakness))

    # 5. Home advantage — home teams score ~14% more on average
    home_mult = 1.08 if is_home else 0.95

    # 6. Clean-sheet probability
    #    Inverse of how threatening the opponent's attack is.
    #    Formula: 0.35 / opp_attack_norm  (so avg opp → ~35% CS chance)
    opp_attack_norm = opp_stats["attack_per_game"] / league_avg
    cs_prob = max(0.05, min(0.65, 0.35 / max(opp_attack_norm, 0.1)))

    # ------------------------------------------------------------------ #
    # xP components (all additive)
    # ------------------------------------------------------------------ #
    pos = player["element_type"]

    # Appearance points — 2 pts for playing 60+ mins
    appearance_xp = 2.0 * minutes_prob

    # Attacking returns — goal / assist contribution scaled by fixture context
    attack_xp = (
        ATTACK_BASE[pos]
        * ATTACK_PTS_PER_UNIT
        * attack_factor
        * def_weakness
        * home_mult
        * form_factor
        * minutes_prob
    )

    # Clean sheet points — only meaningful for GKP/DEF/MID
    cs_xp = CS_PTS[pos] * cs_prob * form_factor * minutes_prob

    # Save bonus — only for GKP
    save_xp = GKP_SAVE_BONUS * minutes_prob if pos == 1 else 0.0

    # Bonus points (BPS-based, small but real)
    bonus_xp = BONUS_BASE[pos] * form_factor * minutes_prob

    total_xp = max(0.0, min(XP_HARD_CAP, appearance_xp + attack_xp + cs_xp + save_xp + bonus_xp))

    return {
        "xp_score":     round(total_xp, 3),
        "minutes_prob": round(minutes_prob, 3),
        "attack_factor":round(attack_factor, 3),
        "def_weakness": round(def_weakness, 3),
        "cs_prob":      round(cs_prob, 3),
        "form_factor":  round(form_factor, 3),
        "opponent_id":  opp_id,
        "is_home":      int(is_home),
    }


# ---------------------------------------------------------------------------
# Step 4 — Run the model over all players × all upcoming GWs
# ---------------------------------------------------------------------------

def run_model(conn):
    """
    Core loop: for every player, for every upcoming GW, calculate xP and save.
    Handles blank GWs (no fixture) and double GWs (two fixtures = summed xP).
    """
    print("\n[MODEL] Loading team stats from finished fixtures...")
    team_stats, league_avg = load_team_stats(conn)
    print(f"[MODEL] League avg goals per team per game: {league_avg:.3f}")

    upcoming_gws = get_upcoming_gws(conn)
    if not upcoming_gws:
        print("[WARN]  No upcoming gameweeks found.")
        return []
    print(f"[MODEL] Upcoming GWs to score: {upcoming_gws}")

    gw_map = get_fixtures_by_gw(conn, upcoming_gws)

    # Load every player from the DB
    cur = conn.cursor()
    cur.execute("""
        SELECT id, element_type, team_id, total_points, status, web_name
        FROM players
    """)
    players = [dict(r) for r in cur.fetchall()]
    print(f"[MODEL] Scoring {len(players)} players × {len(upcoming_gws)} GWs...")

    now = datetime.utcnow().isoformat()
    rows_saved = 0

    for gw_id in upcoming_gws:
        team_fixtures = gw_map.get(gw_id, {})   # {team_id: [fixture_entries]}

        for player in players:
            tid      = player["team_id"]
            pid      = player["id"]
            fixtures = team_fixtures.get(tid, [])

            if not fixtures:
                # ---- Blank GW: team has no match this week ----
                conn.execute("""
                    INSERT OR REPLACE INTO xp_scores
                        (player_id, gameweek, xp_score, minutes_prob, attack_factor,
                         def_weakness, cs_prob, form_factor,
                         has_fixture, opponent_id, is_home, computed_at)
                    VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, NULL, NULL, ?)
                """, (pid, gw_id, now))
            else:
                # ---- Normal or Double GW: sum xP across all fixtures ----
                total_xp = 0.0
                last     = None
                for fx_entry in fixtures:
                    result   = calc_xp_one_fixture(player, team_stats, league_avg, fx_entry)
                    total_xp += result["xp_score"]
                    last      = result

                conn.execute("""
                    INSERT OR REPLACE INTO xp_scores
                        (player_id, gameweek, xp_score, minutes_prob, attack_factor,
                         def_weakness, cs_prob, form_factor,
                         has_fixture, opponent_id, is_home, computed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """, (
                    pid, gw_id,
                    round(total_xp, 3),
                    last["minutes_prob"], last["attack_factor"],
                    last["def_weakness"], last["cs_prob"], last["form_factor"],
                    last["opponent_id"],  last["is_home"],
                    now,
                ))
            rows_saved += 1

        conn.commit()   # commit after each GW for safety

    print(f"[MODEL] {rows_saved} xP rows saved to db/fpl.db.")
    return upcoming_gws


# ---------------------------------------------------------------------------
# Step 5 — Generate plain-English reasons for a player's score
# ---------------------------------------------------------------------------

def generate_reasons(row):
    """
    Produce 2–3 plain-English bullet points explaining a player's xP score.
    `row` is a sqlite3.Row from the squad-ranking query below.
    """
    reasons = []
    pos = POS_LABEL.get(row["element_type"], "?")

    # ---- Reason 1: Form ----
    ff = row["form_factor"]
    if ff >= 1.4:
        reasons.append(
            f"Excellent form — producing {ff:.1f}× the seasonal average for a {pos}."
        )
    elif ff >= 1.0:
        reasons.append(
            f"Solid form — slightly above-average output for a {pos} this season."
        )
    else:
        reasons.append(
            f"Below-par season — only {ff:.1f}× the {pos} positional average."
        )

    # ---- Reason 2: Fixture ----
    if not row["has_fixture"]:
        reasons.append("Blank gameweek — no fixture, guaranteed zero points.")
    else:
        venue = "home" if row["is_home"] else "away"
        opp   = row["opponent_name"] or "opponent"
        combo = row["attack_factor"] * row["def_weakness"]
        if combo >= 1.4:
            reasons.append(
                f"Favourable {venue} fixture vs {opp} — "
                f"strong attack ({row['attack_factor']:.2f}×) meets leaky defence ({row['def_weakness']:.2f}×)."
            )
        elif combo >= 0.9:
            reasons.append(
                f"Neutral {venue} fixture vs {opp} — "
                f"average difficulty for attacking returns."
            )
        else:
            reasons.append(
                f"Difficult {venue} fixture vs {opp} — "
                f"solid defence limits scoring potential."
            )

    # ---- Reason 3: CS outlook (GKP/DEF) or availability ----
    status = row["status"]
    if status in ("i", "s", "n"):
        reasons.append(
            f"Fitness/suspension concern — only {row['minutes_prob']*100:.0f}% "
            f"chance of playing significantly reduces expected output."
        )
    elif status == "d":
        reasons.append("Fitness doubt — roughly 50/50 chance of starting.")
    elif row["element_type"] in (1, 2):   # GKP or DEF
        cp = row["cs_prob"]
        if cp >= 0.40:
            reasons.append(
                f"Good clean-sheet chance (~{cp*100:.0f}%) — "
                f"opponent rarely scores, boosting the defensive premium."
            )
        elif cp >= 0.25:
            reasons.append(
                f"Moderate clean-sheet chance (~{cp*100:.0f}%) — "
                f"defensively viable but not a banker."
            )
        else:
            reasons.append(
                f"Low clean-sheet chance (~{cp*100:.0f}%) — "
                f"opponent's attack limits defensive upside."
            )
    else:
        # MID or FWD
        if row["attack_factor"] >= 1.3:
            reasons.append(
                f"Playing for a potent attack (factor {row['attack_factor']:.2f}×) — "
                f"high floor for goals and assists."
            )
        elif row["def_weakness"] >= 1.3:
            reasons.append(
                f"Facing a porous defence (weakness {row['def_weakness']:.2f}×) — "
                f"ceiling is raised for attacking returns."
            )
        else:
            reasons.append(
                "Mid-range attacking returns expected — no exceptional fixture edges."
            )

    return reasons


# ---------------------------------------------------------------------------
# Step 6 — Print ranked squad table
# ---------------------------------------------------------------------------

def print_squad_ranking(conn, upcoming_gws):
    """Print Tiki Taka CF's 15 players ranked by next-GW xP, with reasons."""
    next_gw = upcoming_gws[0]
    print(f"\n{'='*72}")
    print(f"  Tiki Taka CF — xP Ranking for GW{next_gw}")
    print(f"{'='*72}")

    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.id, p.web_name, p.element_type, p.status,
            t.short_name          AS team_name,
            x.xp_score, x.minutes_prob, x.attack_factor,
            x.def_weakness, x.cs_prob, x.form_factor, x.has_fixture,
            x.is_home,
            mp.is_captain, mp.is_vice_captain,
            mp.position           AS squad_pos,
            opp.short_name        AS opponent_name
        FROM my_picks mp
        JOIN players   p   ON mp.player_id = p.id
        JOIN teams     t   ON p.team_id    = t.id
        JOIN xp_scores x   ON x.player_id  = p.id AND x.gameweek = ?
        LEFT JOIN teams opp ON x.opponent_id = opp.id
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks)
        ORDER BY x.xp_score DESC
    """, (next_gw,))

    rows = cur.fetchall()

    print(f"\n  {'Rank':<5} {'Name':<22} {'Pos':<5} {'Team':<5} {'xP':>5}  Fixture")
    print(f"  {'-'*68}")

    for i, row in enumerate(rows, 1):
        cap_tag  = " [C]" if row["is_captain"] else (" [V]" if row["is_vice_captain"] else "")
        name_str = row["web_name"] + cap_tag

        if row["has_fixture"]:
            venue       = "H" if row["is_home"] else "A"
            fixture_str = f"vs {row['opponent_name']}({venue})"
        else:
            fixture_str = "BLANK GW"

        print(f"\n  {i:<5} {name_str:<22} "
              f"{POS_LABEL[row['element_type']]:<5} "
              f"{row['team_name']:<5} "
              f"{row['xp_score']:>5.2f}  {fixture_str}")

        # Print 2–3 reasons indented below each player
        for reason in generate_reasons(row):
            print(f"        → {reason}")

    print(f"\n  {'='*72}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  FPL Assistant — Expected Points Model v1")
    print(f"  Entry: {ENTRY_ID} (Tiki Taka CF)")
    print("=" * 60)

    conn = get_conn()
    create_xp_table(conn)

    upcoming_gws = run_model(conn)

    if upcoming_gws:
        print_squad_ranking(conn, upcoming_gws)
        print(f"\n  xP scores for GWs {upcoming_gws} saved to db/fpl.db → xp_scores table.")
    else:
        print("[WARN] Nothing to rank — no upcoming GWs found.")

    conn.close()
    print("\n  Run engine/test_model.py to validate the results.")
    print("=" * 60)


if __name__ == "__main__":
    main()
