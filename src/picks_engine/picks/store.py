"""Persist board suggestions and Logan's decisions."""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ..db import schema as t
from .generate import Suggestion


def save_suggestions(engine: Engine, run_id: str, suggestions: list[Suggestion]) -> list[int]:
    now = datetime.now(timezone.utc)
    ids = []
    with engine.begin() as conn:
        for s in suggestions:
            row = {k: v for k, v in s.__dict__.items()} | {"run_id": run_id, "created_at": now}
            ids.append(conn.execute(t.suggestions.insert().values(**row)).inserted_primary_key[0])
    return ids


def record_decision(engine: Engine, suggestion_id: int, decision: str,
                    price_paid: float | None = None, contracts: int | None = None,
                    note: str | None = None) -> int:
    if decision not in ("took", "pass"):
        raise ValueError("decision must be 'took' or 'pass'")
    if decision == "took" and (price_paid is None or not contracts):
        raise ValueError("'took' needs the price paid and number of contracts")
    with engine.begin() as conn:
        exists = conn.execute(
            sa.select(t.suggestions.c.id).where(t.suggestions.c.id == suggestion_id)
        ).first()
        if not exists:
            raise ValueError(f"no suggestion {suggestion_id}")
        return conn.execute(
            t.logan_decisions.insert().values(
                suggestion_id=suggestion_id, decision=decision, price_paid=price_paid,
                contracts=contracts if decision == "took" else None, note=note,
                decided_at=datetime.now(timezone.utc),
            )
        ).inserted_primary_key[0]
