"""Turn the three views (tipsters, model, sharp market) into board suggestions.

All probabilities here are for the Kalshi contract's YES outcome. Both sides of
each contract are checked: YES at the yes ask, and NO at the no ask with 1 - p.

A suggestion needs:
  * the model and the de-vigged market both present and both above the cost,
  * tipsters, when any tracked tipster has a view, not net against the side,
  * edge >= min_edge after the Kalshi fee,
  * at least min_depth contracts available at the ask,
  * no unconfirmed key injury.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..pricing.edge import quote_edge
from ..pricing.kelly import stake_fraction

TIER_WEIGHT = {"proven": 1.0, "promising": 0.5, "neutral": 0.0}


@dataclass(frozen=True)
class Backing:
    """One tipster's pick on this contract. agrees_with_yes: they picked the YES outcome."""
    name: str
    tier: str
    trust: float
    agrees_with_yes: bool
    record: str = ""
    posted_at: str = ""


@dataclass(frozen=True)
class BlendParams:
    w_model: float = 0.35
    w_market: float = 0.45
    w_tipster: float = 0.20
    tipster_beta: float = 0.10  # logit shift per unit of trust signal
    fade_weight: float = 0.25  # a Fade tipster's pick counts this much the other way
    max_signal: float = 3.0
    min_edge: float = 0.03
    min_depth: int = 100
    require_tipster_agreement: bool = True
    kelly_fraction: float = 0.25
    stake_cap: float = 0.02
    fee_rate: float = 0.07
    fee_contracts: int = 100


@dataclass
class Candidate:
    market_ticker: str
    league: str
    pick_type: str
    description_yes: str
    description_no: str
    yes_ask: float | None
    no_ask: float | None
    model_prob: float | None = None
    market_prob: float | None = None
    backings: list[Backing] = field(default_factory=list)
    depth_yes: int = 0  # contracts available at the yes ask
    depth_no: int = 0
    injury_unconfirmed: bool = False
    game_id: int | None = None
    game_label: str = ""
    game_start: object = None
    notes: dict = field(default_factory=dict)


@dataclass
class Suggestion:
    market_ticker: str
    league: str
    pick_type: str
    side: str
    description: str
    kalshi_price: float
    fee_per_contract: float
    fair_prob: float
    edge: float
    model_prob: float | None
    market_prob: float | None
    tipster_prob: float | None
    tipsters_for: list[dict]
    tipsters_against: list[dict]
    depth_at_price: int
    stake_pct: float
    game_id: int | None = None
    game_label: str = ""
    game_start: object = None
    notes: dict = field(default_factory=dict)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def tipster_signal(backings: list[Backing], params: BlendParams) -> float | None:
    """Net trust behind YES (positive) or NO (negative). None when no tracked tipster has a view."""
    if not backings:
        return None
    total = 0.0
    for b in backings:
        if b.tier == "fade":
            contrib = -params.fade_weight * abs(b.trust)
        else:
            contrib = TIER_WEIGHT.get(b.tier, 0.0) * max(b.trust, 0.0)
        total += contrib if b.agrees_with_yes else -contrib
    return max(-params.max_signal, min(params.max_signal, total))


def blend(model: float | None, market: float | None, tipster: float | None, params: BlendParams) -> float | None:
    parts = [(model, params.w_model), (market, params.w_market), (tipster, params.w_tipster)]
    parts = [(p, w) for p, w in parts if p is not None and w > 0]
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return _sigmoid(sum(_logit(p) * w for p, w in parts) / total_w)


def _side_view(c: Candidate, side: str, params: BlendParams, signal: float | None):
    flip = (lambda p: None if p is None else 1 - p) if side == "no" else (lambda p: p)
    model, market = flip(c.model_prob), flip(c.market_prob)
    side_signal = None if signal is None else (signal if side == "yes" else -signal)
    base = market if market is not None else model
    tipster = None
    if side_signal is not None and base is not None:
        tipster = _sigmoid(_logit(base) + params.tipster_beta * side_signal)
    return model, market, tipster, side_signal


def evaluate(c: Candidate, params: BlendParams | None = None) -> Suggestion | None:
    """The better of YES/NO if it passes every filter, else None."""
    params = params or BlendParams()
    if c.injury_unconfirmed:
        return None
    signal = tipster_signal(c.backings, params)
    best: Suggestion | None = None
    for side, ask, depth, desc in (
        ("yes", c.yes_ask, c.depth_yes, c.description_yes),
        ("no", c.no_ask, c.depth_no, c.description_no),
    ):
        if ask is None or not 0 < ask < 1:
            continue
        model, market, tipster, side_signal = _side_view(c, side, params, signal)
        if model is None or market is None:
            continue
        fair = blend(model, market, tipster, params)
        q = quote_edge(fair, ask, params.fee_contracts, params.fee_rate)
        if model <= q.cost or market <= q.cost:
            continue
        if params.require_tipster_agreement and side_signal is not None and side_signal < 0:
            continue
        if q.edge < params.min_edge or depth < params.min_depth:
            continue
        agrees = [b for b in c.backings if b.agrees_with_yes == (side == "yes")]
        opposes = [b for b in c.backings if b.agrees_with_yes != (side == "yes")]
        s = Suggestion(
            market_ticker=c.market_ticker, league=c.league, pick_type=c.pick_type, side=side,
            description=desc, kalshi_price=ask, fee_per_contract=q.fee, fair_prob=round(fair, 4),
            edge=round(q.edge, 4), model_prob=model, market_prob=market, tipster_prob=tipster,
            tipsters_for=[b.__dict__ for b in agrees], tipsters_against=[b.__dict__ for b in opposes],
            depth_at_price=depth,
            stake_pct=stake_fraction(fair, q.cost, params.kelly_fraction, params.stake_cap),
            game_id=c.game_id, game_label=c.game_label, game_start=c.game_start, notes=c.notes,
        )
        if best is None or s.edge > best.edge:
            best = s
    return best


def build_board(candidates: list[Candidate], params: BlendParams | None = None) -> list[Suggestion]:
    out = [s for c in candidates if (s := evaluate(c, params)) is not None]
    return sorted(out, key=lambda s: s.edge, reverse=True)
