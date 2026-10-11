from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from picks_engine.board import queries
from picks_engine.db import schema as t
from picks_engine.ids.mapping import add_alias, link_kalshi_events, resolve_review_item
from picks_engine.kalshi import sync as ks
from picks_engine.picks import Backing, evaluate
from picks_engine.picks.store import record_decision, save_suggestions
from tests_helpers import make_candidate


def _teams_and_game(engine):
    with engine.begin() as conn:
        dal = conn.execute(t.teams.insert().values(league="NFL", name="Dallas Cowboys", abbreviation="DAL")).inserted_primary_key[0]
        phi = conn.execute(t.teams.insert().values(league="NFL", name="Philadelphia Eagles", abbreviation="PHI")).inserted_primary_key[0]
        kc = conn.execute(t.teams.insert().values(league="NFL", name="Kansas City Chiefs", abbreviation="KC")).inserted_primary_key[0]
        game = conn.execute(t.games.insert().values(
            league="NFL", season=2026, home_team_id=phi, away_team_id=dal,
            start_time=datetime(2026, 10, 19, 0, 20, tzinfo=timezone.utc))).inserted_primary_key[0]
        for code, tid in (("DAL", dal), ("PHI", phi), ("KC", kc)):
            add_alias(conn, "team", "NFL", "kalshi", code, tid)
    return game


def test_link_events_and_review_queue(engine, client):
    ks.sync_league(engine, client, "NFL")
    game = _teams_and_game(engine)
    stats = link_kalshi_events(engine, "NFL")
    # DALPHI (game + spread events) link; KCBUF has no BUF alias and no game -> review.
    assert stats == {"linked": 2, "queued": 1}
    with engine.connect() as conn:
        linked = conn.execute(sa.select(sa.func.count()).select_from(t.kalshi_markets)
                              .where(t.kalshi_markets.c.game_id == game)).scalar()
        assert linked == 3
        item = conn.execute(sa.select(t.id_review_queue)).mappings().one()
        assert item["source_key"] == "kxnflgame26oct18kcbuf"
    resolve_review_item(engine, item["id"], game)
    assert link_kalshi_events(engine, "NFL") == {"linked": 1, "queued": 0}


def test_board_decisions_and_report(engine, client, fake):
    ks.sync_league(engine, client, "NFL")
    s = evaluate(make_candidate(backings=[Backing("sharp", "proven", 1.5, True)]))
    other = evaluate(make_candidate(market_ticker="KXNFLGAME-26OCT18KCBUF-KC", model_prob=0.70, market_prob=0.68))
    ids = save_suggestions(engine, "run-1", [s, other])
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    rows = queries.board(engine, since)
    assert [r["market_ticker"] for r in rows] == ["KXNFLGAME-26OCT18KCBUF-KC", "KXNFLGAME-26OCT18DALPHI-PHI"]
    assert [r["market_ticker"] for r in queries.board(engine, since, proven_only=True)] == ["KXNFLGAME-26OCT18DALPHI-PHI"]

    with pytest.raises(ValueError):
        record_decision(engine, ids[0], "took")  # needs price and size
    record_decision(engine, ids[0], "took", 0.54, 100)
    record_decision(engine, ids[1], "pass")
    rows = {r["id"]: r for r in queries.board(engine, since)}
    assert rows[ids[0]]["decision"] == "took" and rows[ids[1]]["decision"] == "pass"
    assert queries.exposure_today(engine) == 54.0

    with engine.begin() as conn:
        conn.execute(t.kalshi_markets.update().where(t.kalshi_markets.c.ticker == s.market_ticker).values(result="yes"))
        conn.execute(t.kalshi_markets.update().where(t.kalshi_markets.c.ticker == other.market_ticker).values(result="no"))
    report = queries.weekly_report(engine, since, datetime.now(timezone.utc) + timedelta(minutes=1))
    assert report["board"]["wins"] == 1 and report["board"]["losses"] == 1
    assert report["logan"] == {"wins": 1, "losses": 0, "units": 46.0}


def test_markets_with_prices(engine, client):
    ks.sync_league(engine, client, "NFL")
    rows = queries.markets_with_prices(engine, "NFL", ["moneyline"])
    assert len(rows) == 4 and all(r["yes_ask"] is not None for r in rows)
