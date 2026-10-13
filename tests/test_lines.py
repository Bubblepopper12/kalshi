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


def test_spread_team_found_by_ticker_code_when_names_differ():
    oe = soccer_event()
    model, main = model_for("BUNDESLIGA", "soccer", oe)
    m = {"ticker": "KXBUNDESLIGASPREAD-26OCT18FCBBVB-FCB2", "yes_sub_title": "Die Roten wins by more than 1.5 goals",
         "yes_ask": 50, "no_ask": 52}
    assert price_markets([m], "spread", "BUNDESLIGA", "soccer", oe, model, main) == []  # a name the books don't use: no match
    bets = price_markets([m], "spread", "BUNDESLIGA", "soccer", oe, model, main, code_sides={"FCB": "home"})
    assert bets and bets[0].fair == pytest.approx(model.wins_by_more_than("home", 1.5))


def test_asian_totals_are_read_like_the_books_settle_them():
    from picks_engine.pricing.models import fit_soccer

    base = fit_soccer(0.45, 0.27, 0.28, 2.5, 0.55)
    # The same game quoted on a whole line (refund on exactly 3) or a quarter line must give the same goals.
    for line in (2.25, 2.75, 3.0, 3.25):
        again = fit_soccer(0.45, 0.27, 0.28, line, base.book_over(line))
        assert again.home_rate + again.away_rate == pytest.approx(base.home_rate + base.away_rate, abs=0.01)
    assert base.book_over(3.0) < base.book_over(2.75) < base.total_over(2.5)
    assert base.book_over(3.0) > base.total_over(3.5)  # the refund on exactly 3 lifts the quoted chance


def test_nfl_margins_use_the_real_shape():
    from picks_engine.pricing.models import fit_points

    nfl, smooth = fit_points("NFL", None, -3.5, 0.5), fit_points("CFB", None, -3.5, 0.5)
    assert nfl.wins_by_more_than("home", 3.5) == pytest.approx(0.5, abs=0.005)
    # nflverse 2010-2026: a favourite covers by 3+ extra points ~38% of the time, not the bell curve's ~41%
    assert nfl.wins_by_more_than("home", 6.5) == pytest.approx(0.39, abs=0.015)
    assert nfl.home_win() == pytest.approx(0.62, abs=0.02)
    assert smooth.shape is None and nfl.shape is not None


def test_winner_no_side():
    from picks_engine.live.board import Choice, Game
    from picks_engine.live.lines import winner_no_bets

    g = Game("EPL", "moneyline", "KXEPLGAME-26OCT18ARSLIL", "Arsenal vs Lille", None, [
        Choice("T-ARS", "Arsenal", "Arsenal wins", Decimal("0.60"), Decimal("0.58"), Decimal("0.36"),
               book=0.70, books=["Pinnacle", "A", "B"], pinnacle=0.70),
        Choice("T-TIE", "Tie", "It ends in a tie", Decimal("0.20"), Decimal("0.18"), Decimal("0.82"),
               book=0.18, books=["Pinnacle", "A", "B"], pinnacle=0.18),
        Choice("T-LIL", "Lille", "Lille wins", Decimal("0.14"), Decimal("0.12"), Decimal("0.80"),
               book=0.12, books=["Pinnacle", "A", "B"], pinnacle=0.12)], matched=True)
    bets = {b.ticker: b for b in winner_no_bets(g, "EPL", "soccer")}
    assert bets["T-ARS"].headline == "Arsenal doesn't win (draw or Lille)" and bets["T-ARS"].side == "no"
    assert bets["T-ARS"].fair == pytest.approx(0.30) and bets["T-TIE"].headline == "Not a draw (either team wins)"
    lil = bets["T-LIL"]  # NO on Lille at 80c, worth 88c: a real edge on the books' own price
    assert judge_bet(lil, 0.03) and lil.strength == "Strong" and lil.pinnacle == pytest.approx(0.88)


def test_game_wide_disagreement_counts_against_the_edge():
    oe = soccer_event()
    model, main = model_for("BUNDESLIGA", "soccer", oe)

    def ladder(shift):  # Kalshi's over ladder, `shift` points below the model on every line
        out = []
        for line in (1.5, 2.5, 3.5, 4.5):
            mid = round((model.total_over(line) - shift) * 100)
            out.append({"ticker": f"T-{line}", "yes_sub_title": f"Over {line} goals scored", "floor_strike": line,
                        "yes_bid": mid - 1, "yes_ask": mid + 1, "no_ask": 101 - mid})
        return out

    bets = price_markets(ladder(0.07), "total", "BUNDESLIGA", "soccer", oe, model, main)
    over = next(b for b in bets if b.ticker == "T-2.5" and b.side == "yes")
    assert over.level_gap == pytest.approx(0.07, abs=0.01) and over.edge > 0.04
    assert not judge_bet(over, 0.03)  # ~5 points of edge, but Kalshi disagrees by ~7 on every line of the game
    lone = price_markets(ladder(0.0)[:1] + [dict(ladder(0.07)[1])] + ladder(0.0)[2:], "total", "BUNDESLIGA",
                         "soccer", oe, model, main)
    single = next(b for b in lone if b.ticker == "T-2.5" and b.side == "yes")
    assert single.level_gap < 0.02  # one cheap line against an agreeing ladder: no penalty


def test_nba_only_prices_lines_near_the_books():
    oe = {"home_team": "Orlando Magic", "away_team": "Cleveland Cavaliers", "commence_time": "2026-10-20T23:00:00Z",
          "bookmakers": [book(k, t, [
              {"key": "h2h", "outcomes": [{"name": "Orlando Magic", "price": -200}, {"name": "Cleveland Cavaliers", "price": 170}]},
              {"key": "spreads", "outcomes": [{"name": "Orlando Magic", "price": -110, "point": -5.5},
                                              {"name": "Cleveland Cavaliers", "price": -110, "point": 5.5}]},
              {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 214.5},
                                             {"name": "Under", "price": -110, "point": 214.5}]}])
              for k, t in (("pinnacle", "Pinnacle"), ("b2", "B2"), ("b3", "B3"))]}
    model, main = model_for("NBA", "basketball", oe)
    assert main.spread == -5.5 and main.total == 214.5
    mk = lambda t, line: {"ticker": f"KXNBASPREAD-X-ORL{t}", "yes_sub_title": f"Orlando wins by over {line} points",
                          "floor_strike": line, "yes_ask": 40, "no_ask": 62}  # noqa: E731
    near = price_markets([mk(7, 7.5)], "spread", "NBA", "basketball", oe, model, main, code_sides={"ORL": "home"})
    far = price_markets([mk(19, 18.5)], "spread", "NBA", "basketball", oe, model, main, code_sides={"ORL": "home"})
    assert near and not far
    exact = price_markets([mk(6, 5.5)], "spread", "NBA", "basketball", oe, model, main, code_sides={"ORL": "home"})
    assert exact[0].exact and exact[0].fair == pytest.approx(0.5, abs=0.01)
    tot = lambda line: {"ticker": f"T{line}", "yes_sub_title": f"Over {line} points", "floor_strike": line,  # noqa: E731
                        "yes_ask": 50, "no_ask": 52}
    assert price_markets([tot(218.5)], "total", "NBA", "basketball", oe, model, main)
    assert not price_markets([tot(230.5)], "total", "NBA", "basketball", oe, model, main)
