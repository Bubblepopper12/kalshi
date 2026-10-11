"""Stake guide: fractional Kelly on a binary contract, capped as a share of bankroll."""

from __future__ import annotations


def stake_fraction(fair_prob: float, cost: float, kelly_fraction: float = 0.25, cap: float = 0.02) -> float:
    """Share of bankroll to put on a contract costing `cost` (price + fee) that pays 1.

    Full Kelly for this payoff is (q - c) / (1 - c). The guide uses quarter Kelly
    and never goes above `cap` (2% by default).
    """
    if not 0 < cost < 1 or fair_prob <= cost:
        return 0.0
    full = (fair_prob - cost) / (1 - cost)
    return round(min(full * kelly_fraction, cap), 4)
