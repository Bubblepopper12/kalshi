"""Corrections for the soccer goals model, fitted on real results (scripts/validate_models.py).

The plain goals model, fitted to Pinnacle's closing odds, was checked on 11,605 games (5 leagues,
2019-2026). Totals were already right; it under-rated both-teams-to-score (51.0% vs 54.2%) and draws,
and over-rated favourites winning by 2+ (31.8% vs 29.2%). Each market type gets a small logistic
correction, P = sigmoid(a + b * logit(model)), fitted on 2019-2024 (8,955 games) and checked on
2024-2026 (2,650 games it never saw): every market then landed within 0.7 points of reality.
"""

from __future__ import annotations

import math

COEFS = {"over 0.5": (0.1113, 0.9648), "over 1.5": (0.0949, 0.9929), "over 2.5": (0.0227, 1.0359),
         "over 3.5": (0.0157, 1.0321), "over 4.5": (-0.1273, 0.9507), "over 5.5": (-0.1540, 0.9663),
         "both score": (0.1397, 1.0518), "draw": (0.2417, 1.0892), "fav by 1.5": (-0.1787, 0.9044),
         "dog by 1.5": (-0.2147, 0.9459), "fav by 2.5": (-0.2376, 0.9371), "dog by 2.5": (-0.3747, 0.9144),
         "fav by 3.5": (-0.1964, 0.9938), "dog by 3.5": (-1.0905, 0.7996)}


def calibrated(market: str, p: float) -> float:
    """The corrected chance for a market ("over 3.5", "both score", "fav by 1.5"...); unchanged if unknown."""
    ab = COEFS.get(market)
    if ab is None:
        return p
    p = min(max(p, 1e-4), 1 - 1e-4)
    return 1 / (1 + math.exp(-(ab[0] + ab[1] * math.log(p / (1 - p)))))
