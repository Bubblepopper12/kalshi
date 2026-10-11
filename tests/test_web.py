import time
from datetime import datetime, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from picks_engine.web.app import COOKIE, create_app, sign, totp_code, totp_ok
from picks_engine.config import Settings
from test_trading import KEY, FakeExchange

PASSWORD = "correct horse battery"
TOTP = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # RFC 6238 test secret ("12345678901234567890")
TICKER = "KXNFLGAME-26OCT18DALPHI-PHI"
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()).decode()


class WebExchange(FakeExchange):
    def __init__(self):
        super().__init__(balance_cents=10_000)
        self.fills: list[dict] = []

    def handler(self, request):
        path = request.url.path.split("/trade-api/v2")[1]
        if request.method == "GET" and path == "/portfolio/fills":
            self._verify(request)
            return httpx.Response(200, json={"fills": self.fills})
        if request.method == "GET" and path == "/portfolio/positions":
            self._verify(request)
            return httpx.Response(200, json={"market_positions": [{"ticker": TICKER, "position": 3,
                                                                    "market_exposure": 162}]})
        if request.method == "GET" and path == "/portfolio/orders":
            self._verify(request)
            status = request.url.params.get("status")
            return httpx.Response(200, json={"orders": [o for o in self.orders.values()
                                                        if not status or o["status"] == status]})
        return super().handler(request)

    def _verify(self, request):
        import base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sig = base64.b64decode(request.headers["KALSHI-ACCESS-SIGNATURE"])
        msg = (request.headers["KALSHI-ACCESS-TIMESTAMP"] + request.method + request.url.path).encode()
        KEY.public_key().verify(sig, msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                      salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())


