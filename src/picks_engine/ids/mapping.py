"""ID matching: map each source's names for teams, players and games to internal IDs.

Every miss goes to id_review_queue instead of being guessed. Resolving a queue
item writes an alias, so the same name never needs review twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from ..db import schema as t
from ..db.session import upsert
from ..kalshi.classify import split_teams_code


def normalize(name: str) -> str:
    return " ".join("".join(ch for ch in name.lower() if ch.isalnum() or ch.isspace()).split())


def resolve(conn: Connection, entity_type: str, league: str, source: str, source_key: str) -> int | None:
    a = t.entity_aliases
    return conn.execute(
        sa.select(a.c.internal_id).where(
            a.c.entity_type == entity_type, a.c.league == league,
            a.c.source == source, a.c.source_key == normalize(source_key),
        )
    ).scalar()


def add_alias(conn: Connection, entity_type: str, league: str, source: str, source_key: str,
              internal_id: int, method: str = "manual") -> None:
    upsert(conn, t.entity_aliases, [{
        "entity_type": entity_type, "league": league, "source": source,
        "source_key": normalize(source_key), "internal_id": internal_id, "method": method,
    }], ["entity_type", "league", "source", "source_key"], update=["internal_id", "method"])


def enqueue(conn: Connection, entity_type: str, league: str, source: str, source_key: str,
            context: dict | None = None) -> None:
    upsert(conn, t.id_review_queue, [{
        "entity_type": entity_type, "league": league, "source": source,
        "source_key": normalize(source_key), "context": context or {}, "status": "open",
    }], ["entity_type", "league", "source", "source_key"], update=[])


def resolve_or_enqueue(conn: Connection, entity_type: str, league: str, source: str, source_key: str,
                       context: dict | None = None) -> int | None:
    found = resolve(conn, entity_type, league, source, source_key)
    if found is None:
        enqueue(conn, entity_type, league, source, source_key, context)
    return found


def resolve_review_item(engine: Engine, item_id: int, internal_id: int | None) -> None:
    """Close a review item: map it (internal_id) or mark it ignored (None)."""
    q = t.id_review_queue
    with engine.begin() as conn:
        item = conn.execute(sa.select(q).where(q.c.id == item_id)).mappings().first()
        if item is None:
            raise ValueError(f"no review item {item_id}")
        if internal_id is not None:
            add_alias(conn, item["entity_type"], item["league"], item["source"], item["source_key"],
                      internal_id, method="review")
        conn.execute(q.update().where(q.c.id == item_id).values(
            status="resolved" if internal_id is not None else "ignored",
            resolved_internal_id=internal_id, resolved_at=datetime.now(timezone.utc),
        ))


def link_kalshi_events(engine: Engine, league: str) -> dict[str, int]:
    """Attach Kalshi game events (and their markets) to games by date and team codes.

    Needs team aliases with source "kalshi" (e.g. "DAL" -> Cowboys' team id). Events
    whose code can't be split, or whose teams/date match no single game, go to review.
    """
    e, g, m = t.kalshi_events, t.games, t.kalshi_markets
    stats = {"linked": 0, "queued": 0}
    with engine.begin() as conn:
        codes = set(conn.execute(
            sa.select(t.entity_aliases.c.source_key).where(
                t.entity_aliases.c.entity_type == "team", t.entity_aliases.c.league == league,
                t.entity_aliases.c.source == "kalshi",
            )
        ).scalars())
        known_codes = {c.upper() for c in codes}
        events = conn.execute(
            sa.select(e.c.ticker, e.c.game_date, e.c.teams_code, e.c.title).where(
                e.c.league == league, e.c.game_id.is_(None), e.c.game_date.is_not(None),
                e.c.teams_code.is_not(None),
            )
        ).all()
        for ev in events:
            # Game alias first (manual fixes win), then the team-code split.
            game_id = resolve(conn, "game", league, "kalshi", ev.ticker)
            if game_id is None:
                pair = split_teams_code(ev.teams_code, known_codes)
                if pair:
                    ids = [resolve(conn, "team", league, "kalshi", code) for code in pair]
                    day = datetime(ev.game_date.year, ev.game_date.month, ev.game_date.day, tzinfo=timezone.utc)
                    # US evening kickoffs fall on the next UTC day; allow a window.
                    matches = conn.execute(
                        sa.select(g.c.id).where(
                            g.c.league == league,
                            g.c.start_time >= day - timedelta(hours=12),
                            g.c.start_time < day + timedelta(hours=36),
                            sa.or_(
                                sa.and_(g.c.away_team_id == ids[0], g.c.home_team_id == ids[1]),
                                sa.and_(g.c.home_team_id == ids[0], g.c.away_team_id == ids[1]),
                            ),
                        )
                    ).scalars().all()
                    if len(matches) == 1:
                        game_id = matches[0]
            if game_id is None:
                enqueue(conn, "game", league, "kalshi", ev.ticker,
                        {"title": ev.title, "date": str(ev.game_date), "teams_code": ev.teams_code})
                stats["queued"] += 1
                continue
            conn.execute(e.update().where(e.c.ticker == ev.ticker).values(game_id=game_id))
            conn.execute(m.update().where(m.c.event_ticker == ev.ticker).values(game_id=game_id))
            stats["linked"] += 1
    return stats
