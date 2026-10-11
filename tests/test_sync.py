from datetime import timedelta

import sqlalchemy as sa

from picks_engine.db import schema as t
from picks_engine.kalshi import sync as ks


def test_discover_only_league_series(client):
    tickers = {s["ticker"] for s in ks.discover_series(client, "NFL")}
    assert tickers == {"KXNFLGAME", "KXNFLSPREAD", "KXSB"}


def test_sync_league_stores_everything(engine, client):
    stats = ks.sync_league(engine, client, "nfl")
    assert stats.series == 3
    assert stats.markets == 6
    assert stats.snapshots == 6
    assert stats.by_type == {"moneyline": 4, "spread": 1, "future": 1}
    with engine.connect() as conn:
        ev = conn.execute(sa.select(t.kalshi_events).where(
            t.kalshi_events.c.ticker == "KXNFLGAME-26OCT18DALPHI")).mappings().one()
        assert str(ev["game_date"]) == "2026-10-18" and ev["teams_code"] == "DALPHI"
        snap = conn.execute(sa.select(t.kalshi_price_snapshots).where(
            t.kalshi_price_snapshots.c.market_ticker == "KXNFLGAME-26OCT18KCBUF-KC")).mappings().one()
        assert float(snap["yes_ask"]) == 0.61 and float(snap["no_ask"]) == 0.40
        run = conn.execute(sa.select(t.sync_runs)).mappings().one()
        assert run["status"] == "ok" and run["job"] == "kalshi_sync"


def test_resync_is_idempotent_and_keeps_links(engine, client):
    ks.sync_league(engine, client, "NFL")
    with engine.begin() as conn:
        conn.execute(t.kalshi_markets.update().values(first_seen_at=sa.func.now()))
    ks.sync_league(engine, client, "NFL")
    with engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(t.kalshi_markets)).scalar() == 6


def test_snapshot_picks_up_new_markets(engine, client, fake):
    ks.sync_league(engine, client, "NFL")
    fake.markets["KXNFLGAME"].append(
        {**fake.markets["KXNFLGAME"][0], "ticker": "KXNFLGAME-26OCT19NYGNYJ-NYG",
         "event_ticker": "KXNFLGAME-26OCT19NYGNYJ"})
    stats = ks.snapshot_prices(engine, client, "NFL")
    assert stats.markets == 1 and stats.snapshots == 7
    with engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(t.kalshi_price_snapshots)).scalar() == 13
        ev = conn.execute(sa.select(t.kalshi_events.c.teams_code).where(
            t.kalshi_events.c.ticker == "KXNFLGAME-26OCT19NYGNYJ")).scalar()
        assert ev == "NYGNYJ"


def test_phase1_gate(engine, client, fake):
    report = ks.phase1_gate(engine, client, "NFL")
    assert not report.passed and report.live_open == 5 and report.in_db == 0
    ks.sync_league(engine, client, "NFL")
    report = ks.phase1_gate(engine, client, "NFL")
    assert report.passed, report.summary()
    fake.markets["KXNFLSPREAD"].append(
        {**fake.markets["KXNFLSPREAD"][0], "ticker": "KXNFLSPREAD-26OCT18DALPHI-PHI7"})
    report = ks.phase1_gate(engine, client, "NFL")
    assert report.missing == ["KXNFLSPREAD-26OCT18DALPHI-PHI7"]
    assert "FAIL" in report.summary()


def test_orderbooks_and_settlement(engine, client, fake):
    ks.sync_league(engine, client, "NFL")
    assert ks.snapshot_orderbooks(engine, client, ["KXNFLGAME-26OCT18DALPHI-PHI"]) == 1
    for m in fake.markets["KXNFLGAME"]:
        m.update(status="finalized", result="yes" if m["ticker"].endswith("PHI") else "no")
    with engine.begin() as conn:
        conn.execute(t.kalshi_markets.update().values(close_time=ks.utcnow() - timedelta(hours=1)))
    assert ks.refresh_settlements(engine, client, "NFL") == 6
    with engine.connect() as conn:
        res = conn.execute(sa.select(t.kalshi_markets.c.result).where(
            t.kalshi_markets.c.ticker == "KXNFLGAME-26OCT18DALPHI-PHI")).scalar()
    assert res == "yes"
