"""
api_server.py  —  Local REST API for FPL Assistant
----------------------------------------------------
Serves data from db/fpl.db as JSON over HTTP on http://localhost:8000.
Uses only Python built-ins: http.server, sqlite3, json, os, sys.

Endpoints:
  GET /squad      → my 15 squad players with xP scores + 6-GW forecast
  GET /players    → all players (for the Transfer Planner tab)
  GET /recommend  → captain pick, transfer suggestions, XI advice
  GET /briefing   → today's daily briefing text + news pills
  GET /status     → last data refresh time + table row counts

The server adds CORS headers so the Vite dev server (port 8080) can
talk to it freely without any proxy configuration needed.

Run from the project root:
    python3 engine/api_server.py
"""

import sys
import os
import json
import sqlite3
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Allow importing explainer.py from the same engine/ folder
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from explainer       import explain_player
from validate_squad  import validate_squad, load_squad_from_db
from fpl_rules       import (
    hit_cost, is_hit_worthwhile, transfer_summary,
    HIT_COST_POINTS, MIN_NET_XP_FOR_HIT, FREE_TRANSFERS_PER_GW,
    chip_advice, CHIP_WILDCARD, CHIP_FREE_HIT,
    CHIP_TRIPLE_CAPTAIN, CHIP_BENCH_BOOST,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT     = 8000
HOST     = "localhost"
DB_PATH  = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")

# The FPL entry ID whose squad this server always serves.
# Every query that reads my_picks filters by this ID so no other
# account's data can ever leak into the responses.
ENTRY_ID  = 140222   # Tiki Taka CF
FPL_ENTRY = f"https://fantasy.premierleague.com/api/entry/{ENTRY_ID}"

# ---------------------------------------------------------------------------
# FPL live-API helper with in-memory cache (5-minute TTL)
# ---------------------------------------------------------------------------

_fpl_cache: dict = {}

def _fetch_fpl_live(url: str, ttl: int = 300) -> dict:
    """Fetch URL from FPL API with 5-min in-memory cache. Uses stdlib only."""
    now = time.time()
    if url in _fpl_cache and now - _fpl_cache[url]["ts"] < ttl:
        return _fpl_cache[url]["data"]
    req = urllib.request.Request(url, headers={"User-Agent": "FPL-Assistant/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    _fpl_cache[url] = {"ts": now, "data": data}
    return data

# FPL element_type → position label used by the React UI
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# FPL status code → fitness label used by the React UI
FITNESS_MAP = {
    "a": "fit",    # available
    "d": "doubt",  # doubtful
    "i": "out",    # injured
    "s": "out",    # suspended
    "u": "fit",    # rotation risk but technically available
    "n": "out",    # not registered
}


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------

def get_conn():
    """Open a read-only connection to fpl.db with dict-style row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_next_gw(conn):
    """Return the id of the next unfinished gameweek, or None."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM gameweeks WHERE finished=0 ORDER BY id LIMIT 1")
    row = cur.fetchone()
    return row["id"] if row else None


def get_upcoming_gw_ids(conn, n=6):
    """Return the ids of the next n unfinished gameweeks."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM gameweeks WHERE finished=0 ORDER BY id LIMIT ?", (n,)
    )
    return [r["id"] for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Qualitative signal helpers — used by handle_recommend
# ---------------------------------------------------------------------------

# FPL-specific sources score higher than general football press
_SIGNAL_WEIGHTS = {
    "LetsTalkFPL (YouTube)":         3,
    "FPL Mate (YouTube)":            3,
    "FPL General (YouTube)":         3,
    "FPL Pod (Official PL Podcast)": 2,
    "BBC Sport Football":            1,
    "The Guardian Football":         1,
}

def get_buzz_scores(conn, hours=72):
    """
    Return {player_id: weighted_buzz_score} from qualitative_signals.
    FPL-specialist sources count 2–3× more than general news.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT player_id, source_name, COUNT(*) AS cnt
        FROM qualitative_signals
        WHERE fetched_at > datetime('now', ?)
          AND player_id IS NOT NULL
        GROUP BY player_id, source_name
    """, (f"-{hours} hours",))
    scores = {}
    for row in cur.fetchall():
        w = _SIGNAL_WEIGHTS.get(row["source_name"], 1)
        scores[row["player_id"]] = scores.get(row["player_id"], 0) + row["cnt"] * w
    return scores


def get_signal_summary(conn, player_id, hours=72):
    """
    Return a short string like: 'LetsTalkFPL: "Salah captain vs..." · FPL Pod: "Is Salah..."'
    Prioritises FPL-specialist sources. Returns None if no signals exist.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT source_name, signal_text
        FROM qualitative_signals
        WHERE player_id = ?
          AND fetched_at > datetime('now', ?)
          AND signal_text IS NOT NULL
        ORDER BY
            CASE source_name
                WHEN 'LetsTalkFPL (YouTube)'         THEN 1
                WHEN 'FPL Mate (YouTube)'            THEN 2
                WHEN 'FPL General (YouTube)'         THEN 3
                WHEN 'FPL Pod (Official PL Podcast)' THEN 4
                ELSE 5
            END, id DESC
        LIMIT 6
    """, (player_id, f"-{hours} hours"))
    rows = cur.fetchall()
    if not rows:
        return None
    seen, parts = set(), []
    for r in rows:
        src = r["source_name"]
        if src in seen:
            continue
        seen.add(src)
        short = (src.replace(" (YouTube)", "")
                    .replace(" (Official PL Podcast)", "")
                    .replace("The ", ""))
        headline = (r["signal_text"] or "")[:90].rstrip()
        if headline:
            parts.append(f'{short}: "{headline}"')
        if len(parts) >= 3:
            break
    return " · ".join(parts) if parts else None


def get_official_fdr(conn, player_team_id, opponent_id, gameweek):
    """Return the official FPL difficulty (1-5) from the fixtures table."""
    if not player_team_id or not opponent_id or not gameweek:
        return 3
    cur = conn.cursor()
    cur.execute("""
        SELECT team_h, team_a, team_h_difficulty, team_a_difficulty
        FROM fixtures
        WHERE gameweek = ?
          AND ((team_h = ? AND team_a = ?) OR (team_a = ? AND team_h = ?))
        LIMIT 1
    """, (gameweek, player_team_id, opponent_id, player_team_id, opponent_id))
    row = cur.fetchone()
    if not row:
        return 3  # neutral fallback
    if row["team_h"] == player_team_id:
        return row["team_h_difficulty"] or 3
    return row["team_a_difficulty"] or 3


# ---------------------------------------------------------------------------
# Endpoint: GET /squad
# ---------------------------------------------------------------------------

def handle_squad(conn, gw=None):
    """
    Return my 15-player squad shaped to match the React Player interface:
      starters (positions 1-11) and bench (12-15), each with:
        id, name, shortName, position, team, xP, xPForecast[6],
        isCaptain, isViceCaptain, fitness, opponent, isHome, fdr

    If gw is a past GW: return historical picks with upcoming-GW xP.
    If gw is a future GW: return current picks with that future GW's xP (planning mode).
    If gw is None: return current picks with next-GW xP.
    """
    next_gw  = get_next_gw(conn)
    upcoming = get_upcoming_gw_ids(conn, 6)

    if not next_gw:
        return {"error": "No upcoming gameweeks found in DB."}

    cur = conn.cursor()
    is_historical = False
    is_planning   = False

    if gw is not None:
        # Determine if this GW is in the past or in the future
        cur.execute("SELECT MAX(id) AS last FROM gameweeks WHERE finished=1")
        last_finished = cur.fetchone()["last"] or 0

        if gw <= last_finished:
            # Historical GW — check we have picks in the DB
            cur.execute(
                "SELECT COUNT(*) AS n FROM my_picks WHERE gameweek=? AND (entry_id=? OR entry_id IS NULL)",
                (gw, ENTRY_ID),
            )
            if cur.fetchone()["n"] == 0:
                return {"error": "historical picks not in DB"}
            picks_where  = "mp.gameweek = ? AND (mp.entry_id = ? OR mp.entry_id IS NULL)"
            picks_params = (next_gw, gw, ENTRY_ID)   # xp join uses next_gw
            xp_gw        = next_gw
            is_historical = True
        else:
            # Future GW — use most-recent stored picks, but xP for the target GW
            picks_where  = ("mp.gameweek = (SELECT MAX(gameweek) FROM my_picks "
                            "WHERE entry_id = ? OR entry_id IS NULL) "
                            "AND (mp.entry_id = ? OR mp.entry_id IS NULL)")
            picks_params = (gw, ENTRY_ID, ENTRY_ID)   # xp join uses future gw
            xp_gw        = gw
            is_planning  = True
    else:
        picks_where  = ("mp.gameweek = (SELECT MAX(gameweek) FROM my_picks "
                        "WHERE entry_id = ? OR entry_id IS NULL) "
                        "AND (mp.entry_id = ? OR mp.entry_id IS NULL)")
        picks_params = (next_gw, ENTRY_ID, ENTRY_ID)
        xp_gw        = next_gw

    # Join picks → players → teams → xp_scores in one query
    cur.execute(f"""
        SELECT
            mp.player_id,
            mp.position        AS squad_pos,
            mp.is_captain,
            mp.is_vice_captain,
            p.first_name || ' ' || p.second_name AS full_name,
            p.web_name,
            p.element_type,
            p.status,
            p.team_id,
            t.short_name       AS team,
            x.xp_score,
            x.has_fixture,
            x.is_home,
            x.opponent_id,
            opp.short_name     AS opponent
        FROM my_picks mp
        JOIN players   p   ON mp.player_id    = p.id
        JOIN teams     t   ON p.team_id        = t.id
        LEFT JOIN xp_scores x   ON x.player_id = mp.player_id
                                AND x.gameweek  = ?
        LEFT JOIN teams opp     ON x.opponent_id = opp.id
        WHERE {picks_where}
        ORDER BY mp.position
    """, picks_params)

    picks = cur.fetchall()

    def xp_forecast(player_id):
        """Return a 6-element array of xP values for upcoming GWs."""
        if not upcoming:
            return [0.0] * 6
        ph = ",".join("?" for _ in upcoming)
        cur2 = conn.cursor()
        cur2.execute(
            f"SELECT xp_score FROM xp_scores "
            f"WHERE player_id=? AND gameweek IN ({ph}) ORDER BY gameweek",
            [player_id] + upcoming,
        )
        scores = [round(r["xp_score"] or 0, 2) for r in cur2.fetchall()]
        while len(scores) < 6:
            scores.append(0.0)
        return scores[:6]

    starters, bench = [], []

    for p in picks:
        fdr = None
        if p["has_fixture"] and p["team_id"] and p["opponent_id"]:
            fdr = get_official_fdr(conn, p["team_id"], p["opponent_id"], xp_gw)

        player = {
            "id":            p["player_id"],
            "name":          p["full_name"],
            "shortName":     p["web_name"],
            "position":      POSITION_MAP.get(p["element_type"], "MID"),
            "team":          p["team"],
            "xP":            round(p["xp_score"] or 0, 2),
            "xPForecast":    xp_forecast(p["player_id"]),
            "isCaptain":     bool(p["is_captain"]),
            "isViceCaptain": bool(p["is_vice_captain"]),
            "fitness":       FITNESS_MAP.get(p["status"], "fit"),
            "opponent":      p["opponent"],
            "isHome":        bool(p["is_home"]) if p["is_home"] is not None else None,
            "fdr":           fdr,
        }
        if p["squad_pos"] <= 11:
            starters.append(player)
        else:
            bench.append(player)

    result = {"gameweek": gw if gw is not None else next_gw, "starters": starters, "bench": bench}

    if is_historical:
        try:
            history_data = _fetch_fpl_live(f"{FPL_ENTRY}/history/")
            gw_entry = next(
                (e for e in history_data.get("current", []) if e["event"] == gw),
                None,
            )
            if gw_entry:
                result["points"] = gw_entry["points"]
        except Exception:
            pass
        result["isHistorical"] = True
    elif is_planning:
        result["isPlanning"] = True

    return result


# ---------------------------------------------------------------------------
# Endpoint: GET /player  (query: ?id=<player_id>)
# ---------------------------------------------------------------------------

def handle_player(conn, player_id=None):
    """
    Return detailed stats for a single player including:
    - All season stats (goals, assists, CS, minutes, ICT, etc.)
    - Upcoming fixtures with FDR computed from xp_scores factors
    - GW-by-GW ownership trend from FPL element-summary API
    """
    if not player_id:
        return {"error": "Missing ?id= parameter"}

    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, t.short_name AS team_short, t.name AS team_name
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.id = ?
    """, (player_id,))
    row = cur.fetchone()
    if not row:
        return {"error": f"Player {player_id} not found"}

    # Upcoming fixtures from xp_scores (already has opponent info)
    cur.execute("""
        SELECT
            x.gameweek,
            x.opponent_id,
            opp.short_name   AS opponent,
            x.is_home,
            x.has_fixture
        FROM xp_scores x
        LEFT JOIN teams opp ON x.opponent_id = opp.id
        WHERE x.player_id = ?
        ORDER BY x.gameweek
        LIMIT 6
    """, (player_id,))
    xp_rows = cur.fetchall()

    fixtures = []
    for x in xp_rows:
        if x["has_fixture"]:
            fdr = get_official_fdr(conn, row["team_id"], x["opponent_id"], x["gameweek"])
            fixtures.append({
                "gw":       x["gameweek"],
                "opponent": x["opponent"] or "TBC",
                "home":     bool(x["is_home"]),
                "fdr":      fdr,
            })

    # Live ownership trend from FPL element-summary API
    ownership_trend = []
    try:
        summary = _fetch_fpl_live(
            f"https://fantasy.premierleague.com/api/element-summary/{player_id}/",
            ttl=3600,  # 1 hour cache — this data doesn't change often
        )
        # Last 10 GWs of ownership data
        history = summary.get("history", [])[-10:]
        ownership_trend = [
            {"gw": f"GW{h['round']}", "pct": round(h["selected"] / 1000, 1)}
            for h in history
            if h.get("selected") is not None
        ]
    except Exception:
        pass

    return {
        "id":               row["id"],
        "name":             row["first_name"] + " " + row["second_name"],
        "shortName":        row["web_name"],
        "team":             row["team_short"],
        "price":            round((row["now_cost"] or 0) / 10, 1),
        "goalsScored":      row["goals_scored"] or 0,
        "assists":          row["assists"] or 0,
        "cleanSheets":      row["clean_sheets"] or 0,
        "yellowCards":      row["yellow_cards"] or 0,
        "redCards":         row["red_cards"] or 0,
        "bonus":            row["bonus"] or 0,
        "minutes":          row["minutes"] or 0,
        "ictIndex":         float(row["ict_index"] or 0),
        "selectedByPct":    float(row["selected_by_percent"] or 0),
        "form":             float(row["form"] or 0),
        "pointsPerGame":    float(row["points_per_game"] or 0),
        "totalPoints":      row["total_points"] or 0,
        "fixtures":         fixtures,
        "ownershipTrend":   ownership_trend,
    }


# ---------------------------------------------------------------------------
# Endpoint: GET /history
# ---------------------------------------------------------------------------

def handle_history(conn):
    """
    Return the season GW-by-GW history from the FPL API.
    Response: { history: [{gw, points, totalPoints, overallRank}], currentGW: N }
    """
    data = _fetch_fpl_live(f"{FPL_ENTRY}/history/")
    history = [
        {
            "gw":           e["event"],
            "points":       e["points"],
            "totalPoints":  e["total_points"],
            "overallRank":  e["overall_rank"],
        }
        for e in data.get("current", [])
    ]
    current_gw = history[-1]["gw"] if history else 0
    return {"history": history, "currentGW": current_gw}


# ---------------------------------------------------------------------------
# Endpoint: GET /standings
# ---------------------------------------------------------------------------

def handle_standings(conn):
    """
    Return overall rank, Sweden country rank, and all classic/private leagues.
    Response: { totalPoints, overallRank, swedenRank, leagues: [...] }
    """
    data = _fetch_fpl_live(f"{FPL_ENTRY}/")

    total_points  = data.get("summary_overall_points", 0)
    overall_rank  = data.get("summary_overall_rank", 0)

    sweden_rank = None
    leagues     = []

    for league in data.get("leagues", {}).get("classic", []):
        ltype      = league.get("league_type", "")
        name       = league.get("name", "")
        short_name = league.get("short_name", "")

        # Sweden country league
        if ltype == "s" and (
            "sweden" in name.lower() or "country-" in short_name.lower()
        ):
            sweden_rank = league.get("entry_rank")
            continue

        # Private / user classic mini-leagues
        if ltype in ("x", "c"):
            leagues.append({
                "id":       league.get("id"),
                "name":     name,
                "rank":     league.get("entry_rank"),
                "lastRank": league.get("entry_last_rank"),
            })

    return {
        "totalPoints": total_points,
        "overallRank": overall_rank,
        "swedenRank":  sweden_rank,
        "leagues":     leagues,
    }


# ---------------------------------------------------------------------------
# Endpoint: GET /players
# ---------------------------------------------------------------------------

def handle_players(conn):
    """
    Return up to 200 available players shaped to match the React PoolPlayer
    interface used by the Transfer Planner tab:
      id, name, team, position, price, xP, form, fitness, selectedPct, last5
    """
    next_gw  = get_next_gw(conn)
    upcoming = get_upcoming_gw_ids(conn, 5)

    # Approximate games played (for form = PPG calculation)
    cur = conn.cursor()
    cur.execute("""
        SELECT AVG(cnt) AS avg_games FROM (
            SELECT COUNT(*) AS cnt FROM fixtures
            WHERE finished=1 GROUP BY team_h
        )
    """)
    row = cur.fetchone()
    games_played = float(row["avg_games"] or 29)

    cur.execute("""
        SELECT
            p.id, p.web_name AS name,
            p.element_type, p.now_cost, p.total_points, p.status,
            t.short_name AS team,
            x.xp_score
        FROM players p
        JOIN teams t ON p.team_id = t.id
        LEFT JOIN xp_scores x ON x.player_id = p.id AND x.gameweek = ?
        WHERE p.status != 'u'          -- exclude unavailable rotation players
        ORDER BY x.xp_score DESC
        LIMIT 200
    """, (next_gw,))

    rows = cur.fetchall()
    players = []

    for r in rows:
        # last5 = xP values for the next 5 GWs (acts as a recent-form sparkline)
        last5 = []
        if upcoming:
            ph = ",".join("?" for _ in upcoming)
            cur2 = conn.cursor()
            cur2.execute(
                f"SELECT xp_score FROM xp_scores "
                f"WHERE player_id=? AND gameweek IN ({ph}) ORDER BY gameweek",
                [r["id"]] + upcoming,
            )
            last5 = [round(x["xp_score"] or 0, 1) for x in cur2.fetchall()]
        while len(last5) < 5:
            last5.append(0.0)

        players.append({
            "id":          r["id"],
            "name":        r["name"],
            "team":        r["team"],
            "position":    POSITION_MAP.get(r["element_type"], "MID"),
            "price":       round((r["now_cost"] or 0) / 10, 1),
            "xP":          round(r["xp_score"] or 0, 2),
            "form":        round((r["total_points"] or 0) / games_played, 1),
            "fitness":     FITNESS_MAP.get(r["status"], "fit"),
            "selectedPct": 0.0,   # not stored in our DB — future enhancement
            "last5":       last5,
        })

    return {"players": players}


# ---------------------------------------------------------------------------
# Endpoint: GET /recommend
# ---------------------------------------------------------------------------

def handle_recommend(conn):
    """
    Returns AI recommendations from the ai_recommendations table if available
    for the current GW, otherwise falls back to heuristic recommendations.
    """
    next_gw = get_next_gw(conn)
    if not next_gw:
        return {"recommendations": []}

    # --- Try AI recommendations first --------------------------------------
    ai = None
    try:
        cur0 = conn.cursor()
        cur0.execute("""
            SELECT transfer_in, transfer_out, captain, starting_xi, daily_briefing
            FROM ai_recommendations
            WHERE gameweek = ?
        """, (next_gw,))
        ai = cur0.fetchone()
    except Exception:
        pass  # table doesn't exist yet — fall through to heuristic
    if ai and ai["captain"]:
        import json as _json
        ti   = _json.loads(ai["transfer_in"]  or "{}")
        to_  = _json.loads(ai["transfer_out"] or "{}")
        cap  = _json.loads(ai["captain"]      or "{}")
        xi   = _json.loads(ai["starting_xi"]  or "{}")
        recs = []
        if cap.get("player"):
            conf = cap.get("confidence_pct", "")
            conf_label = f" ({conf}% confidence)" if conf else ""
            recs.append({
                "id": 1, "type": "captain",
                "title":     f"Captain Pick: {cap['player']}{conf_label}",
                "summary":   cap.get("reason", ""),
                "reasoning": cap.get("reason", ""),
                "positive":  True,
            })
        if ti.get("player"):
            recs.append({
                "id": 2, "type": "transfer_in",
                "title":     f"Transfer In: {ti['player']}",
                "summary":   ti.get("reason", ""),
                "reasoning": ti.get("reason", ""),
                "positive":  True,
            })
        if to_.get("player"):
            recs.append({
                "id": 3, "type": "transfer_out",
                "title":     f"Consider Selling: {to_['player']}",
                "summary":   to_.get("reason", ""),
                "reasoning": to_.get("reason", ""),
                "positive":  False,
            })
        if xi.get("reasoning"):
            players    = xi.get("players", [])
            xi_summary = xi["reasoning"]
            if players:
                xi_summary = f"Starters: {', '.join(players[:4])}… | {xi['reasoning']}"
            recs.append({
                "id": 4, "type": "starting_xi",
                "title":     "Recommended XI",
                "summary":   xi_summary,
                "reasoning": xi["reasoning"],
                "positive":  True,
            })
        if ai["daily_briefing"]:
            recs.append({
                "id": 5, "type": "community_buzz",
                "title":     "AI Daily Briefing",
                "summary":   ai["daily_briefing"],
                "reasoning": ai["daily_briefing"],
                "positive":  True,
            })
        return {"recommendations": recs}

    # --- Fallback: heuristic recommendations --------------------------------

    cur = conn.cursor()
    cur.execute("""
        SELECT
            mp.player_id  AS id,
            mp.position   AS squad_pos,
            mp.is_captain,
            p.web_name    AS short_name,
            p.first_name || ' ' || p.second_name AS full_name,
            p.element_type, p.status,
            t.short_name  AS team,
            x.xp_score    AS xp,
            x.has_fixture,
            x.is_home,
            x.attack_factor, x.def_weakness,
            x.form_factor, x.minutes_prob,
            opp.short_name AS opponent
        FROM my_picks mp
        JOIN players   p   ON mp.player_id = p.id
        JOIN teams     t   ON p.team_id     = t.id
        LEFT JOIN xp_scores x   ON x.player_id=mp.player_id AND x.gameweek=?
        LEFT JOIN teams opp     ON x.opponent_id=opp.id
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks
                             WHERE entry_id = ? OR entry_id IS NULL)
          AND (mp.entry_id = ? OR mp.entry_id IS NULL)
        ORDER BY mp.position
    """, (next_gw, ENTRY_ID, ENTRY_ID))

    squad    = [dict(r) for r in cur.fetchall()]
    starters = [p for p in squad if p["squad_pos"] <= 11]
    bench    = [p for p in squad if p["squad_pos"] > 11]

    # ---- Validate current squad before making any recommendations ----
    # Convert to the format validate_squad() expects.
    squad_for_validation = [
        {
            "name":      p["short_name"],
            "position":  p["element_type"],
            "team":      p["team"],
            "squad_pos": p["squad_pos"],
        }
        for p in squad
    ]
    squad_violations = validate_squad(squad_for_validation)

    starters_by_xp = sorted(starters, key=lambda p: p["xp"] or 0, reverse=True)
    bench_by_xp    = sorted(bench,    key=lambda p: p["xp"] or 0, reverse=True)

    recs      = []
    squad_ids = {p["id"] for p in squad}

    # ---- Load community buzz scores for the whole squad --------------------
    buzz = get_buzz_scores(conn)

    # ---- 1. Captain --------------------------------------------------------
    cap_picks = [p for p in starters_by_xp if p.get("has_fixture")]
    if cap_picks:
        cap   = cap_picks[0]
        venue = "at home" if cap.get("is_home") else "away"
        opp   = cap.get("opponent") or "their opponent"
        cap_buzz    = buzz.get(cap["id"], 0)
        cap_signals = get_signal_summary(conn, cap["id"])
        buzz_note   = ""
        if cap_buzz >= 6:
            buzz_note = f" The FPL community is strongly backing this pick ({cap_buzz} buzz score across multiple sources)."
        elif cap_buzz >= 2:
            buzz_note = f" Also attracting attention in the FPL community this week."
        reasoning = explain_player(cap["id"], gameweek=next_gw)
        if cap_signals:
            reasoning += f"\n\nCommunity signals: {cap_signals}"
        if buzz_note:
            reasoning += buzz_note
        recs.append({
            "id":       1,
            "type":     "captain",
            "title":    f"Captain Pick: {cap['short_name']}",
            "summary":  (f"Highest xP in your squad ({cap['xp']:.1f}) — "
                         f"playing {venue} vs {opp}."
                         + (f" 📡 {cap_buzz} community buzz." if cap_buzz >= 2 else "")),
            "reasoning": reasoning,
            "positive": True,
        })

    # ---- 2. Transfer Out ---------------------------------------------------
    # Priority: injured/suspended > blank GW > lowest xP
    injured = [p for p in starters if p["status"] in ("i", "s", "n")]
    blanks  = [p for p in starters if not p.get("has_fixture") and p["status"] == "a"]
    worst   = sorted(starters, key=lambda p: p["xp"] or 0)

    sell = None
    why  = ""
    if injured:
        sell = injured[0]
        why  = "currently injured or suspended"
    elif blanks:
        sell = blanks[0]
        why  = f"has no fixture in GW{next_gw} (blank week)"
    elif worst:
        sell = worst[0]
        why  = f"has the lowest xP in your starting XI ({sell['xp']:.1f})"  # type: ignore[index]

    if sell:
        sell_buzz    = buzz.get(sell["id"], 0)
        sell_signals = get_signal_summary(conn, sell["id"])
        sell_reasoning = explain_player(sell["id"], gameweek=next_gw)
        if sell_signals:
            sell_reasoning += f"\n\nCommunity signals: {sell_signals}"
        sell_buzz_note = ""
        if sell_buzz >= 4:
            sell_buzz_note = f" ({sell_buzz} community mentions may reflect injury/form concerns.)"
        recs.append({
            "id":       2,
            "type":     "transfer_out",
            "title":    f"Consider Selling: {sell['short_name']}",
            "summary":  f"{sell['short_name']} {why}." + sell_buzz_note,
            "reasoning": sell_reasoning,
            "positive": False,
        })

        # ---- 3. Transfer In ------------------------------------------------
        # Best non-squad player at the same position with a fixture
        # Boost candidates that have community buzz
        target_pos = sell["element_type"]
        cur.execute("""
            SELECT p.id, p.web_name, p.element_type, t.short_name AS team,
                   x.xp_score, p.now_cost, p.status
            FROM players p
            JOIN teams t ON p.team_id = t.id
            LEFT JOIN xp_scores x ON x.player_id=p.id AND x.gameweek=?
            WHERE p.element_type=? AND p.status='a' AND x.has_fixture=1
            ORDER BY x.xp_score DESC
            LIMIT 50
        """, (next_gw, target_pos))

        candidates = [r for r in cur.fetchall() if r["id"] not in squad_ids]
        if candidates:
            # Prefer candidates with both high xP AND community buzz
            def candidate_score(c):
                return (c["xp_score"] or 0) + buzz.get(c["id"], 0) * 0.3
            candidates_sorted = sorted(candidates, key=candidate_score, reverse=True)
            best        = candidates_sorted[0]
            price       = round((best["now_cost"] or 0) / 10, 1)
            best_buzz   = buzz.get(best["id"], 0)
            best_signals = get_signal_summary(conn, best["id"])
            best_reasoning = explain_player(best["id"], gameweek=next_gw)
            if best_signals:
                best_reasoning += f"\n\nCommunity signals: {best_signals}"
            buzz_summary = f" 📡 {best_buzz} community buzz." if best_buzz >= 2 else ""
            recs.append({
                "id":        3,
                "type":      "transfer_in",
                "title":     f"Transfer In: {best['web_name']} ({best['team']})",
                "summary":   (f"Top xP at the same position — "
                              f"{best['xp_score']:.1f} xP, £{price}m.{buzz_summary}"),
                "reasoning": best_reasoning,
                "positive":  True,
            })

    # ---- 4. Starting XI swap -----------------------------------------------
    for bp in bench_by_xp:
        for sp in sorted(starters, key=lambda p: p["xp"] or 0):
            if (
                (bp.get("xp") or 0) > (sp.get("xp") or 0) + 0.5
                and bp.get("has_fixture")
                and not sp.get("has_fixture")
            ):
                recs.append({
                    "id":       4,
                    "type":     "starting_xi",
                    "title":    f"Start {bp['short_name']} over {sp['short_name']}",
                    "summary":  (f"{bp['short_name']} projects {bp['xp']:.1f} xP vs "
                                 f"{sp['short_name']}'s {sp['xp']:.1f} xP — "
                                 f"consider the swap before the deadline."),
                    "reasoning": (f"{bp['full_name']} has a GW{next_gw} fixture while "
                                  f"{sp['full_name']} has a blank. "
                                  f"Check formation legality before swapping."),
                    "positive":  True,
                })
                break
        if len(recs) >= 4:
            break

    # ---- 5. Community Buzz — most-talked-about non-squad player -----------
    # Find the highest-buzz player NOT in the squad with good upcoming xP
    cur.execute("""
        SELECT p.id, p.web_name, p.element_type, t.short_name AS team,
               x.xp_score, p.now_cost, p.status
        FROM players p
        JOIN teams t ON p.team_id = t.id
        LEFT JOIN xp_scores x ON x.player_id=p.id AND x.gameweek=?
        WHERE p.status = 'a' AND x.has_fixture = 1
    """, (next_gw,))
    all_players = {r["id"]: dict(r) for r in cur.fetchall()}

    # Score = buzz × 2 + xP (community signal is the primary driver here)
    buzz_candidates = [
        (pid, all_players[pid], score)
        for pid, score in buzz.items()
        if pid not in squad_ids and pid in all_players and score >= 3
    ]
    buzz_candidates.sort(key=lambda x: x[2] * 2 + (x[1]["xp_score"] or 0), reverse=True)

    if buzz_candidates:
        bpid, bplayer, bscore = buzz_candidates[0]
        bprice   = round((bplayer["now_cost"] or 0) / 10, 1)
        bsignals = get_signal_summary(conn, bpid)
        pos_name = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(bplayer["element_type"], "")
        if bsignals:
            recs.append({
                "id":       5,
                "type":     "community_buzz",
                "title":    f"Community Buzz: {bplayer['web_name']} ({bplayer['team']})",
                "summary":  (f"Trending across FPL podcasts & channels this week — "
                             f"{pos_name}, £{bprice}m, {bplayer['xp_score']:.1f} xP next GW. "
                             f"Buzz score: {bscore}."),
                "reasoning": (f"Multiple FPL sources are discussing {bplayer['web_name']} "
                              f"({bplayer['team']}) this week.\n\n{bsignals}"),
                "positive": True,
            })

    # ---- Transfer rule summary (assumes 1 free transfer available) ----
    # In future this could be fetched from the FPL API (entry/{id}/transfers/)
    transfers_info = transfer_summary(
        free_transfers=FREE_TRANSFERS_PER_GW,
        transfers_planned=1,   # one suggestion per call
    )

    return {
        "recommendations":  recs,
        "squad_violations": squad_violations,   # empty list = squad is legal
        "transfers":        transfers_info,
    }


# ---------------------------------------------------------------------------
# Endpoint: GET /briefing
# ---------------------------------------------------------------------------

def handle_briefing(conn):
    """
    Compose a comprehensive daily briefing from squad data + qualitative signals.
    Returns:
      date, gameweek, summary, newsPills, deadlineTime,
      communityHeadlines, hotPlayers, squadWatch
    """
    next_gw  = get_next_gw(conn)
    today    = datetime.now().strftime("%A, %d %B %Y")
    cur      = conn.cursor()

    # Deadline for next GW
    cur.execute("SELECT deadline_time FROM gameweeks WHERE id=?", (next_gw,))
    gw_row   = cur.fetchone()
    deadline = gw_row["deadline_time"] if gw_row else None

    # Load squad with xP
    cur.execute("""
        SELECT
            p.id AS player_id,
            p.web_name, p.element_type, p.status,
            t.short_name AS team,
            x.xp_score, x.has_fixture, x.is_home,
            opp.short_name AS opponent,
            mp.is_captain, mp.position AS squad_pos
        FROM my_picks mp
        JOIN players   p   ON mp.player_id = p.id
        JOIN teams     t   ON p.team_id     = t.id
        LEFT JOIN xp_scores x  ON x.player_id=mp.player_id AND x.gameweek=?
        LEFT JOIN teams opp    ON x.opponent_id=opp.id
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks
                             WHERE entry_id = ? OR entry_id IS NULL)
          AND (mp.entry_id = ? OR mp.entry_id IS NULL)
        ORDER BY x.xp_score DESC
    """, (next_gw, ENTRY_ID, ENTRY_ID))
    squad     = [dict(r) for r in cur.fetchall()]
    squad_ids = {p["player_id"] for p in squad}

    # ── Summary paragraph ────────────────────────────────────────────────
    captain = next((p for p in squad if p["is_captain"]), None)
    top     = squad[0] if squad else None
    injured = [p for p in squad if p["status"] in ("i", "s")]
    blanks  = [p for p in squad if not p.get("has_fixture") and p["status"] == "a"]
    doubts  = [p for p in squad if p["status"] == "d"]

    lines = []
    if top:
        venue = "at home" if top.get("is_home") else "away"
        opp   = top.get("opponent") or "their opponent"
        lines.append(
            f"GW{next_gw} outlook: your standout player is {top['web_name']} "
            f"({top['xp_score']:.1f} xP), playing {venue} against {opp}."
        )
    if captain and captain["web_name"] != (top["web_name"] if top else ""):
        lines.append(
            f"Your captain {captain['web_name']} carries the armband "
            f"with {captain['xp_score']:.1f} projected points."
        )
    elif captain:
        lines.append(
            f"{captain['web_name']} wears the armband as your top pick ({captain['xp_score']:.1f} xP)."
        )
    if injured:
        names = ", ".join(p["web_name"] for p in injured)
        lines.append(f"Injury/suspension concern: {names} — check fitness before the deadline.")
    if doubts:
        names = ", ".join(p["web_name"] for p in doubts[:3])
        lines.append(f"Doubtful to play: {names}.")
    if blanks:
        names = ", ".join(p["web_name"] for p in blanks[:3])
        lines.append(f"Blank GW alert: {names} have no fixture this week.")
    if not injured and not blanks and not doubts:
        lines.append("Good news: your full squad has fixtures and no injury concerns this week.")

    # Top 5 starters by xP for context
    starters_by_xp = sorted(
        [p for p in squad if p["squad_pos"] <= 11 and p.get("has_fixture")],
        key=lambda p: p["xp_score"] or 0, reverse=True
    )
    if len(starters_by_xp) >= 3:
        top3 = ", ".join(
            f"{p['web_name']} ({p['xp_score']:.1f})" for p in starters_by_xp[:3]
        )
        lines.append(f"Top projected starters: {top3}.")

    summary = " ".join(lines)

    # ── News pills ───────────────────────────────────────────────────────
    pill_status_map = {"i": "injury", "d": "flagged", "s": "suspended"}
    pill_text_map   = {"i": "Injured", "d": "Doubtful", "s": "Suspended"}
    news_pills = [
        {"player": p["web_name"],
         "status": pill_status_map[p["status"]],
         "text":   pill_text_map[p["status"]]}
        for p in squad if p["status"] in pill_status_map
    ]

    # ── Community headlines ───────────────────────────────────────────────
    # Most recent unique headlines from each source (last 48 h, FPL sources first)
    cur.execute("""
        SELECT signal_text, source_name
        FROM qualitative_signals
        WHERE fetched_at > datetime('now', '-48 hours')
          AND signal_text IS NOT NULL AND signal_text != ''
        GROUP BY signal_text, source_name
        ORDER BY
            CASE source_name
                WHEN 'LetsTalkFPL (YouTube)'         THEN 1
                WHEN 'FPL Mate (YouTube)'            THEN 2
                WHEN 'FPL General (YouTube)'         THEN 3
                WHEN 'FPL Pod (Official PL Podcast)' THEN 4
                ELSE 5
            END,
            MAX(fetched_at) DESC
        LIMIT 12
    """)
    seen_headlines = set()
    community_headlines = []
    for row in cur.fetchall():
        h = (row["signal_text"] or "").strip()[:120]
        if h and h not in seen_headlines:
            seen_headlines.add(h)
            community_headlines.append({
                "source":   row["source_name"],
                "headline": h,
            })
        if len(community_headlines) >= 8:
            break

    # ── Hot players (non-squad, high community buzz) ─────────────────────
    buzz = get_buzz_scores(conn)
    non_squad_buzz = sorted(
        [(pid, score) for pid, score in buzz.items()
         if pid not in squad_ids and score >= 3],
        key=lambda x: x[1], reverse=True
    )[:6]

    hot_players = []
    for pid, score in non_squad_buzz:
        cur.execute("""
            SELECT p.web_name, t.short_name AS team, p.element_type, x.xp_score
            FROM players p
            JOIN teams t ON p.team_id = t.id
            LEFT JOIN xp_scores x ON x.player_id=p.id AND x.gameweek=?
            WHERE p.id=?
        """, (next_gw, pid))
        row = cur.fetchone()
        if not row:
            continue
        headline = get_signal_summary(conn, pid)
        hot_players.append({
            "id":       pid,
            "name":     row["web_name"],
            "team":     row["team"],
            "position": POSITION_MAP.get(row["element_type"], ""),
            "xP":       round(row["xp_score"] or 0, 1),
            "buzz":     score,
            "headline": headline,
        })

    # ── Squad watch (squad players mentioned in signals this week) ────────
    squad_watch = []
    for p in squad:
        score = buzz.get(p["player_id"], 0)
        if score < 1:
            continue
        summary_text = get_signal_summary(conn, p["player_id"])
        if not summary_text:
            continue
        squad_watch.append({
            "name":     p["web_name"],
            "team":     p["team"],
            "buzz":     score,
            "headline": summary_text,
        })
    squad_watch.sort(key=lambda x: x["buzz"], reverse=True)

    return {
        "date":               today,
        "gameweek":           next_gw,
        "summary":            summary,
        "newsPills":          news_pills,
        "deadlineTime":       deadline,
        "communityHeadlines": community_headlines,
        "hotPlayers":         hot_players,
        "squadWatch":         squad_watch[:5],
    }


# ---------------------------------------------------------------------------
# Endpoint: GET /status
# ---------------------------------------------------------------------------

def handle_status(conn):
    """
    Return DB freshness: when was the model last run, and do all tables
    have data?  Shapes to match the React DataSource interface.
    """
    cur = conn.cursor()

    # The model writes a UTC timestamp into xp_scores.computed_at
    cur.execute("SELECT MAX(computed_at) AS last_run FROM xp_scores")
    row      = cur.fetchone()
    last_run = row["last_run"]

    # Human-readable relative time
    if last_run:
        try:
            dt   = datetime.fromisoformat(last_run)
            secs = int((datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds())
            if secs < 60:
                relative = f"{secs} seconds ago"
            elif secs < 3600:
                relative = f"{secs // 60} minutes ago"
            else:
                relative = f"{secs // 3600} hours ago"
        except Exception:
            relative = last_run or "unknown"
    else:
        relative = "Never (run engine/fetch_fpl.py)"

    # Check each table has at least one row
    checks = [
        ("FPL Official API (players & teams)", "SELECT COUNT(*) AS n FROM players"),
        ("Fixtures",                           "SELECT COUNT(*) AS n FROM fixtures"),
        ("My Squad Picks",                     "SELECT COUNT(*) AS n FROM my_picks"),
        ("xP Model Scores",                    "SELECT COUNT(*) AS n FROM xp_scores"),
    ]

    sources = []
    for name, sql in checks:
        cur.execute(sql)
        count = cur.fetchone()["n"]
        sources.append({
            "name":       name,
            "status":     "ok" if count > 0 else "warning",
            "lastUpdate": relative,
            "count":      count,
        })

    return {
        "lastRefresh":         last_run,
        "lastRefreshRelative": relative,
        "sources":             sources,
    }


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class FPLHandler(BaseHTTPRequestHandler):
    """Routes every GET request to the correct endpoint handler."""

    # Keep the terminal readable — print one line per request
    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "?"
        print(f"  [{status}] {self.command} {self.path}")

    def send_json(self, data, status=200):
        """Serialise data to JSON and write the HTTP response."""
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        # CORS headers — allow the Vite dev server (port 8080) to call us
        self.send_header("Content-Type",                 "application/json")
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length",               str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests from the browser."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed    = urlparse(self.path)
        path      = parsed.path
        qs_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Guard: DB must exist before we try anything
        if not os.path.exists(DB_PATH):
            self.send_json(
                {"error": "Database missing. Run engine/fetch_fpl.py first."}, 503
            )
            return

        # Route table
        routes = {
            "/squad":     handle_squad,
            "/players":   handle_players,
            "/recommend": handle_recommend,
            "/briefing":  handle_briefing,
            "/status":    handle_status,
            "/history":   handle_history,
            "/standings": handle_standings,
            "/player":    handle_player,
        }

        handler = routes.get(path)
        if handler is None:
            self.send_json(
                {"error": "Unknown endpoint",
                 "available": list(routes.keys())},
                404,
            )
            return

        try:
            conn   = get_conn()
            kwargs = {}
            if path == "/squad" and "gw" in qs_params:
                try:
                    kwargs["gw"] = int(qs_params["gw"])
                except ValueError:
                    pass
            elif path == "/player" and "id" in qs_params:
                try:
                    kwargs["player_id"] = int(qs_params["id"])
                except ValueError:
                    pass
            data = handler(conn, **kwargs)
            conn.close()
            self.send_json(data)
        except Exception as exc:
            import traceback
            print(f"  [ERROR] {exc}")
            traceback.print_exc()
            self.send_json({"error": str(exc)}, 500)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"  FPL Assistant — API Server")
    print(f"  http://{HOST}:{PORT}")
    print(f"  DB: {os.path.abspath(DB_PATH)}")
    print("=" * 60)
    for ep in ["/squad", "/players", "/recommend", "/briefing", "/status", "/history", "/standings", "/player?id=<id>"]:
        print(f"    http://{HOST}:{PORT}{ep}")
    print("\n  Press Ctrl+C to stop.\n")

    server = HTTPServer((HOST, PORT), FPLHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
