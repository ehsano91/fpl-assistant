"""
ai_recommend.py  —  AI-Powered FPL Recommendations
----------------------------------------------------
Reads your squad's xP scores and qualitative signals from db/fpl.db,
sends a structured prompt to Claude, and stores the AI's recommendations
back in the db under the `ai_recommendations` table.

What Claude produces:
  a) Best transfer in  + reasoning
  b) Best transfer out + reasoning
  c) Captain pick      + confidence % + reasoning
  d) Best starting XI  + bench order  + reasoning
  e) 3-sentence daily briefing paragraph

Requirements:
  • ANTHROPIC_API_KEY environment variable must be set
  • Run engine/fetch_fpl.py and engine/model.py first

Run from the project root:
    python3 engine/ai_recommend.py
"""

import sqlite3
import json
import os
import sys
from datetime import datetime

import anthropic

# Load ANTHROPIC_API_KEY from .env in project root if not already in environment
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_ENV_PATH) and not os.environ.get("ANTHROPIC_API_KEY"):
    with open(_ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH   = os.path.join(os.path.dirname(__file__), "..", "db", "fpl.db")
MODEL     = "claude-sonnet-4-6"     # latest Sonnet — best reasoning for FPL analysis
MAX_TOKENS = 2048

ENTRY_ID  = 140222   # Tiki Taka CF

# Positions we include from the non-squad pool (one per position type)
TOP_TARGETS_PER_POS = 5   # how many transfer-in candidates per position to show Claude


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_recommendations_table(conn):
    """Create the ai_recommendations table (safe to call repeatedly)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            gameweek           INTEGER,
            transfer_in        TEXT,    -- JSON: {player, reason}
            transfer_out       TEXT,    -- JSON: {player, reason}
            captain            TEXT,    -- JSON: {player, confidence_pct, reason}
            starting_xi        TEXT,    -- JSON: {players:[...], bench_order:[...], reasoning}
            daily_briefing     TEXT,    -- 3-sentence plain-English paragraph
            raw_response       TEXT,    -- full Claude output for debugging
            model              TEXT,    -- model name used
            created_at         TEXT,
            UNIQUE(gameweek) ON CONFLICT REPLACE
        )
    """)
    conn.commit()
    print("[DB]  ai_recommendations table ready.")


# ---------------------------------------------------------------------------
# Build the data payload for the prompt
# ---------------------------------------------------------------------------

def get_next_gw(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM gameweeks WHERE finished=0 ORDER BY id LIMIT 1")
    row = cur.fetchone()
    return row["id"] if row else None


def load_squad_with_xp(conn, next_gw):
    """Return the 15-player squad with xP and fixture info for the next GW."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            mp.position   AS squad_pos,
            mp.is_captain, mp.is_vice_captain,
            p.web_name    AS name,
            p.element_type, p.status, p.total_points,
            t.short_name  AS team,
            x.xp_score    AS xp,
            x.has_fixture,
            x.is_home,
            x.form_factor,
            x.cs_prob,
            opp.short_name AS opponent
        FROM my_picks mp
        JOIN players   p   ON mp.player_id = p.id
        JOIN teams     t   ON p.team_id     = t.id
        LEFT JOIN xp_scores x   ON x.player_id=mp.player_id AND x.gameweek=?
        LEFT JOIN teams opp     ON x.opponent_id=opp.id
        WHERE mp.gameweek = (SELECT MAX(gameweek) FROM my_picks)
        ORDER BY mp.position
    """, (next_gw,))
    return [dict(r) for r in cur.fetchall()]


def load_transfer_targets(conn, next_gw, squad_player_names):
    """
    Return the top non-squad players per position, sorted by xP.
    These are Claude's transfer-in candidates.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.web_name AS name, p.element_type, p.status,
            t.short_name AS team,
            x.xp_score AS xp,
            p.now_cost,
            opp.short_name AS opponent,
            x.has_fixture, x.is_home
        FROM players p
        JOIN teams t ON p.team_id = t.id
        LEFT JOIN xp_scores x   ON x.player_id=p.id AND x.gameweek=?
        LEFT JOIN teams opp     ON x.opponent_id=opp.id
        WHERE p.status = 'a'
          AND x.has_fixture = 1
          AND x.xp_score IS NOT NULL
        ORDER BY x.xp_score DESC
        LIMIT 100
    """, (next_gw,))

    squad_set = {n.lower() for n in squad_player_names}
    pos_labels = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

    by_pos = {1: [], 2: [], 3: [], 4: []}
    for r in cur.fetchall():
        if r["name"].lower() not in squad_set:
            pos = r["element_type"]
            if len(by_pos[pos]) < TOP_TARGETS_PER_POS:
                by_pos[pos].append({
                    "name":     r["name"],
                    "position": pos_labels[pos],
                    "team":     r["team"],
                    "xp":       round(r["xp"] or 0, 2),
                    "price":    round((r["now_cost"] or 0) / 10, 1),
                    "fixture":  f"vs {r['opponent']}({'H' if r['is_home'] else 'A'})" if r["has_fixture"] else "BLANK",
                })

    # Flatten into one list
    targets = []
    for pos_players in by_pos.values():
        targets.extend(pos_players)
    return sorted(targets, key=lambda p: p["xp"], reverse=True)


