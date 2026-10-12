from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest

from picks_engine import grading
from picks_engine.live import espn

KICK = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)  # Dallas at Philadelphia, 1 PM Eastern
EVENT = "KXNFLGAME-26OCT18DALPHI"
PHI, DAL = f"{EVENT}-PHI", f"{EVENT}-DAL"


def ts(dt):
    return int(dt.timestamp())


def minute_candles(mid_cents, spread=2):
    """1-minute candles for the 90 minutes before kickoff, ending at kickoff."""
    end = ts(KICK)
    return [{"end_period_ts": end - 60 * i, "yes_bid": {"close": mid_cents - spread // 2},
             "yes_ask": {"close": mid_cents + spread // 2}} for i in range(0, 90)]


MARKETS = {
    PHI: {"ticker": PHI, "event_ticker": EVENT, "yes_sub_title": "Philadelphia", "title": "Dallas at Philadelphia Winner?",
          "result": "yes"},
    DAL: {"ticker": DAL, "event_ticker": EVENT, "yes_sub_title": "Dallas", "title": "Dallas at Philadelphia Winner?",
          "result": "no"},
    "KXMVECROSS-26OCT18ABC-X1": {"ticker": "KXMVECROSS-26OCT18ABC-X1", "event_ticker": "KXMVECROSS-26OCT18ABC",
                                 "title": "yes Philadelphia,yes Kansas City", "result": "",
                                 "mve_selected_legs": [{"event_ticker": EVENT, "market_ticker": PHI, "side": "yes"},
                                                       {"event_ticker": "KXNFLGAME-26OCT18KCBUF",
                                                        "market_ticker": "KXNFLGAME-26OCT18KCBUF-KC", "side": "yes"}]},
    "KXUCL-26-BAR": {"ticker": "KXUCL-26-BAR", "event_ticker": "KXUCL-26", "title": "Will Barcelona win the Champions League?",
                     "yes_sub_title": "Barcelona", "yes_bid": 23, "yes_ask": 25, "result": ""},
}
STARTS = {(EVENT, ("Dallas", "Philadelphia")): KICK,
          ("KXNFLGAME-26OCT18KCBUF", ("Buffalo", "Kansas City")): datetime(2026, 10, 18, 20, 25, tzinfo=timezone.utc)}


def lookups(books=None):
    def event(t):
        teams = {"KXNFLGAME-26OCT18KCBUF": ("Kansas City", "Buffalo")}.get(t)
        markets = [m for m in MARKETS.values() if m["event_ticker"] == t]
        if teams:
            markets = [{"ticker": f"{t}-KC", "event_ticker": t, "yes_sub_title": "Kansas City"},
                       {"ticker": f"{t}-BUF", "event_ticker": t, "yes_sub_title": "Buffalo"}]
        return {"event": {"event_ticker": t, "title": "x"}, "markets": markets}

    def start_time(league, day, teams):
        assert league == "NFL" and day == date(2026, 10, 18)
        return next((v for (e, tm), v in STARTS.items() if tuple(sorted(teams)) == tm), None)

    def candles(series, ticker, a, b, minutes):
        if minutes != 1:
            return []
        return minute_candles({PHI: 60, DAL: 40, "KXMVECROSS-26OCT18ABC-X1": 30}[ticker])

    return grading.Lookups(market=lambda t: MARKETS[t], event=event, candles=candles, start_time=start_time,
                           books_close=books or (lambda league, m, sib: None))


def fill(ticker, price, at, side="yes", action="buy", n=10, fee=None):
    raw = {"ticker": ticker, "side": side, "action": action, "count": n, f"{side}_price": price,
           "created_time": at.isoformat().replace("+00:00", "Z"), "is_taker": True}
    if fee is not None:
        raw["fee_cost"] = fee
    return grading.parse_fill(raw)


def test_parse_fill_fees():
    f = fill(PHI, 55, KICK)
    assert f.price == Decimal("0.55") and f.fee == Decimal(str(0.018))  # ceil(0.07*10*.55*.45)=18c over 10
    assert fill(PHI, 55, KICK, fee="0.12").fee == Decimal("0.012")  # the real fee, in dollars
    assert fill(PHI, 55, KICK, fee="12").fee == Decimal("0.012")  # or whole cents


def test_buy_below_the_closing_price_is_a_good_grade_even_if_it_lost():
    early = datetime(2026, 10, 16, 15, tzinfo=timezone.utc)
    s = grading.grade([fill(PHI, 52, early), fill(DAL, 45, early)], lookups())
    phi, dal = sorted(s.grades, key=lambda g: g.fill.ticker, reverse=True)
    assert phi.fill.ticker == PHI and phi.fair == pytest.approx(0.60) and phi.fair_source == "Kalshi's price at kickoff"
    assert phi.edge == pytest.approx((0.60 - 0.52 - 0.018) * 100) and phi.letter == "A" and phi.result == "won"
    assert dal.edge == pytest.approx((0.40 - 0.45 - 0.018) * 100) and dal.letter == "F" and dal.result == "lost"
    assert phi.start == KICK and phi.start_source == "ESPN"
    assert s.beat_close == 1 and s.contracts == 20
    assert s.expected == pytest.approx(phi.expected + dal.expected)
    assert s.actual == pytest.approx(10 * (1 - 0.538) + 10 * (0 - 0.468))
    assert s.luck == pytest.approx(s.actual - s.expected)


def test_in_game_bets_and_unknown_kickoffs_are_not_graded():
    late = datetime(2026, 10, 18, 18, tzinfo=timezone.utc)
    g = grading.grade([fill(PHI, 70, late)], lookups()).grades[0]
    assert not g.graded and "after the game started" in g.notes[0]


def test_pinnacle_closing_line_wins_over_kalshi():
    s = grading.grade([fill(PHI, 52, datetime(2026, 10, 17, tzinfo=timezone.utc))],
                      lookups(books=lambda league, m, sib: 0.65 if m["ticker"] == PHI else None))
    g = s.grades[0]
    assert g.fair == 0.65 and g.fair_source == "Pinnacle's closing line" and g.kalshi_close == pytest.approx(0.60)


def test_no_side_and_sells():
    early = datetime(2026, 10, 17, tzinfo=timezone.utc)
    no = grading.grade([fill(PHI, 38, early, side="no")], lookups()).grades[0]
    assert no.fair == pytest.approx(0.40) and no.result == "lost"  # NO on Philadelphia, which won
    sell = grading.grade([fill(PHI, 63, early, action="sell")], lookups()).grades[0]
    assert sell.edge == pytest.approx((0.63 - float(sell.fill.fee) - 0.60) * 100)  # sold above what it was worth


def test_combo_uses_the_first_legs_kickoff_and_futures_use_the_price_now():
    early = datetime(2026, 10, 17, tzinfo=timezone.utc)
    s = grading.grade([fill("KXMVECROSS-26OCT18ABC-X1", 20, early), fill("KXUCL-26-BAR", 12, early)], lookups())
    combo, fut = sorted(s.grades, key=lambda g: g.kind)
    assert combo.kind == "combo" and combo.start == KICK and combo.fair == pytest.approx(0.30)
    assert fut.kind == "future" and fut.fair == pytest.approx(0.24) and "price has moved" in fut.notes[0]


def test_espn_scoreboard():
    data = {"events": [{"competitions": [{"date": "2026-10-18T17:00Z", "competitors": [
        {"homeAway": "home", "team": {"displayName": "Philadelphia Eagles", "location": "Philadelphia",
                                      "name": "Eagles", "abbreviation": "PHI"}},
        {"homeAway": "away", "team": {"displayName": "Dallas Cowboys", "location": "Dallas", "name": "Cowboys",
                                      "abbreviation": "DAL"}}]}]}]}
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json=data if request.url.params["dates"] == "20261018" else {"events": []})
    espn.clear()
    t = httpx.MockTransport(handler)
    assert espn.find_start("NFL", date(2026, 10, 18), ["Philadelphia", "Dallas"], transport=t) == KICK
    assert espn.find_start("NFL", date(2026, 10, 18), ["Philadelphia", "Dallas"], transport=t) == KICK
    assert len(seen) == 1 and "football/nfl" in str(seen[0])  # cached
    assert espn.find_start("NFL", date(2026, 10, 18), ["Philadelphia", "New York G"], transport=t) is None


def test_books_close_for_nfl_from_nflverse():
    csv_text = ("game_id,season,game_type,week,gameday,gametime,away_team,home_team,away_moneyline,home_moneyline\n"
                "2026_07_DAL_PHI,2026,REG,7,2026-10-18,13:00,DAL,PHI,170,-200\n")
    look = grading.books_close_lookup(lambda url: csv_text)
    p = look("NFL", MARKETS[PHI], [MARKETS[PHI], MARKETS[DAL]])
    assert p == pytest.approx(0.651, abs=0.005)
    assert look("NBA", MARKETS[PHI], []) is None


def test_grades_page(monkeypatch):
    from fastapi.testclient import TestClient
    from picks_engine.web import app as webapp
    import test_web

    for k, v in {"APP_PASSWORD": test_web.PASSWORD, "APP_TOTP_SECRET": test_web.TOTP, "KALSHI_ENV": "live",
                 "KALSHI_API_KEY_ID": "key-123", "KALSHI_PRIVATE_KEY": test_web.PEM,
                 "KALSHI_TRADING_BASE": "https://kalshi.test/trade-api/v2",
                 "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2"}.items():
        monkeypatch.setenv(k, v)
    ex = test_web.WebExchange()
    ex.fills = [{"ticker": PHI, "side": "yes", "action": "buy", "count": 10, "yes_price": 52, "is_taker": True,
                 "created_time": "2026-10-16T15:00:00Z", "trade_id": "t1"},
                {"ticker": DAL, "side": "yes", "action": "buy", "count": 5, "yes_price": 45, "is_taker": True,
                 "created_time": "2026-10-18T18:00:00Z", "trade_id": "t2"}]

    def market_api(request):
        path = request.url.path.split("/trade-api/v2")[1]
        if path.startswith("/markets/"):
            return httpx.Response(200, json={"market": MARKETS[path.split("/")[2]]})
        if path.startswith("/events/"):
            return httpx.Response(200, json={"event": {"title": "Dallas at Philadelphia"},
                                             "markets": [MARKETS[PHI], MARKETS[DAL]]})
        if path.endswith("/candlesticks"):
            return httpx.Response(200, json={"candlesticks": minute_candles(60 if PHI in path else 40)})
        return httpx.Response(404)

    def espn_api(request):
        return httpx.Response(200, json={"events": [{"competitions": [{"date": "2026-10-18T17:00Z", "competitors": [
            {"homeAway": "home", "team": {"displayName": "Philadelphia Eagles"}},
            {"homeAway": "away", "team": {"displayName": "Dallas Cowboys"}}]}]}]})

    espn.clear()
    app = webapp.create_app(trading_transport=httpx.MockTransport(ex.handler),
                            market_transport=httpx.MockTransport(market_api),
                            espn_transport=httpx.MockTransport(espn_api),
                            reference_transport=httpx.MockTransport(lambda r: httpx.Response(404)),
                            clock=lambda: datetime(2026, 10, 19, tzinfo=timezone.utc))
    web = TestClient(app, base_url="https://testserver")
    test_web.login(web)
    assert 'href="/grades"' in web.get("/account").text
    r = web.get("/grades")
    assert r.status_code == 200
    assert "Philadelphia wins" in r.text and "+6.2 points" in r.text and "Worth 60.0¢ at kickoff (per Kalshi)" in r.text
    assert "1 of 1" in r.text  # beat the closing price
    assert "after the game started" in r.text  # the in-game Dallas bet isn't graded
    assert "Won: +$4.62" in r.text
