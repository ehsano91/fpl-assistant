"""
fpl_rules.py  —  FPL Official Rules Reference
----------------------------------------------
A single source of truth for every Fantasy Premier League rule that
the model, recommendation engine, and squad validator must respect.

Import this module anywhere you need to check or enforce a rule:
    from fpl_rules import MAX_PLAYERS_PER_CLUB, hit_cost, is_hit_worthwhile

Sections:
  1. Squad composition rules
  2. Formation rules
  3. Budget rules
  4. Transfer rules
  5. Chip rules
  6. Helper functions
"""


# ===========================================================================
# 1. SQUAD COMPOSITION
# ===========================================================================

# Your squad always has exactly 15 players: 11 starters + 4 on the bench.
SQUAD_SIZE   = 15
STARTERS     = 11
BENCH_SIZE   = 4

# FPL position codes — these match the `element_type` field in the FPL API.
GKP = 1   # Goalkeeper
DEF = 2   # Defender
MID = 3   # Midfielder
FWD = 4   # Forward

# Human-readable labels for each position code.
POSITION_NAMES = {GKP: "GKP", DEF: "DEF", MID: "MID", FWD: "FWD"}

# Every valid 15-man FPL squad must contain exactly these counts per position.
# (You can vary the formation within the starting XI, but the squad totals
#  are fixed — always 2 GKPs, 5 DEFs, 5 MIDs, 3 FWDs.)
REQUIRED_SQUAD_COUNTS = {
    GKP: 2,
    DEF: 5,
    MID: 5,
    FWD: 3,
}

# No more than 3 players from the same Premier League club in your squad.
MAX_PLAYERS_PER_CLUB = 3

# The first bench slot (squad position 12) must be a goalkeeper.
# He acts as the emergency substitute if your starting GK doesn't play.
BENCH_GK_SLOT = STARTERS + 1   # squad position 12


# ===========================================================================
# 2. FORMATION RULES  (starting XI only)
# ===========================================================================

# Minimum number of starters required per position.
# These rules ensure every valid formation (e.g. 4-4-2, 3-5-2, 4-3-3) is
# covered while illegal ones (e.g. 0 defenders) are caught.
MIN_STARTERS = {
    GKP: 1,   # exactly 1 goalkeeper must start
    DEF: 3,   # at least 3 defenders (3-back or 4-back or 5-back)
    MID: 2,   # at least 2 midfielders
    FWD: 1,   # at least 1 forward
}

# The starting GK must be exactly 1 (not 0, not 2).
EXACT_STARTERS = {
    GKP: 1,
}


# ===========================================================================
# 3. BUDGET RULES
# ===========================================================================

# The total budget you start the season with, in millions of GBP.
STARTING_BUDGET = 100.0

# FPL sell price rule:
#   If a player's price has RISEN since you bought them, you only receive
#   half of the profit back.  The other half stays with FPL.
#
#   Examples:
#     Bought Salah for £12.5m, now worth £13.0m → sell for £12.75m
#     Bought Salah for £12.5m, now worth £12.0m → sell for £12.0m (no penalty)
SELL_PROFIT_FRACTION = 0.5   # you keep 50 % of any price rise


def sell_price(buy_price: float, current_price: float) -> float:
    """
    Calculate how much you would receive for selling a player.

    Args:
        buy_price:     The price you originally paid (in £m).
        current_price: The player's current market price (in £m).

    Returns:
        The amount credited to your budget if you sell (in £m).

    >>> sell_price(8.0, 8.4)   # price rose by 0.4m → you keep half
    8.2
    >>> sell_price(8.0, 7.8)   # price dropped → no penalty, get current price
    7.8
    >>> sell_price(8.0, 8.0)   # no change
    8.0
    """
    if current_price > buy_price:
        profit = current_price - buy_price
        return buy_price + profit * SELL_PROFIT_FRACTION
    # Price stayed the same or dropped — you receive the current price
    return current_price


def remaining_budget(
    outgoing_sell_prices: list[float],
    incoming_costs: list[float],
    current_bank: float = 0.0,
) -> float:
    """
    Calculate the budget remaining after a set of transfers.

    Args:
        outgoing_sell_prices: Sell prices of every player you're selling (£m).
        incoming_costs:       Buy prices of every player you're buying (£m).
        current_bank:         Money already in the bank before this transfer (£m).

    Returns:
        Remaining budget in £m (negative = over budget = illegal transfer).

    Example:
        Selling a player at £7.8m, buying one at £8.0m, with £0.5m in bank:
        remaining_budget([7.8], [8.0], 0.5) → 0.3
    """
    bank_after = current_bank + sum(outgoing_sell_prices) - sum(incoming_costs)
    return round(bank_after, 1)


# ===========================================================================
# 4. TRANSFER RULES
# ===========================================================================

# At the start of each gameweek you receive 1 free transfer.
# If you don't use it, it rolls over to the NEXT gameweek (max 2 banked).
FREE_TRANSFERS_PER_GW = 1
MAX_BANKED_TRANSFERS  = 2

# Every transfer beyond your free allocation costs 4 points (a "hit").
HIT_COST_POINTS = 4

# Minimum NET expected-points gain over the next 3 gameweeks before we
# recommend a player accept a points hit.  12 pts = 3 GWs × 4 pts/GW
# which means the hit has paid for itself within 3 weeks.
MIN_NET_XP_FOR_HIT = 12.0