def load_qualitative_signals(conn, next_gw):
    """
    Load recent qualitative signals from the scraper.
    Returns a list of dicts: {player_name, source_name, signal_text, context}
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT player_name, source_name, signal_text, context
        FROM qualitative_signals
        ORDER BY fetched_at DESC
        LIMIT 30
    """)
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Build the prompt
# ---------------------------------------------------------------------------

POS_LABELS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS_LABELS = {
    "a": "Available", "d": "Doubtful", "i": "Injured",
    "s": "Suspended", "u": "Rotation risk", "n": "Ineligible",
}


def build_prompt(next_gw, squad, targets, signals):
    """
    Compose the structured prompt Claude will receive.
    Keeps the token count reasonable by being concise and factual.
    """

    # ---- Squad section ----
    squad_lines = []
    for p in squad:
        pos    = POS_LABELS.get(p["element_type"], "?")
        status = STATUS_LABELS.get(p["status"], "?")
        role   = " [C]" if p["is_captain"] else (" [V]" if p["is_vice_captain"] else "")
        fix    = f"vs {p['opponent']}({'H' if p['is_home'] else 'A'})" if p["has_fixture"] else "BLANK GW"
        slot   = "Starter" if p["squad_pos"] <= 11 else "Bench"
        squad_lines.append(
            f"  {slot:7} #{p['squad_pos']:2}  {p['name'] + role:<22} {pos:<4} "
            f"{p['team']:<5} xP={p['xp']:.2f}  {fix:<14} Status: {status}"
        )

    squad_block = "\n".join(squad_lines)

    # ---- Transfer targets section ----
    targets_lines = []
    for t in targets[:20]:   # limit to top 20 to keep prompt concise
        targets_lines.append(
            f"  {t['name']:<22} {t['position']:<4} {t['team']:<5} "
            f"xP={t['xp']:.2f}  £{t['price']}m  {t['fixture']}"
        )
    targets_block = "\n".join(targets_lines) if targets_lines else "  (none available)"

    # ---- Qualitative signals section ----
    if signals:
        sig_lines = []
        for s in signals[:15]:   # limit to 15 most recent signals
            # Truncate long context to keep the prompt short
            ctx = s["context"][:200].replace("\n", " ")
            sig_lines.append(f"  [{s['source_name']}] {s['player_name']}: {ctx}")
        signals_block = "\n".join(sig_lines)
    else:
        signals_block = "  (No qualitative signals available — only quantitative data used)"

    prompt = f"""You are an expert Fantasy Premier League (FPL) analyst.
Below is data for Tiki Taka CF ahead of Gameweek {next_gw}.
Use it to produce your best recommendations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT SQUAD (xP = expected points for GW{next_gw})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{squad_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOP TRANSFER-IN CANDIDATES (not in squad)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{targets_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITATIVE SIGNALS (news, injuries, manager quotes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{signals_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with ONLY a JSON object (no markdown, no explanation outside the JSON).
Follow this exact structure:

{{
  "transfer_in": {{
    "player": "Player Name",
    "reason": "2-3 sentence explanation"
  }},
  "transfer_out": {{
    "player": "Player Name",
    "reason": "2-3 sentence explanation"
  }},
  "captain": {{
    "player": "Player Name",
    "confidence_pct": 85,
    "reason": "2-3 sentence explanation"
  }},
  "starting_xi": {{
    "players": ["Name1", "Name2", ...],
    "bench_order": ["Name12", "Name13", "Name14", "Name15"],
    "reasoning": "2-3 sentence explanation of any changes from the default lineup"
  }},
  "daily_briefing": "Exactly 3 sentences summarising the key decisions for GW{next_gw}."
}}

Rules:
- starting_xi.players must contain exactly 11 names from the squad above
- bench_order must contain exactly 4 names (bench players in priority order)
- All player names must match exactly as shown in the squad list above
- confidence_pct must be an integer 0–100
- Prioritise: form, fixture difficulty, injury status, and qualitative signals
"""
    return prompt


# ---------------------------------------------------------------------------
# Call Claude and parse the response
# ---------------------------------------------------------------------------

def call_claude(prompt):
    """
    Send the prompt to Claude and return the raw text response.
    Raises an exception if the API call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "  export ANTHROPIC_API_KEY='your-key-here'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    print(f"[API]  Calling {MODEL} (max_tokens={MAX_TOKENS})...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=(
            "You are an expert FPL analyst. "
            "You MUST respond with ONLY valid JSON — no markdown, no preamble, no explanation."
        ),
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return raw


def parse_response(raw):
    """
    Parse Claude's JSON response.
    Returns (parsed_dict, error_string).
    """
    try:
        data = json.loads(raw)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}\nRaw: {raw[:300]}"


# ---------------------------------------------------------------------------
# Store results in DB
# ---------------------------------------------------------------------------

def save_recommendations(conn, next_gw, parsed, raw_response):
    """Save the parsed recommendations to the ai_recommendations table."""
    conn.execute("""
        INSERT OR REPLACE INTO ai_recommendations
            (gameweek, transfer_in, transfer_out, captain,
             starting_xi, daily_briefing, raw_response, model, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        next_gw,
        json.dumps(parsed.get("transfer_in",  {})),
        json.dumps(parsed.get("transfer_out", {})),
        json.dumps(parsed.get("captain",      {})),
        json.dumps(parsed.get("starting_xi",  {})),
        parsed.get("daily_briefing", ""),
        raw_response,
        MODEL,
        datetime.utcnow().isoformat(),
    ))
    conn.commit()
    print("[DB]   Recommendations saved to ai_recommendations table.")


