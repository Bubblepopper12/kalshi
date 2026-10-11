"""Grade one pick: result, units won and closing-line value.

Sides: moneyline home/away/draw, spread home/away (line is that side's handicap,
e.g. -3.5), total over/under, prop over/under (line is the stat threshold).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..pricing.devig import american_to_decimal, american_to_prob


@dataclass(frozen=True)
class Outcome:
    home_score: float | None = None
    away_score: float | None = None
    stat_value: float | None = None  # player prop result
    void: bool = False  # cancelled game, player inactive, etc.


@dataclass(frozen=True)
class Grade:
    result: str  # win | loss | push | void
    units_risked: float
    units_won: float
    clv: float | None


def is_gradable(posted_at: datetime | None, captured_at: datetime, start_time: datetime) -> bool:
    """Only picks we saw before kickoff count. A claimed post time is not enough on its own."""
    seen = max(posted_at, captured_at) if posted_at else captured_at
    return seen < start_time


def result_of(pick_type: str, side: str, line: float | None, outcome: Outcome, three_way: bool = False) -> str:
    if outcome.void:
        return "void"
    if pick_type == "prop":
        if outcome.stat_value is None or line is None:
            return "void"
        diff = outcome.stat_value - line
        if side == "under":
            diff = -diff
        return "win" if diff > 0 else "loss" if diff < 0 else "push"

    if outcome.home_score is None or outcome.away_score is None:
        return "void"
    home, away = outcome.home_score, outcome.away_score

    if pick_type == "moneyline":
        winner = "home" if home > away else "away" if away > home else "draw"
        if winner == "draw" and side in ("home", "away"):
            # Two-way moneylines (NFL/NBA ties) push; soccer three-way picks lose to a draw.
            return "loss" if three_way else "push"
        return "win" if side == winner else "loss"

    if pick_type == "spread":
        if line is None:
            return "void"
        margin = (home - away) if side == "home" else (away - home)
        diff = margin + line
        return "win" if diff > 0 else "loss" if diff < 0 else "push"

    if pick_type == "total":
        if line is None:
            return "void"
        diff = (home + away) - line
        if side == "under":
            diff = -diff
        return "win" if diff > 0 else "loss" if diff < 0 else "push"

    raise ValueError(f"cannot grade pick type {pick_type!r} directly (combos are graded leg by leg)")


def clv(posted_odds: float | None, closing_fair_prob: float | None) -> float | None:
    """Closing fair probability minus the probability implied by the posted price.

    Positive means the tipster got a better price than the market settled on.
    Use the de-vigged closing probability for the same side and line.
    """
    if posted_odds is None or closing_fair_prob is None:
        return None
    return closing_fair_prob - american_to_prob(posted_odds)


def grade(
    pick_type: str,
    side: str,
    line: float | None,
    odds: float | None,
    units: float,
    outcome: Outcome,
    closing_fair_prob: float | None = None,
    three_way: bool = False,
) -> Grade:
    result = result_of(pick_type, side, line, outcome, three_way)
    price = odds if odds is not None else -110  # tipsters who omit odds are graded at standard juice
    if result == "win":
        won = units * (american_to_decimal(price) - 1)
    elif result == "loss":
        won = -units
    else:
        won = 0.0
    risked = units if result in ("win", "loss") else 0.0
    return Grade(result, risked, round(won, 4), clv(odds, closing_fair_prob))