@pytest.fixture
def env(monkeypatch):
    for k, v in {"APP_PASSWORD": PASSWORD, "APP_TOTP_SECRET": TOTP, "KALSHI_ENV": "live", "KALSHI_API_KEY_ID": "key-123",
                 "KALSHI_PRIVATE_KEY": PEM.replace("\n", "\\n"),  # as some settings UIs store it
                 "KALSHI_TRADING_BASE": "https://kalshi.test/trade-api/v2",
                 "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("TRADING_HALTED", raising=False)


@pytest.fixture
def exchange():
    return WebExchange()


@pytest.fixture
def web(env, exchange, fake):
    app = create_app(trading_transport=httpx.MockTransport(exchange.handler),
                     market_transport=httpx.MockTransport(fake.handler))
    return TestClient(app, base_url="https://testserver")


def login(web):
    r = web.post("/login", data={"password": PASSWORD, "code": totp_code(TOTP)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def review(web, **form):
    data = {"ticker": TICKER, "side": "yes", "price": "54", "contracts": "2"} | form
    return web.post("/bet", data=data)


def token_from(html: str) -> str:
    return html.split('name="token" value="')[1].split('"')[0]


def test_locked_without_password(monkeypatch, exchange, fake):
    monkeypatch.setenv("APP_PASSWORD", "short")
    web = TestClient(create_app(), base_url="https://testserver")
    for path in ("/", "/account", "/login", "/find", "/bet"):
        assert "Setup needed" in web.get(path).text
    assert web.post("/login", data={"password": "short"}, follow_redirects=False).headers["location"] == "/login"


def test_login_required(web):
    for path in ("/", "/account", "/find", "/bet"):
        r = web.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert web.post("/send", data={"token": "x", "approve": "yes"}, follow_redirects=False).status_code == 303
    assert web.post("/bet", data={"ticker": TICKER}, follow_redirects=False).status_code == 303
    r = web.post("/login", data={"password": "wrong password!!"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=1"
    r = web.post("/login", data={"password": PASSWORD}, follow_redirects=False)  # no code
    assert r.headers["location"] == "/login?error=1"
    wrong = f"{(int(totp_code(TOTP)) + 1) % 1_000_000:06d}"
    r = web.post("/login", data={"password": PASSWORD, "code": wrong}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=1"
    r = web.post("/login", data={"password": PASSWORD, "code": totp_code(TOTP)}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_home_uses_plain_names(web, exchange):
    login(web)
    r = web.get("/account")
    assert "LIVE" in r.text and "$100.00" in r.text and r.headers["cache-control"] == "no-store"
    assert "Your bets" in r.text and "PHI wins" in r.text  # position named, not shown as a ticker
    assert "3 contracts · pays $3.00 if right" in r.text


def test_home_warns_when_no_cash(web, exchange):
    login(web)
    exchange.balance_cents = 0
    assert "You have no cash to bet with" in web.get("/account").text


def test_find_groups_games_and_hides_partial_markets(web, fake):
    fake.series.append({"ticker": "KXNFL2H", "title": "Pro Football 2nd Half Winner", "category": "Sports"})
    fake.markets["KXNFL2H"] = [dict(fake.markets["KXNFLGAME"][0], ticker="KXNFL2H-26OCT18DALPHI-PHI",
                                    event_ticker="KXNFL2H-26OCT18DALPHI")]
    fake.series.append({"ticker": "KXSBLGAME", "title": "Slovak Basketball League", "category": "Sports"})
    fake.markets["KXSBLGAME"] = [dict(fake.markets["KXNFLGAME"][0], ticker="KXSBLGAME-26OCT18BKSNV-BK",
                                      event_ticker="KXSBLGAME-26OCT18BKSNV")]
    login(web)
    r = web.get("/find")  # all leagues by default
    assert 'id="q"' in r.text and 'id="count"' in r.text  # search box; the count is filled in by the browser
    assert "KXNFLGAME-26OCT18DALPHI" in r.text and "KXNBAGAME" not in r.text
    assert "Sun, Oct 18" in r.text and "NFL" in r.text
    assert "/bet?ticker=KXNFLGAME-26OCT18DALPHI-PHI&amp;side=yes" in r.text
    assert "price=" not in r.text  # bet links never carry a price: the bet page starts from the live one
    assert "KXNFL2H" not in r.text  # half-game market hidden
    assert "KXSBL" not in r.text  # Slovak basketball is not the Super Bowl
    assert 'data-k="' in r.text and "sun sunday oct october 18" in r.text  # searchable by day
    assert web.get("/markets", follow_redirects=False).headers["location"].startswith("/find")


def test_stretched_prices_are_flagged(web, fake):
    for m in fake.markets["KXNFLGAME"]:
        if m["ticker"].endswith("KCBUF-KC"):
            m.update(yes_ask_dollars="0.7100")  # KC 71c + BUF 40c = $1.11
    login(web)
    r = web.get("/find?league=NFL")
    assert "Prices add up to $1.11" in r.text and 'data-thin="1"' in r.text


def test_choose_page_explains_the_bet(web):
    login(web)
    r = web.get(f"/bet?ticker={TICKER}&side=yes")
    assert "You're betting" in r.text and "PHI wins" in r.text and "55¢" in r.text
    r = web.get(f"/bet?ticker={TICKER}&side=no")
    assert "NOT: PHI wins" in r.text


def test_full_approval_flow(web, exchange):
    login(web)
    r = review(web)
    assert "Review your bet" in r.text and "real money" in r.text and exchange.posts == []
    assert "You pay at most</dt><dd>$1.12" in r.text  # 2 x 54c + fee 0.07 x 2 x .54 x .46 = 3.5c -> 4c
    assert "You get $2.00 back (profit $0.88)" in r.text and "You lose $1.12" in r.text
    token = token_from(r.text)

    r = web.post("/send", data={"token": token})
    assert "I approve this bet" in r.text and "Nothing was bought" in r.text and exchange.posts == []

    r = web.post("/send", data={"token": token, "approve": "yes"})
    assert "Waiting for a seller" in r.text and "PHI wins" in r.text
    assert exchange.posts[0]["count"] == 2 and exchange.posts[0]["yes_price"] == 54
    assert exchange.posts[0]["ticker"] == TICKER


def test_tampered_or_expired_tickets(web, exchange):
    login(web)
    token = token_from(review(web).text)
    body, mac = token.split(".")
    forged = sign(Settings(kalshi_private_key="other"), {"k": "ticket", "count": 99})  # wrong secret
    for bad in (forged, body + "x." + mac, "nonsense"):
        assert "expired or invalid" in web.post("/send", data={"token": bad, "approve": "yes"}).text
    s = Settings.from_env()
    old = sign(s, {"k": "ticket", "env": "live", "ticker": TICKER, "side": "yes", "count": 1,
                   "price": "0.54", "coid": "c", "exp": int(time.time()) - 1})
    assert "expired or invalid" in web.post("/send", data={"token": old, "approve": "yes"}).text
    session = web.cookies.get(COOKIE)
    assert "expired or invalid" in web.post("/send", data={"token": session, "approve": "yes"}).text
    assert exchange.posts == []


def test_limits_on_review_and_send(web, exchange, monkeypatch):
    login(web)
    assert "per-order limit" in review(web, contracts="40").text
    assert "outside the allowed" in review(web, price="99").text
    assert "ticker" in review(web, ticker="bad ticker!").text

    exchange.fills = [{"action": "buy", "side": "yes", "count": 15, "yes_price": 60, "ticker": TICKER}]
    r = web.post("/send", data={"token": token_from(review(web, contracts="5").text), "approve": "yes"})
    assert "daily limit" not in r.text  # 9 + 2.7 < 50 default
    monkeypatch.setenv("PICKS_MAX_DAILY_DOLLARS", "12")
    r = web.post("/send", data={"token": token_from(review(web, contracts="5").text), "approve": "yes"})
    assert "daily limit" in r.text

    monkeypatch.setenv("PICKS_MAX_DAILY_DOLLARS", "1000")
    monkeypatch.setenv("PICKS_MAX_OPEN_ORDERS", "1")
    r = web.post("/send", data={"token": token_from(review(web).text), "approve": "yes"})
    assert "waiting orders" in r.text
    assert len(exchange.posts) == 1


def test_halt_balance_and_env_switch(web, exchange, monkeypatch):
    login(web)
    token = token_from(review(web).text)
    monkeypatch.setenv("TRADING_HALTED", "1")
    assert "turned off" in web.post("/send", data={"token": token, "approve": "yes"}).text
    monkeypatch.delenv("TRADING_HALTED")
    exchange.balance_cents = 50
    assert "Add money on kalshi.com" in review(web).text  # warned on the review page already
    assert "Your cash is $0.50" in web.post("/send", data={"token": token, "approve": "yes"}).text
    exchange.balance_cents = 10_000
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_TRADING_BASE", "https://kalshi.test/trade-api/v2")
    assert "reviewed for LIVE" in web.post("/send", data={"token": token, "approve": "yes"}).text
    assert exchange.posts == []


def test_cancel(web, exchange):
    login(web)
    web.post("/send", data={"token": token_from(review(web).text), "approve": "yes"})
    home = web.get("/account").text
    assert "Waiting orders" in home and "Cancel" in home
    r = web.post("/cancel", data={"order_id": "ord-1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account"
    assert exchange.orders["ord-1"]["status"] == "canceled"
    assert "valid order" in web.post("/cancel", data={"order_id": "../x"}).text


def test_totp_matches_rfc6238():
    assert totp_code(TOTP, at=59) == "287082"
    assert totp_code(TOTP, at=1111111109) == "081804"
    assert totp_ok(TOTP, "287 082", at=59) and totp_ok(TOTP, "287082", at=80)  # one step of clock drift
    assert not totp_ok(TOTP, "287082", at=200) and not totp_ok(TOTP, "abc", at=59)


def test_keys_require_two_step(env, monkeypatch):
    monkeypatch.delenv("APP_TOTP_SECRET")
    web = TestClient(create_app(), base_url="https://testserver")
    assert "two-step code is required" in web.get("/login").text
    assert web.post("/login", data={"password": PASSWORD}, follow_redirects=False).headers["location"] == "/login"
    monkeypatch.setenv("APP_TOTP_SECRET", "not base32 !!")
    assert "valid authenticator secret" in web.get("/login").text
    monkeypatch.setenv("APP_PASSWORD", "fifteen chars..")
    assert "at least 16" in web.get("/login").text


def test_vercel_entry_loads_plain_defaults(monkeypatch, tmp_path):
    import runpy
    from pathlib import Path

    for k in ("KALSHI_ENV", "PICKS_MAX_ORDER_DOLLARS", "PICKS_MAX_DAILY_DOLLARS"):
        monkeypatch.setenv(k, "x")  # records the original value so it is restored afterwards
        monkeypatch.delenv(k)
    monkeypatch.setenv("PICKS_MAX_DAILY_DOLLARS", "7")  # set in Vercel: must win
    ns = runpy.run_path(str(Path(__file__).resolve().parent.parent / "api" / "index.py"))
    assert ns["app"] is not None
    s = Settings.from_env()
    assert s.kalshi_env == "live" and s.max_order_dollars == 5 and s.max_daily_dollars == 7
    defaults = (Path(__file__).resolve().parent.parent / "src/picks_engine/web/web.env").read_text().upper()
    assert "PASSWORD" not in defaults.replace("NEVER PUT PASSWORDS", "") and "PRIVATE_KEY=" not in defaults


def odds_feed(home="Philadelphia Eagles", away="Dallas Cowboys", books=((-200, 170), (-190, 160), (-210, 175))):
    calls = []

    def handler(request):
        calls.append(request)
        event = {"home_team": home, "away_team": away, "commence_time": "2026-10-18T17:00:00Z",
                 "bookmakers": [{"key": f"b{i}", "title": name, "markets": [{"key": "h2h", "outcomes": [
                     {"name": home, "price": h}, {"name": away, "price": a}]}]}
                     for i, ((h, a), name) in enumerate(zip(books, ("Pinnacle", "DraftKings", "FanDuel")))]}
        return httpx.Response(200, json=[event], headers={"x-requests-remaining": "480"})
    return handler, calls


def picks_web(fake, exchange, handler):
    # Real team names on the fake Kalshi game: Dallas at Philadelphia, PHI YES at 58c, DAL at 43c.
    for m in fake.markets["KXNFLGAME"]:
        if m["event_ticker"].endswith("DALPHI"):
            phi = m["ticker"].endswith("PHI")
            m.update(yes_sub_title="Philadelphia" if phi else "Dallas", yes_ask=58 if phi else 43)
    app = create_app(trading_transport=httpx.MockTransport(exchange.handler),
                     market_transport=httpx.MockTransport(fake.handler), odds_transport=httpx.MockTransport(handler),
                     clock=lambda: datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
    return TestClient(app, base_url="https://testserver")


def test_picks_page_shows_a_pick_with_reasons(env, exchange, fake, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "odds-key")
    handler, calls = odds_feed()
    web = picks_web(fake, exchange, handler)
    login(web)
    r = web.get("/")
    best = r.text.split("Every game")[0]
    assert "Best picks" in best and "Philadelphia wins" in best and "Dallas wins" not in best
    assert "cheaper on Kalshi" in best and "Sportsbooks say" in best and "65% chance" in best
    assert "Pinnacle" in best and "480 sportsbook lookups left" in r.text
    assert "/bet?ticker=KXNFLGAME-26OCT18DALPHI-PHI&amp;side=yes&amp;contracts=" in best and "price=" not in best
    every = r.text.split("Every game")[1]
    assert "Books 65%" in every and "Books 35%" in every  # both teams compared, even the non-pick
    assert "eagles" in every and "cowboys" in every  # nicknames are searchable
    assert len(calls) == 1 and calls[0].url.path.endswith("/americanfootball_nfl/odds")
    web.get("/")  # cached: no second sportsbook request
    web.get("/?refresh=1")  # too soon to refresh again
    assert len(calls) == 1


def test_picks_page_without_odds_key_explains_setup(web):
    login(web)
    r = web.get("/")
    assert "ODDS_API_KEY" in r.text and "the-odds-api.com" in r.text


def test_picks_page_no_strong_picks(env, exchange, fake, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "odds-key")
    handler, _ = odds_feed(books=((-130, 110), (-135, 115)))  # Philadelphia ~55%: Kalshi's 58c is too dear
    web = picks_web(fake, exchange, handler)
    login(web)
    assert "No strong picks in NFL right now" in web.get("/").text


def test_bet_link_prefills_contracts_and_price(web):
    login(web)
    r = web.get(f"/bet?ticker={TICKER}&side=yes&contracts=7&price=58")
    assert 'value="7"' in r.text and 'value="58"' in r.text


def test_all_leagues_survive_one_failing_league(env, exchange, fake):
    def flaky(request):
        if request.url.params.get("series_ticker") == "KXNBAGAME":
            return httpx.Response(503)
        return fake.handler(request)
    fake.series.append({"ticker": "KXNBAGAME", "title": "Pro Basketball Game", "category": "Sports"})
    app = create_app(trading_transport=httpx.MockTransport(exchange.handler), market_transport=httpx.MockTransport(flaky))
    web = TestClient(app, base_url="https://testserver")
    login(web)
    r = web.get("/find")
    assert "KXNFLGAME-26OCT18DALPHI" in r.text and "load NBA right now" in r.text


def test_search_in_address_bar_and_kept_across_filters(web):
    login(web)
    r = web.get("/find?q=kc")
    assert "KXNFLGAME-26OCT18KCBUF" in r.text and "KXNFLGAME-26OCT18DALPHI" not in r.text
    assert 'value="kc"' in r.text and 'class="keepq' in r.text


def test_in_progress_games_are_listed_not_compared(env, exchange, fake, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "odds-key")
    handler, _ = odds_feed()
    for m in fake.markets["KXNFLGAME"]:
        if m["event_ticker"].endswith("DALPHI"):
            m.update(yes_sub_title="Philadelphia" if m["ticker"].endswith("PHI") else "Dallas")
    app = create_app(trading_transport=httpx.MockTransport(exchange.handler),
                     market_transport=httpx.MockTransport(fake.handler), odds_transport=httpx.MockTransport(handler),
                     clock=lambda: datetime(2026, 10, 18, 18, tzinfo=timezone.utc))  # an hour after kickoff
    web = TestClient(app, base_url="https://testserver")
    login(web)
    r = web.get("/")
    assert "1 already started" in r.text and "in progress" in r.text and "No strong picks" in r.text