# ---------------------------------------------------------------------------
# Pretty-print results to the terminal
# ---------------------------------------------------------------------------

def print_results(next_gw, parsed):
    """Display the recommendations in a readable format."""
    width = 62
    print(f"\n{'=' * width}")
    print(f"  Claude's FPL Recommendations — GW{next_gw}")
    print(f"  Model: {MODEL}")
    print(f"{'=' * width}")

    # Transfer In
    ti = parsed.get("transfer_in", {})
    print(f"\n  TRANSFER IN  →  {ti.get('player', '?')}")
    for line in _wrap(ti.get("reason", ""), 58):
        print(f"    {line}")

    # Transfer Out
    to = parsed.get("transfer_out", {})
    print(f"\n  TRANSFER OUT →  {to.get('player', '?')}")
    for line in _wrap(to.get("reason", ""), 58):
        print(f"    {line}")

    # Captain
    cap = parsed.get("captain", {})
    conf = cap.get("confidence_pct", "?")
    print(f"\n  CAPTAIN PICK →  {cap.get('player', '?')}  ({conf}% confidence)")
    for line in _wrap(cap.get("reason", ""), 58):
        print(f"    {line}")

    # Starting XI
    xi = parsed.get("starting_xi", {})
    players = xi.get("players", [])
    bench   = xi.get("bench_order", [])
    print(f"\n  STARTING XI")
    for i, name in enumerate(players, 1):
        print(f"    {i:2}. {name}")
    if bench:
        print(f"\n  BENCH (in priority order)")
        for i, name in enumerate(bench, 1):
            print(f"    {i}. {name}")
    if xi.get("reasoning"):
        print(f"\n  XI Reasoning:")
        for line in _wrap(xi["reasoning"], 58):
            print(f"    {line}")

    # Daily Briefing
    print(f"\n  DAILY BRIEFING")
    print(f"  {'─' * 58}")
    for line in _wrap(parsed.get("daily_briefing", ""), 58):
        print(f"  {line}")

    print(f"\n{'=' * width}\n")


def _wrap(text, width):
    """Simple word-wrap to keep terminal output tidy."""
    import textwrap
    return textwrap.wrap(text, width) if text else []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"  FPL Assistant — AI Recommendations")
    print(f"  Entry: {ENTRY_ID} (Tiki Taka CF)")
    print("=" * 60)

    # Guard: check API key early to give a clear error
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n[ERROR] ANTHROPIC_API_KEY is not set.")
        print("  Set it in your terminal before running:")
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    conn     = get_conn()
    next_gw  = get_next_gw(conn)

    if not next_gw:
        print("[ERROR] No upcoming gameweeks. Run engine/fetch_fpl.py first.")
        sys.exit(1)

    create_recommendations_table(conn)

    print(f"\n[DATA] Loading squad data for GW{next_gw}...")
    squad   = load_squad_with_xp(conn, next_gw)

    if len(squad) < 15:
        print(f"[ERROR] Only {len(squad)} squad players found. Run fetch_fpl.py first.")
        sys.exit(1)

    squad_names = [p["name"] for p in squad]
    print(f"       {len(squad)} squad players loaded.")

    print(f"[DATA] Loading transfer targets...")
    targets = load_transfer_targets(conn, next_gw, squad_names)
    print(f"       {len(targets)} transfer targets found.")

    print(f"[DATA] Loading qualitative signals...")
    signals = load_qualitative_signals(conn, next_gw)
    print(f"       {len(signals)} qualitative signal(s) found.")

    # Build and send the prompt
    prompt = build_prompt(next_gw, squad, targets, signals)

    try:
        raw = call_claude(prompt)
    except EnvironmentError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\n[ERROR] Anthropic API error: {e}")
        sys.exit(1)

    print("[API]  Response received. Parsing...")
    parsed, err = parse_response(raw)

    if err:
        print(f"[WARN] Could not parse JSON response: {err}")
        print("[WARN] Storing raw response and exiting.")
        # Store raw even if parse failed
        conn.execute("""
            INSERT OR REPLACE INTO ai_recommendations
                (gameweek, raw_response, model, created_at)
            VALUES (?, ?, ?, ?)
        """, (next_gw, raw, MODEL, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        sys.exit(1)

    save_recommendations(conn, next_gw, parsed, raw)
    conn.close()

    print_results(next_gw, parsed)


if __name__ == "__main__":
    main()
