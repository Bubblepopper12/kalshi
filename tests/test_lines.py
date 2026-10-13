from decimal import Decimal

import pytest

from picks_engine.live.lines import judge_bet, main_lines, model_for, parse_line, price_markets
from picks_engine.pricing.models import fit_points, fit_soccer


def book(key, title, markets):
    return {"key": key, "title": title, "markets": markets}


def soccer_event(over_price=(-120, 100)):
    h2h = {"key": "h2h", "outcomes": [{"name": "Bayern Munich", "price": -250}, {"name": "Borussia Dortmund", "price": 600},
                                      {"name": "Draw", "price": 420}]}
    totals = {"key": "totals", "outcomes": [{"name": "Over", "price": over_price[0], "point": 3.5},
                                            {"name": "Under", "price": over_price[1], "point": 3.5}]}
    return {"home_team": "Bayern Munich", "away_team": "Borussia Dortmund", "commence_time": "2026-10-18T16:30:00Z",
            "bookmakers": [book(k, t, [h2h, totals]) for k, t in (("pinnacle", "Pinnacle"), ("b2", "Book 2"),
                                                                    ("b3", "Book 3"))]}


def test_models_reproduce_the_books():
    m = fit_soccer(0.55, 0.25, 0.20, 2.5, 0.55)
    assert m.home_win() / (m.home_win() + m.away_win()) == pytest.approx(0.55 / 0.75, abs=0.002)
    assert m.total_over(2.5) == pytest.approx(0.55, abs=0.002)
    assert fit_soccer(0.55, 0.25, 0.20).draw() == pytest.approx(0.25, abs=0.002)  # no totals: draw sets the goals
    p = fit_points("NFL", None, -6.5, 0.5, 44.5, 0.5)
    assert p.wins_by_more_than("home", 6.5) == pytest.approx(0.5, abs=1e-6)
    assert p.total_over(44.5) == pytest.approx(0.5, abs=1e-6)
    assert p.wins_by_more_than("home", 10.5) < 0.5 < p.wins_by_more_than("home", 2.5)


def test_parse_kalshi_lines():
    assert parse_line({"yes_sub_title": "Bayern Munich wins by more than 2.5 goals"}, "spread") == \
        {"team": "Bayern Munich", "line": 2.5}
    assert parse_line({"yes_sub_title": "Philadelphia wins by over 6.5 points", "floor_strike": 6.5}, "spread") == \
        {"team": "Philadelphia", "line": 6.5}
    assert parse_line({"yes_sub_title": "Arsenal wins by at least 2 goals"}, "spread") == {"team": "Arsenal", "line": 1.5}
    assert parse_line({"yes_sub_title": "Over 3.5 goals scored"}, "total") == {"line": 3.5}
    assert parse_line({"title": "Both Teams To Score?"}, "btts") == {}
    assert parse_line({"yes_sub_title": "Something else"}, "spread") is None


def test_main_lines_and_pricing_both_sides():
    oe = soccer_event()
    main = main_lines(oe)
    assert main.total == 3.5 and main.p_over == pytest.approx(0.524, abs=0.01) and len(main.books) == 3
    model, main = model_for("BUNDESLIGA", "soccer", oe)
    markets = [
        {"ticker": "T-OV35", "yes_sub_title": "Over 3.5 goals scored", "floor_strike": 3.5, "yes_ask": 40, "no_ask": 62},
        {"ticker": "S-BAY25", "yes_sub_title": "Bayern Munich wins by more than 2.5 goals", "yes_ask": 30, "no_ask": 72},
        {"ticker": "S-DOR15", "yes_sub_title": "Borussia Dortmund wins by more than 1.5 goals", "yes_ask": 5, "no_ask": 96},
    ]
    totals = price_markets(markets[:1], "total", "BUNDESLIGA", "soccer", oe, model, main)
    over, under = totals
    assert over.headline == "Over 3.5 goals" and under.headline == "Under 3.5 goals" and under.side == "no"
    assert over.exact and over.fair + under.fair == pytest.approx(1)
    assert over.fair == pytest.approx(main.p_over, abs=0.005)  # the model reproduces the books' own line
    assert over.edge == pytest.approx(over.fair - 0.40 - float(over.fee))
    assert judge_bet(over, 0.03) and over.strength == "Strong"  # ~52% for 40c + fee: a big edge on the books' line
    spread = price_markets(markets[1:], "spread", "BUNDESLIGA", "soccer", oe, model, main)
    bay = next(b for b in spread if b.ticker == "S-BAY25" and b.side == "yes")
    assert bay.headline == "Bayern Munich wins by 3+ goals" and not bay.exact
    dor_no = next(b for b in spread if b.ticker == "S-DOR15" and b.side == "no")
    assert dor_no.headline == "Borussia Dortmund doesn't win by 2+ goals" and dor_no.fair > 0.95


