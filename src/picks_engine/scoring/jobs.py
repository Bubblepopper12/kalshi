"""Database jobs for scoring: recompute tipster_scores from pick_grades."""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ..db import schema as t
from ..db.session import upsert
from .trust import GradedPick, ScoringParams, score_tipsters


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rescore_tipsters(engine: Engine, params: ScoringParams | None = None) -> int:
    """Score every tipster in every (league, pick type) from their gradable, graded picks."""
    p, g, games = t.picks, t.pick_grades, t.games
    query = (
        sa.select(
            p.c.tipster_id, p.c.league, p.c.pick_type, g.c.result, g.c.units_risked,
            g.c.units_won, g.c.clv, sa.func.coalesce(games.c.start_time, g.c.graded_at).label("when"),
        )
        .join(g, g.c.pick_id == p.c.id)
        .outerjoin(games, games.c.id == p.c.game_id)
        .where(p.c.gradable.is_(True))
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    graded = [
        GradedPick(r.tipster_id, r.league, r.pick_type, _aware(r.when), r.result,
                   float(r.units_risked), float(r.units_won), None if r.clv is None else float(r.clv))
        for r in rows
    ]
    scores = score_tipsters(graded, params)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(t.tipster_scores.delete())
        return upsert(conn, t.tipster_scores, [s.as_row() | {"computed_at": now} for s in scores],
                      ["tipster_id", "league", "pick_type"])
