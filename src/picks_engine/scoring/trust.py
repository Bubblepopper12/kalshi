"""Tipster trust scores and tiers, per (league, pick type).

Starting-point formulas from the concept, to be tuned by backtest:

    ROI_shrunk = n / (n + k) * ROI_observed           k ~= 200
    Trust      = 0.6 * z(CLV) + 0.4 * z(ROI_shrunk)   z across tipsters in the group

Recency: each pick is weighted 0.5 ** (age / half_life), half-life about one
season. The n used for shrinkage is the effective sample size of those weights,
so a tipster whose picks are all old is pulled toward zero like a small sample.
CLV is shrunk the same way with a smaller k, because it needs far fewer picks.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ScoringParams:
    roi_k: float = 200.0
    clv_k: float = 50.0
    w_clv: float = 0.6
    w_roi: float = 0.4
    half_life_days: float = 365.0
    proven_min_picks: int = 300
    proven_top_share: float = 0.10
    fade_min_picks: int = 300
    fade_t: float = -2.0  # CLV t-stat at or below this is "reliably negative"


@dataclass(frozen=True)
class GradedPick:
    tipster_id: int
    league: str
    pick_type: str
    graded_at: datetime  # game time; used for recency
    result: str
    units_risked: float
    units_won: float
    clv: float | None


@dataclass
class TipsterScore:
    tipster_id: int
    league: str
    pick_type: str
    n_graded: int
    n_effective: float
    clv_mean: float | None
    clv_t: float | None
    roi_observed: float | None
    roi_shrunk: float
    clv_shrunk: float
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    trust: float = 0.0
    tier: str = "neutral"
    z_clv: float = 0.0
    z_roi: float = 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.pushes}"

    def as_row(self) -> dict:
        return {
            "tipster_id": self.tipster_id,
            "league": self.league,
            "pick_type": self.pick_type,
            "n_graded": self.n_graded,
            "n_effective": round(self.n_effective, 2),
            "clv_mean": None if self.clv_mean is None else round(self.clv_mean, 5),
            "clv_t": None if self.clv_t is None else round(self.clv_t, 3),
            "roi_observed": None if self.roi_observed is None else round(self.roi_observed, 5),
            "roi_shrunk": round(self.roi_shrunk, 5),
            "trust": round(self.trust, 4),
            "tier": self.tier,
            "record": self.record,
        }


def _weighted_stats(values: list[float], weights: list[float]) -> tuple[float, float, float]:
    """Weighted mean, t-stat of the mean, and effective sample size."""
    sw = sum(weights)
    sw2 = sum(w * w for w in weights)
    n_eff = (sw * sw / sw2) if sw2 else 0.0
    mean = sum(v * w for v, w in zip(values, weights)) / sw
    if n_eff <= 1:
        return mean, 0.0, n_eff
    var = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / sw * n_eff / (n_eff - 1)
    se = math.sqrt(var / n_eff) if var > 0 else 0.0
    t = mean / se if se > 0 else 0.0
    return mean, t, n_eff


def _zscores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return [0.0 if sd == 0 else (v - mean) / sd for v in values]


def score_one(picks: list[GradedPick], params: ScoringParams, now: datetime) -> TipsterScore:
    first = picks[0]
    decided = [p for p in picks if p.result in ("win", "loss", "push")]
    weights = [0.5 ** (max((now - p.graded_at).total_seconds(), 0) / 86400 / params.half_life_days)
               for p in decided]

    risked = sum(w * p.units_risked for p, w in zip(decided, weights))
    won = sum(w * p.units_won for p, w in zip(decided, weights))
    roi_obs = won / risked if risked else None
    sw, sw2 = sum(weights), sum(w * w for w in weights)
    n_eff = sw * sw / sw2 if sw2 else 0.0
    roi_shrunk = (n_eff / (n_eff + params.roi_k)) * roi_obs if roi_obs is not None else 0.0

    with_clv = [(p.clv, w) for p, w in zip(decided, weights) if p.clv is not None]
    if with_clv:
        clv_mean, clv_t, clv_n = _weighted_stats([c for c, _ in with_clv], [w for _, w in with_clv])
        clv_shrunk = clv_n / (clv_n + params.clv_k) * clv_mean
    else:
        clv_mean = clv_t = None
        clv_shrunk = 0.0

    return TipsterScore(
        tipster_id=first.tipster_id,
        league=first.league,
        pick_type=first.pick_type,
        n_graded=len(decided),
        n_effective=n_eff,
        clv_mean=clv_mean,
        clv_t=clv_t,
        roi_observed=roi_obs,
        roi_shrunk=roi_shrunk,
        clv_shrunk=clv_shrunk,
        wins=sum(p.result == "win" for p in decided),
        losses=sum(p.result == "loss" for p in decided),
        pushes=sum(p.result == "push" for p in decided),
    )


def assign_tiers(group: list[TipsterScore], params: ScoringParams) -> None:
    """Trust and tier for every tipster in one (league, pick type) group, in place."""
    for s, zc, zr in zip(group, _zscores([s.clv_shrunk for s in group]),
                         _zscores([s.roi_shrunk for s in group])):
        s.z_clv, s.z_roi = zc, zr
        s.trust = params.w_clv * zc + params.w_roi * zr

    ranked = sorted(group, key=lambda s: s.trust, reverse=True)
    top_n = max(1, math.floor(len(group) * params.proven_top_share)) if len(group) >= 2 else 0
    top_ids = {id(s) for s in ranked[:top_n]}
    for s in group:
        if s.n_graded >= params.fade_min_picks and s.clv_t is not None and s.clv_t <= params.fade_t:
            s.tier = "fade"
        elif id(s) in top_ids and s.n_graded >= params.proven_min_picks and s.trust > 0:
            s.tier = "proven"
        elif s.trust > 0 and s.n_graded < params.proven_min_picks:
            s.tier = "promising"
        else:
            s.tier = "neutral"


def score_tipsters(
    picks: Iterable[GradedPick], params: ScoringParams | None = None, now: datetime | None = None
) -> list[TipsterScore]:
    params = params or ScoringParams()
    now = now or datetime.now(timezone.utc)
    by_key: dict[tuple, list[GradedPick]] = defaultdict(list)
    for p in picks:
        by_key[(p.league, p.pick_type, p.tipster_id)].append(p)

    groups: dict[tuple, list[TipsterScore]] = defaultdict(list)
    for (league, pick_type, _), plist in by_key.items():
        score = score_one(plist, params, now)
        if score.n_graded:
            groups[(league, pick_type)].append(score)

    out: list[TipsterScore] = []
    for group in groups.values():
        assign_tiers(group, params)
        out.extend(group)
    return out