def test_model_lines_need_a_bigger_edge():
    oe = soccer_event()
    model, main = model_for("BUNDESLIGA", "soccer", oe)
    fair = model.both_score()
    ask = Decimal(str(round(fair - 0.05, 2)))  # ~4 points of edge after the fee: enough for a book line, not a model one
    b = price_markets([{"ticker": "B", "title": "Both Teams To Score?", "yes_ask": int(ask * 100), "no_ask": 99}],
                      "btts", "BUNDESLIGA", "soccer", oe, model, main)[0]
    assert 0.03 <= b.edge < 0.05 and not judge_bet(b, 0.03)


def test_picks_page_shows_totals_and_spreads(monkeypatch):
    from datetime import datetime, timezone

    import httpx
    from fastapi.testclient import TestClient

    import test_web
    from picks_engine.web import app as webapp

    for k, v in {"APP_PASSWORD": test_web.PASSWORD, "APP_TOTP_SECRET": test_web.TOTP, "KALSHI_ENV": "live",
                 "ODDS_API_KEY": "odds", "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2"}.items():
        monkeypatch.setenv(k, v)
    for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(k, raising=False)
    code = "26OCT18BAYDOR"
    events = {
        "KXBUNDESLIGAGAME": [{"event_ticker": f"KXBUNDESLIGAGAME-{code}", "title": "Bayern Munich vs Dortmund", "markets": [
            {"ticker": f"KXBUNDESLIGAGAME-{code}-BAY", "yes_sub_title": "Bayern Munich", "yes_ask": 72, "no_ask": 30},
            {"ticker": f"KXBUNDESLIGAGAME-{code}-DOR", "yes_sub_title": "Dortmund", "yes_ask": 14, "no_ask": 88},
            {"ticker": f"KXBUNDESLIGAGAME-{code}-TIE", "yes_sub_title": "Tie", "yes_ask": 19, "no_ask": 83}]}],
        "KXBUNDESLIGATOTAL": [{"event_ticker": f"KXBUNDESLIGATOTAL-{code}", "markets": [
            {"ticker": f"KXBUNDESLIGATOTAL-{code}-3", "yes_sub_title": "Over 3.5 goals scored", "floor_strike": 3.5,
             "yes_ask": 40, "no_ask": 62}]}],
        "KXBUNDESLIGASPREAD": [{"event_ticker": f"KXBUNDESLIGASPREAD-{code}", "markets": [
            {"ticker": f"KXBUNDESLIGASPREAD-{code}-BAY2", "yes_sub_title": "Bayern Munich wins by more than 1.5 goals",
             "yes_ask": 50, "no_ask": 52}]}],
        "KXBUNDESLIGABTTS": [],
    }

    def kalshi(request):
        path = request.url.path.split("/trade-api/v2")[1]
        if path == "/series":
            return httpx.Response(200, json={"series": [{"ticker": t, "title": "Bundesliga", "category": "Sports"}
                                                        for t in events]})
        if path == "/events":
            return httpx.Response(200, json={"events": events.get(request.url.params["series_ticker"], []),
                                             "cursor": ""})
        return httpx.Response(404)

    asked = []

    def odds(request):
        asked.append(request.url.params["markets"])
        ev = soccer_event()
        ev["commence_time"] = "2026-10-18T16:30:00Z"
        return httpx.Response(200, json=[ev], headers={"x-requests-remaining": "300"})

    app = webapp.create_app(market_transport=httpx.MockTransport(kalshi), odds_transport=httpx.MockTransport(odds),
                            clock=lambda: datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
    web = TestClient(app, base_url="https://testserver")
    test_web.login(web)
    r = web.get("/?league=BUNDESLIGA")
    assert asked == ["h2h,totals"]
    best = r.text.split("Every game")[0]
    assert "Over 3.5 goals" in best and 'data-kind="total"' in best and 'data-kindchip="total"' in best
    assert "/bet?ticker=KXBUNDESLIGATOTAL-26OCT18BAYDOR-3&amp;side=yes" in best
    # Bayern -1.5 at 50c/52c is about fair (no 5-point model edge on either side), so it isn't a pick.
    assert 'data-kind="spread"' not in best
    with open(__import__("os").environ.get("SLIPS_HTML", "/dev/null"), "w") as fh:
        fh.write(r.text)
