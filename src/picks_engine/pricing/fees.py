"""Kalshi trading fees.

Kalshi's general taker fee is round_up_to_cent(rate * C * P * (1 - P)) for C
contracts at price P, with rate 0.07. Some series use a different rate; check the
fee schedule and set KALSHI_FEE_RATE if it changes.
"""

from __future__ import annotations

import math


def kalshi_fee(price: float, contracts: int = 1, rate: float = 0.07) -> float:
    """Total fee in dollars for buying `contracts` at `price` (0-1)."""
    if contracts <= 0:
        return 0.0
    raw = rate * contracts * price * (1.0 - price)
    # Round up to the next cent; the small epsilon keeps float noise (e.g. 1.0000000002) from adding a cent.
    return math.ceil(raw * 100 - 1e-9) / 100


def fee_per_contract(price: float, contracts: int = 100, rate: float = 0.07) -> float:
    return kalshi_fee(price, contracts, rate) / contracts
