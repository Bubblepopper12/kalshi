"""Sportsbook odds conversion and vig removal."""

from __future__ import annotations

from collections.abc import Sequence


def american_to_decimal(odds: float) -> float:
    if odds == 0 or -100 < odds < 100:
        raise ValueError(f"invalid American odds: {odds}")
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def american_to_prob(odds: float) -> float:
    """Implied probability including the vig."""
    return 1 / american_to_decimal(odds)


def prob_to_american(p: float) -> int:
    if not 0 < p < 1:
        raise ValueError(f"probability must be in (0, 1): {p}")
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def devig(odds: Sequence[float], method: str = "power") -> list[float]:
    """Fair probabilities for a complete set of outcomes (2-way or 3-way).

    "multiplicative" scales implied probabilities to sum to 1. "power" finds k with
    sum(p_i ** k) = 1, which moves more of the margin onto longshots and fits real
    books better on lopsided markets.
    """
    implied = [american_to_prob(o) for o in odds]
    if method == "multiplicative":
        total = sum(implied)
        return [p / total for p in implied]
    if method != "power":
        raise ValueError(f"unknown devig method: {method}")
    lo, hi = 0.5, 3.0
    for _ in range(100):
        k = (lo + hi) / 2
        s = sum(p**k for p in implied)
        if s > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    fair = [p**k for p in implied]
    total = sum(fair)
    return [p / total for p in fair]
