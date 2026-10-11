"""Kalshi listing sync, price snapshots, order books and the Phase 1 gate check."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from ..db import schema as t
from ..db.session import upsert
from .classify import classify, parse_event_ticker
from .client import KalshiReadOnlyClient, count_field, price_field
from .leagues import get_league

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class SyncStats:
    series: int = 0
    events: int = 0
    markets: int = 0
    snapshots: int = 0
    orderbooks: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__ | {"by_type": dict(self.by_type)}


# ---------------------------------------------------------------- discovery


def discover_series(client: KalshiReadOnlyClient, league_code: str) -> list[dict]:
    """Every series in Kalshi's live listings that belongs to the league."""
    league = get_league(league_code)
    seen: dict[str, dict] = {}
    # Sports first; then everything, because some futures sit outside the Sports category.
    for category in ("Sports", None):
        for s in client.series(category=category):
            ticker = s.get("ticker")
            if ticker and ticker not in seen and league.matches(s):
                seen[ticker] = s
    return list(seen.values())


def series_row(s: dict, league_code: str, now: datetime) -> dict:
    return {
        "ticker": s["ticker"],
        "league": league_code,
        "title": s.get("title"),
        "category": s.get("category"),
        "frequency": s.get("frequency"),
        "tags": s.get("tags") or [],
        "market_type": classify(s["ticker"], s.get("title") or ""),
        "synced_at": now,
    }


def event_row(e: dict, league_code: str, now: datetime) -> dict:
    game_date, teams = parse_event_ticker(e["event_ticker"])
    return {
        "ticker": e["event_ticker"],
        "series_ticker": e.get("series_ticker") or e["event_ticker"].split("-")[0],
        "league": league_code,
        "title": e.get("title"),
        "sub_title": e.get("sub_title"),
        "game_date": game_date,
        "teams_code": teams,
        "synced_at": now,
    }


def market_row(m: dict, series_ticker: str, series_type: str, league_code: str, now: datetime) -> dict:
    return {
        "ticker": m["ticker"],
        "event_ticker": m.get("event_ticker") or "",
        "series_ticker": series_ticker,
        "league": league_code,
        "market_type": series_type if series_type != "other" else classify("", m.get("title") or ""),
        "title": m.get("title"),
        "yes_sub_title": m.get("yes_sub_title"),
        "no_sub_title": m.get("no_sub_title"),
        "status": m.get("status"),
        "open_time": _parse_ts(m.get("open_time")),
        "close_time": _parse_ts(m.get("close_time")),
        "expiration_time": _parse_ts(m.get("expiration_time") or m.get("expected_expiration_time")),
        "result": m.get("result") or "",
        "rules_primary": m.get("rules_primary"),
        "rules_secondary": m.get("rules_secondary"),
        "last_synced_at": now,
        "raw": m,
    }


def snapshot_row(m: dict, now: datetime) -> dict:
    return {
        "market_ticker": m["ticker"],
        "ts": now,
        "yes_bid": price_field(m, "yes_bid"),
        "yes_ask": price_field(m, "yes_ask"),
        "no_bid": price_field(m, "no_bid"),
        "no_ask": price_field(m, "no_ask"),
        "last_price": price_field(m, "last_price"),
        "volume": count_field(m, "volume"),
        "volume_24h": count_field(m, "volume_24h"),
        "open_interest": count_field(m, "open_interest"),
    }


# ---------------------------------------------------------------- jobs


def _record_run(engine: Engine, job: str, league: str, started: datetime, status: str,
                stats: dict | None = None, error: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            t.sync_runs.insert().values(
                job=job, league=league, started_at=started, finished_at=utcnow(),
                status=status, stats=stats, error=error,
            )
        )


def sync_league(engine: Engine, client: KalshiReadOnlyClient, league_code: str,
                status: str = "open", with_snapshots: bool = True) -> SyncStats:
    """Daily listing sync: series, events and markets for one league, plus a price snapshot."""
    league_code = get_league(league_code).code
    started = utcnow()
    stats = SyncStats()
    try:
        series = discover_series(client, league_code)
        now = utcnow()
        series_rows = [series_row(s, league_code, now) for s in series]
        with engine.begin() as conn:
            stats.series = upsert(conn, t.kalshi_series, series_rows, ["ticker"])

        for srow in series_rows:
            event_rows, market_rows, snaps = [], [], []
            for e in client.events(srow["ticker"], status=status, with_nested_markets=True):
                e.setdefault("series_ticker", srow["ticker"])
                event_rows.append(event_row(e, league_code, now))
                for m in e.get("markets") or []:
                    m.setdefault("event_ticker", e["event_ticker"])
                    row = market_row(m, srow["ticker"], srow["market_type"], league_code, now)
                    market_rows.append(row)
                    stats.by_type[row["market_type"]] = stats.by_type.get(row["market_type"], 0) + 1
                    if with_snapshots:
                        snaps.append(snapshot_row(m, now))
            with engine.begin() as conn:
                stats.events += upsert(conn, t.kalshi_events, event_rows, ["ticker"],
                                       update=["title", "sub_title", "game_date", "teams_code", "synced_at"])
                stats.markets += upsert(
                    conn, t.kalshi_markets, market_rows, ["ticker"],
                    update=[c for c in market_rows[0] if c not in ("ticker",)] if market_rows else None,
                )
                stats.snapshots += upsert(conn, t.kalshi_price_snapshots, snaps,
                                          ["market_ticker", "ts"], update=[])
            log.info("%s: %d events, %d markets", srow["ticker"], len(event_rows), len(market_rows))
    except Exception as exc:
        _record_run(engine, "kalshi_sync", league_code, started, "failed", stats.as_dict(), repr(exc))
        raise
    _record_run(engine, "kalshi_sync", league_code, started, "ok", stats.as_dict())
    return stats


