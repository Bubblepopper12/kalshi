"""Read queries behind the pick board (kept out of the Streamlit file so they can be tested)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ..db import schema as t


def board(engine: Engine, since: datetime, leagues: list[str] | None = None,
          pick_types: list[str] | None = None, min_edge: float = 0.0,
          proven_only: bool = False, start_before: datetime | None = None) -> list[dict]:
    """Newest suggestion per (market, side) since `since`, with Logan's latest decision, sorted by edge."""
    s, d = t.suggestions, t.logan_decisions
    newest = (
        sa.select(sa.func.max(s.c.id).label("id"))
        .where(s.c.created_at >= since)
        .group_by(s.c.market_ticker, s.c.side)
        .subquery()
    )
    last_decision = (
        sa.select(d.c.suggestion_id, sa.func.max(d.c.id).label("decision_id"))
        .group_by(d.c.suggestion_id)
        .subquery()
    )
    q = (
        sa.select(s, d.c.decision, d.c.price_paid, d.c.contracts)
        .join(newest, newest.c.id == s.c.id)
        .outerjoin(last_decision, last_decision.c.suggestion_id == s.c.id)
        .outerjoin(d, d.c.id == last_decision.c.decision_id)
        .where(s.c.edge >= min_edge)
        .order_by(s.c.edge.desc())
    )
    if leagues:
        q = q.where(s.c.league.in_(leagues))
    if pick_types:
        q = q.where(s.c.pick_type.in_(pick_types))
    if start_before is not None:
        q = q.where(sa.or_(s.c.game_start.is_(None), s.c.game_start <= start_before))
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(q).mappings()]
    if proven_only:
        rows = [r for r in rows if any(b.get("tier") == "proven" for b in (r["tipsters_for"] or []))]
    return rows


def markets_with_prices(engine: Engine, league: str, market_types: list[str] | None = None,
                        lookback: timedelta = timedelta(days=1)) -> list[dict]:
    """Open Kalshi markets for a league with their latest snapshot (the Phase 1 view)."""
    m, p = t.kalshi_markets, t.kalshi_price_snapshots
    cutoff = datetime.now(timezone.utc) - lookback
    latest = (
        sa.select(p.c.market_ticker, sa.func.max(p.c.ts).label("ts"))
        .where(p.c.ts >= cutoff)
        .group_by(p.c.market_ticker)
        .subquery()
    )
    q = (
        sa.select(
            m.c.ticker, m.c.event_ticker, m.c.market_type, m.c.title, m.c.yes_sub_title,
            m.c.close_time, p.c.ts, p.c.yes_bid, p.c.yes_ask, p.c.no_bid, p.c.no_ask,
            p.c.volume, p.c.open_interest,
        )
        .join(latest, latest.c.market_ticker == m.c.ticker)
        .join(p, sa.and_(p.c.market_ticker == latest.c.market_ticker, p.c.ts == latest.c.ts))
        .where(m.c.league == league, m.c.status.in_(["open", "active"]))
        .order_by(m.c.close_time, m.c.event_ticker, m.c.ticker)
    )
    if market_types:
        q = q.where(m.c.market_type.in_(market_types))
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q).mappings()]


def _record(results: list[tuple[str, float]]) -> dict:
    wins = sum(r == "win" for r, _ in results)
    losses = sum(r == "loss" for r, _ in results)
    return {"wins": wins, "losses": losses, "units": round(sum(u for _, u in results), 2)}


def weekly_report(engine: Engine, start: datetime, end: datetime) -> dict:
    """Board record, Logan's record and each tipster tier's record for one window.

    Board and Logan are counted on settled Kalshi markets, per 1 contract at the
    board price (board) or the price paid (Logan). Tipster tiers use pick_grades units.
    """
    s, d, m = t.suggestions, t.logan_decisions, t.kalshi_markets
    with engine.connect() as conn:
        board_rows = conn.execute(
            sa.select(s.c.id, s.c.side, s.c.kalshi_price, s.c.fee_per_contract, m.c.result)
            .join(m, m.c.ticker == s.c.market_ticker)
            .where(s.c.created_at >= start, s.c.created_at < end, m.c.result.in_(["yes", "no"]))
        ).all()
        took = conn.execute(
            sa.select(s.c.side, d.c.price_paid, d.c.contracts, m.c.result)
            .join(s, s.c.id == d.c.suggestion_id)
            .join(m, m.c.ticker == s.c.market_ticker)
            .where(d.c.decision == "took", d.c.decided_at >= start, d.c.decided_at < end,
                   m.c.result.in_(["yes", "no"]))
        ).all()
        tiers = conn.execute(
            sa.select(t.tipster_scores.c.tier, t.pick_grades.c.result, t.pick_grades.c.units_won)
            .select_from(t.pick_grades)
            .join(t.picks, t.picks.c.id == t.pick_grades.c.pick_id)
            .join(t.tipster_scores, sa.and_(
                t.tipster_scores.c.tipster_id == t.picks.c.tipster_id,
                t.tipster_scores.c.league == t.picks.c.league,
                t.tipster_scores.c.pick_type == t.picks.c.pick_type,
            ))
            .outerjoin(t.games, t.games.c.id == t.picks.c.game_id)
            .where(t.games.c.start_time >= start, t.games.c.start_time < end)
        ).all()

    def contract_result(side, price, result, contracts=1):
        cost = float(price)
        won = result == side
        return ("win" if won else "loss", (1 - cost if won else -cost) * contracts)

    board_res = [contract_result(r.side, float(r.kalshi_price) + float(r.fee_per_contract), r.result)
                 for r in board_rows]
    logan_res = [contract_result(r.side, r.price_paid, r.result, r.contracts or 0) for r in took]
    by_tier: dict[str, list] = {}
    for r in tiers:
        by_tier.setdefault(r.tier, []).append((r.result, float(r.units_won)))
    return {
        "board": _record(board_res),
        "logan": _record(logan_res),
        "tiers": {tier: _record(v) for tier, v in sorted(by_tier.items())},
    }


def exposure_today(engine: Engine) -> float:
    """Dollars Logan reported putting on today's picks."""
    d = t.logan_decisions
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(d.c.price_paid, d.c.contracts).where(d.c.decision == "took", d.c.decided_at >= start)
        ).all()
    return round(sum(float(p or 0) * (c or 0) for p, c in rows), 2)
