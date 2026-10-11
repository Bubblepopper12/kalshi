"""Joint probability of combo legs.

Legs in the same game are rarely independent (a QB passing over and his team's
moneyline tend to hit together). Until the per-sport game simulators exist, the
joint probability is simulated with a Gaussian copula: each leg keeps its own
probability and legs are linked by a correlation matrix estimated from history.
A full game simulator can replace `simulate_joint` later by returning the same
boolean outcome matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

MAX_LEGS = 4


@dataclass(frozen=True)
class ComboQuote:
    joint_prob: float
    independent_prob: float
    std_error: float


def simulate_joint(probs: list[float], corr: np.ndarray | list[list[float]] | None = None,
                   n_sims: int = 200_000, seed: int | None = 0) -> np.ndarray:
    """Boolean matrix (n_sims x legs): did each leg hit in each simulation."""
    k = len(probs)
    if not 1 <= k <= MAX_LEGS:
        raise ValueError(f"combos take 1-{MAX_LEGS} legs, got {k}")
    if any(not 0 < p < 1 for p in probs):
        raise ValueError("leg probabilities must be in (0, 1)")
    corr = np.eye(k) if corr is None else np.asarray(corr, dtype=float)
    if corr.shape != (k, k) or not np.allclose(corr, corr.T) or not np.allclose(np.diag(corr), 1):
        raise ValueError("corr must be a symmetric correlation matrix with ones on the diagonal")
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(corr)  # raises if not positive definite
    z = rng.standard_normal((n_sims, k)) @ chol.T
    thresholds = np.array([NormalDist().inv_cdf(p) for p in probs])
    return z < thresholds


def combo_probability(probs: list[float], corr=None, n_sims: int = 200_000, seed: int | None = 0) -> ComboQuote:
    hits = simulate_joint(probs, corr, n_sims, seed).all(axis=1)
    p = float(hits.mean())
    return ComboQuote(
        joint_prob=p,
        independent_prob=float(np.prod(probs)),
        std_error=float(np.sqrt(p * (1 - p) / n_sims)),
    )
