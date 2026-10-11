from __future__ import annotations

import json
import os
from urllib.parse import parse_qs

import httpx
import pytest

from picks_engine.db import get_engine, init_db, metadata
from picks_engine.kalshi import KalshiReadOnlyClient


@pytest.fixture
def engine(tmp_path):
    # Set PICKS_TEST_DATABASE_URL to run against Postgres; tables are dropped and recreated per test.
    url = os.environ.get("PICKS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    eng = get_engine(url)
    metadata.drop_all(eng)
    init_db(eng)
    yield eng
    eng.dispose()


def nfl_market(ticker, event, yes_bid=53, yes_ask=54, dollars=False, **extra):
    m = {
        "ticker": ticker, "event_ticker": event, "status": "active",
        "title": f"Market {ticker}", "yes_sub_title": ticker.split("-")[-1], "no_sub_title": "",
        "open_time": "2026-10-01T12:00:00Z", "close_time": "2026-10-19T03:00:00Z",
        "volume": 1200, "volume_24h": 300, "open_interest": 800, "last_price": yes_bid,
        "rules_primary": "Resolves Yes if ...", "result": "",
    }
    if dollars:
        m |= {"yes_bid_dollars": f"{yes_bid / 100:.4f}", "yes_ask_dollars": f"{yes_ask / 100:.4f}",
              "no_bid_dollars": f"{(100 - yes_ask) / 100:.4f}", "no_ask_dollars": f"{(100 - yes_bid) / 100:.4f}"}
    else:
        m |= {"yes_bid": yes_bid, "yes_ask": yes_ask, "no_bid": 100 - yes_ask, "no_ask": 100 - yes_bid}
    return m | extra


class FakeKalshi:
    """In-memory stand-in for the public Kalshi endpoints the engine reads."""

    def __init__(self):
        self.series = [
            {"ticker": "KXNFLGAME", "title": "Pro Football Game", "category": "Sports", "tags": ["Football"]},
            {"ticker": "KXNFLSPREAD", "title": "Pro Football Spread", "category": "Sports"},
            {"ticker": "KXSB", "title": "Super Bowl Champion", "category": "Sports"},
            {"ticker": "KXNBAGAME", "title": "Pro Basketball Game", "category": "Sports"},
            {"ticker": "KXWNBAGAME", "title": "WNBA Game", "category": "Sports"},
            {"ticker": "KXFEDDECISION", "title": "Fed decision", "category": "Economics"},
        ]
        ev1, ev2 = "KXNFLGAME-26OCT18DALPHI", "KXNFLGAME-26OCT18KCBUF"
        self.markets = {
            "KXNFLGAME": [
                nfl_market(f"{ev1}-DAL", ev1, 45, 46), nfl_market(f"{ev1}-PHI", ev1, 54, 55),
                nfl_market(f"{ev2}-KC", ev2, 60, 61, dollars=True), nfl_market(f"{ev2}-BUF", ev2, 39, 40, dollars=True),
            ],
            "KXNFLSPREAD": [nfl_market("KXNFLSPREAD-26OCT18DALPHI-PHI3", "KXNFLSPREAD-26OCT18DALPHI", 48, 50)],
            "KXSB": [nfl_market("KXSB-27-KC", "KXSB-27", 12, 13)],
        }
        self.requests: list[httpx.Request] = []
        self.page_size = 2

    def events_for(self, series):
        events: dict[str, dict] = {}
        for m in self.markets.get(series, []):
            ev = events.setdefault(m["event_ticker"], {
                "event_ticker": m["event_ticker"], "series_ticker": series,
                "title": m["event_ticker"], "sub_title": "", "markets": [],
            })
            ev["markets"].append(m)
        return list(events.values())

    def _page(self, items, key, params):
        start = int(params.get("cursor", ["0"])[0])
        page = items[start:start + self.page_size]
        nxt = start + self.page_size
        return {key: page, "cursor": str(nxt) if nxt < len(items) else ""}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = parse_qs(request.url.query.decode())
        path = request.url.path.split("/trade-api/v2")[-1]
        if path == "/series":
            cat = params.get("category", [None])[0]
            body = {"series": [s for s in self.series if cat is None or s["category"] == cat]}
        elif path == "/events":
            body = self._page(self.events_for(params["series_ticker"][0]), "events", params)
        elif path == "/markets":
            body = self._page(self.markets.get(params["series_ticker"][0], []), "markets", params)
        elif path.endswith("/orderbook"):
            body = {"orderbook": {"yes": [[52, 300], [53, 150]], "no": [[44, 80], [45, 200]]}}
        elif path.startswith("/markets/"):
            ticker = path.split("/")[-1]
            found = [m for ms in self.markets.values() for m in ms if m["ticker"] == ticker]
            body = {"market": found[0] if found else {}}
        else:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, content=json.dumps(body), headers={"content-type": "application/json"})


@pytest.fixture
def fake():
    return FakeKalshi()


@pytest.fixture
def client(fake):
    c = KalshiReadOnlyClient("https://kalshi.test/trade-api/v2", requests_per_second=0,
                             transport=httpx.MockTransport(fake.handler))
    yield c
    c.close()
