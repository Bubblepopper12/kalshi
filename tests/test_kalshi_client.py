from decimal import Decimal

import pytest

from picks_engine.kalshi.client import OrderBook, count_field, price_field


def test_refuses_anything_but_get(client):
    with pytest.raises(PermissionError):
        client._http.post("/portfolio/orders", json={"ticker": "X"})
    with pytest.raises(PermissionError):
        client._http.delete("/portfolio/orders/1")


def test_refuses_credentials(client):
    with pytest.raises(PermissionError):
        client._http.get("/series", headers={"KALSHI-ACCESS-KEY": "abc"})


def test_paginates(client, fake):
    events = list(client.events("KXNFLGAME"))
    assert [e["event_ticker"] for e in events] == ["KXNFLGAME-26OCT18DALPHI", "KXNFLGAME-26OCT18KCBUF"]
    assert len(list(client.markets(series_ticker="KXNFLGAME"))) == 4
    assert all(r.method == "GET" for r in fake.requests)


def test_price_fields_cents_and_dollars():
    assert price_field({"yes_ask": 54}, "yes_ask") == Decimal("0.54")
    assert price_field({"yes_ask": 54, "yes_ask_dollars": "0.5450"}, "yes_ask") == Decimal("0.5450")
    assert price_field({}, "yes_ask") is None
    assert count_field({"volume_fp": "12.00"}, "volume") == 12


def test_orderbook_asks_and_depth():
    book = OrderBook.from_api({"orderbook": {"yes": [[52, 300], [53, 150]], "no": [[44, 80], [45, 200]]}})
    assert book.best_bid("yes") == Decimal("0.53")
    assert book.best_ask("yes") == Decimal("0.55")  # 1 - best NO bid 0.45
    assert book.best_ask("no") == Decimal("0.47")
    assert book.depth_at_or_below("yes", Decimal("0.55")) == 200
    assert book.depth_at_or_below("yes", Decimal("0.56")) == 280


def test_orderbook_dollar_format():
    book = OrderBook.from_api({"orderbook_fp": {"yes_dollars": [["0.5300", "10.00"]], "no_dollars": [["0.4500", "7"]]}})
    assert book.best_ask("yes") == Decimal("0.55")
    assert book.depth_at_or_below("yes", Decimal("0.55")) == 7