def snapshot_prices(engine: Engine, client: KalshiReadOnlyClient, league_code: str) -> SyncStats:
    """The 5-minute job: one paginated /markets call per known series, one snapshot row per open market.

    Markets that appeared since the last daily sync are inserted too, so nothing is missed.
    """
    league_code = get_league(league_code).code
    started = utcnow()
    stats = SyncStats()
    with engine.connect() as conn:
        series_rows = conn.execute(
            sa.select(t.kalshi_series.c.ticker, t.kalshi_series.c.market_type)
            .where(t.kalshi_series.c.league == league_code)
        ).all()
        known = set(conn.execute(
            sa.select(t.kalshi_markets.c.ticker).where(t.kalshi_markets.c.league == league_code)
        ).scalars())
    try:
        for series_ticker, series_type in series_rows:
            now = utcnow()
            snaps, new_markets, new_events = [], [], {}
            for m in client.markets(series_ticker=series_ticker, status="open"):
                snaps.append(snapshot_row(m, now))
                if m["ticker"] not in known:
                    new_markets.append(market_row(m, series_ticker, series_type, league_code, now))
                    ev = m.get("event_ticker") or ""
                    if ev:
                        new_events[ev] = event_row({"event_ticker": ev, "series_ticker": series_ticker},
                                                   league_code, now)
            with engine.begin() as conn:
                upsert(conn, t.kalshi_events, new_events.values(), ["ticker"], update=[])
                stats.markets += upsert(conn, t.kalshi_markets, new_markets, ["ticker"])
                stats.snapshots += upsert(conn, t.kalshi_price_snapshots, snaps,
                                          ["market_ticker", "ts"], update=[])
            stats.series += 1
    except Exception as exc:
        _record_run(engine, "kalshi_snapshot", league_code, started, "failed", stats.as_dict(), repr(exc))
        raise
    _record_run(engine, "kalshi_snapshot", league_code, started, "ok", stats.as_dict())
    return stats


def snapshot_orderbooks(engine: Engine, client: KalshiReadOnlyClient, tickers: Iterable[str]) -> int:
    """Store full books for the given markets (board candidates; one API call each)."""
    now = utcnow()
    rows = []
    for ticker in tickers:
        book = client.orderbook(ticker)
        rows.append({"market_ticker": ticker, "ts": now, **book.to_json()})
    with engine.begin() as conn:
        return upsert(conn, t.kalshi_orderbook_snapshots, rows, ["market_ticker", "ts"], update=[])


def refresh_settlements(engine: Engine, client: KalshiReadOnlyClient, league_code: str) -> int:
    """Pull results for markets we hold as open/closed whose close time has passed."""
    league_code = get_league(league_code).code
    m = t.kalshi_markets
    with engine.connect() as conn:
        tickers = conn.execute(
            sa.select(m.c.ticker).where(
                m.c.league == league_code,
                m.c.status.notin_(["settled", "finalized"]),
                m.c.close_time < utcnow(),
            )
        ).scalars().all()
    updated = 0
    for ticker in tickers:
        data = client.market(ticker)
        if not data:
            continue
        with engine.begin() as conn:
            conn.execute(
                m.update().where(m.c.ticker == ticker).values(
                    status=data.get("status"), result=data.get("result") or "", last_synced_at=utcnow()
                )
            )
        updated += 1
    return updated


# ---------------------------------------------------------------- gate


@dataclass
class GateReport:
    league: str
    live_open: int
    in_db: int
    missing: list[str]

    @property
    def passed(self) -> bool:
        return self.live_open > 0 and not self.missing

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [f"Phase 1 gate ({self.league}): {verdict}",
                 f"  open game markets on Kalshi: {self.live_open}",
                 f"  of those in the database:    {self.in_db}"]
        if self.live_open == 0:
            lines.append("  no open game markets found live; re-run when the league has games listed")
        if self.missing:
            lines.append(f"  missing ({len(self.missing)}): " + ", ".join(self.missing[:20])
                         + (" ..." if len(self.missing) > 20 else ""))
        return "\n".join(lines)


GAME_MARKET_TYPES = ("moneyline", "spread", "total")


def phase1_gate(engine: Engine, client: KalshiReadOnlyClient, league_code: str = "NFL") -> GateReport:
    """Gate: every open game market (moneyline, spread, total) on Kalshi is in the database."""
    league_code = get_league(league_code).code
    live: set[str] = set()
    for s in discover_series(client, league_code):
        if classify(s["ticker"], s.get("title") or "") not in GAME_MARKET_TYPES:
            continue
        live.update(m["ticker"] for m in client.markets(series_ticker=s["ticker"], status="open"))
    with engine.connect() as conn:
        stored = set(conn.execute(
            sa.select(t.kalshi_markets.c.ticker).where(t.kalshi_markets.c.league == league_code)
        ).scalars())
    missing = sorted(live - stored)
    return GateReport(league_code, len(live), len(live) - len(missing), missing)