def hit_cost(extra_transfers: int) -> int:
    """
    Total points deducted for taking extra (paid) transfers.

    Args:
        extra_transfers: Number of transfers BEYOND your free transfers.
                         Negative values are treated as 0.

    Returns:
        Points deducted (always >= 0).

    >>> hit_cost(0)   # no extra transfers — no cost
    0
    >>> hit_cost(1)   # one hit
    4
    >>> hit_cost(2)   # two hits
    8
    """
    return max(0, extra_transfers) * HIT_COST_POINTS


def is_hit_worthwhile(xp_gain_3gw: float, extra_transfers: int) -> bool:
    """
    Decide whether taking a points hit is worth it.

    The rule: only recommend a hit when the NET expected-points gain
    (after subtracting hit costs) across the next 3 gameweeks exceeds
    MIN_NET_XP_FOR_HIT (12 pts by default).

    Args:
        xp_gain_3gw:       Expected xP improvement over the next 3 GWs
                           (new player xP minus old player xP, summed).
        extra_transfers:   Number of paid transfers beyond free allocation.

    Returns:
        True if the hit is worth taking, False otherwise.

    >>> is_hit_worthwhile(20.0, 1)   # gain 20, cost 4 → net 16 > 12 ✓
    True
    >>> is_hit_worthwhile(14.0, 1)   # gain 14, cost 4 → net 10 < 12 ✗
    False
    """
    cost    = hit_cost(extra_transfers)
    net_gain = xp_gain_3gw - cost
    return net_gain > MIN_NET_XP_FOR_HIT


def transfer_summary(
    free_transfers: int,
    transfers_planned: int,
) -> dict:
    """
    Build a plain-English summary of the transfer situation.

    Returns a dict with:
        free_transfers:    how many free transfers are available
        transfers_planned: how many the user wants to make
        hits_taken:        how many will cost 4 pts each
        points_cost:       total points deducted
        recommendation:    short advice string
    """
    hits      = max(0, transfers_planned - free_transfers)
    pts_cost  = hit_cost(hits)

    if hits == 0:
        advice = f"{transfers_planned} transfer(s) within free allowance — no cost."
    else:
        advice = (
            f"{hits} hit(s) taken — -{pts_cost} pts. "
            f"Only proceed if net xP gain over 3 GWs > {MIN_NET_XP_FOR_HIT}."
        )

    return {
        "free_transfers":    free_transfers,
        "transfers_planned": transfers_planned,
        "hits_taken":        hits,
        "points_cost":       pts_cost,
        "recommendation":    advice,
    }


# ===========================================================================
# 5. CHIP RULES
# ===========================================================================

# Chip identifiers
CHIP_WILDCARD       = "wildcard"
CHIP_FREE_HIT       = "free_hit"
CHIP_TRIPLE_CAPTAIN = "triple_captain"
CHIP_BENCH_BOOST    = "bench_boost"

# How many times each chip can be used per season.
# Wildcard is special: it can be used once in each half of the season.
CHIP_USES = {
    CHIP_WILDCARD:       2,   # once per half-season (H1 = GW1-19, H2 = GW20-38)
    CHIP_FREE_HIT:       1,
    CHIP_TRIPLE_CAPTAIN: 1,
    CHIP_BENCH_BOOST:    1,
}

# Plain-English description of each chip.
CHIP_DESCRIPTIONS = {
    CHIP_WILDCARD: (
        "Wildcard — freely replace your entire squad for one gameweek. "
        "Available TWICE per season (once in each half). "
        "Use it when your squad needs a major overhaul or during a double-GW."
    ),
    CHIP_FREE_HIT: (
        "Free Hit — acts like a one-gameweek wildcard. You can make unlimited "
        "transfers for a single GW; your squad then reverts to its pre-FH state. "
        "Best used to cover a blank gameweek or double gameweek."
    ),
    CHIP_TRIPLE_CAPTAIN: (
        "Triple Captain — your captain earns triple points instead of double "
        "for one gameweek. Best used when your captain has an easy home fixture "
        "or a double gameweek."
    ),
    CHIP_BENCH_BOOST: (
        "Bench Boost — all 15 players' points count this gameweek (not just the "
        "starting 11). Best used in a double gameweek when many bench players "
        "have good fixtures."
    ),
}

# Minimum conditions before recommending a chip.
# These are guidelines — the AI may still recommend one with a strong reason.
CHIP_GUIDELINES = {
    CHIP_WILDCARD: (
        "Only recommend if 4+ squad players have poor fixtures for 3+ GWs, "
        "OR if a major injury/suspension crisis hits multiple key players."
    ),
    CHIP_FREE_HIT: (
        "Only recommend for a blank gameweek where 6+ players have no fixture, "
        "or a large double gameweek with 6+ players having two games."
    ),
    CHIP_TRIPLE_CAPTAIN: (
        "Only recommend when the captain candidate has a double gameweek "
        "or an extremely easy home fixture (FDR ≤ 2) AND is in top form."
    ),
    CHIP_BENCH_BOOST: (
        "Only recommend for a double gameweek where at least 3 bench players "
        "have two fixtures and decent xP."
    ),
}


def chip_advice(chip_name: str) -> str:
    """
    Return a short advice string for a given chip.

    Args:
        chip_name: One of the CHIP_* constants above.

    Returns:
        A multi-sentence string explaining the chip and when to use it.
    """
    desc      = CHIP_DESCRIPTIONS.get(chip_name, "Unknown chip.")
    guideline = CHIP_GUIDELINES.get(chip_name, "")
    return f"{desc}\nGuideline: {guideline}"
