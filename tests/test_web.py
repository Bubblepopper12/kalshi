import time

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
    return web.post("/ticket", data=data)


def token_from(html: str) -> str:
    return html.split('name="token" value="')[1].split('"')[0]


def test_locked_without_password(monkeypatch, exchange, fake):
    monkeypatch.setenv("APP_PASSWORD", "short")
    web = TestClient(create_app(), base_url="https://testserver")
    for path in ("/", "/login", "/markets"):
        r = web.get(path)
        assert "Setup needed" in r.text
    assert web.post("/login", data={"password": "short"}, follow_redirects=False).headers["location"] == "/login"


def test_login_required(web):
    for path in ("/", "/markets", "/ticket"):
        r = web.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert web.post("/send", data={"token": "x", "approve": "yes"}, follow_redirects=False).status_code == 303
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


def test_account_page(web, exchange):
    login(web)
    r = web.get("/")
    assert "LIVE" in r.text and "$100.00" in r.text and TICKER in r.text
    assert r.headers["cache-control"] == "no-store"


def test_markets_page_links_to_tickets(web):
    login(web)
    r = web.get("/markets?league=NFL&kind=moneyline")
    assert "KXNFLGAME-26OCT18KCBUF-KC" in r.text
    assert "/ticket?ticker=KXNFLGAME-26OCT18DALPHI-PHI&amp;side=yes&amp;price=55" in r.text


def test_full_approval_flow(web, exchange):
    login(web)
    r = review(web)
    assert "Review ticket" in r.text and "real money" in r.text and exchange.posts == []
    token = token_from(r.text)

    r = web.post("/send", data={"token": token})
    assert "tick the approval box" in r.text and exchange.posts == []

    r = web.post("/send", data={"token": token, "approve": "yes"})
    assert "Sent to Kalshi" in r.text
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
    assert "open orders" in r.text
    assert len(exchange.posts) == 1


def test_halt_balance_and_env_switch(web, exchange, monkeypatch):
    login(web)
    token = token_from(review(web).text)
    monkeypatch.setenv("TRADING_HALTED", "1")
    assert "halted" in web.post("/send", data={"token": token, "approve": "yes"}).text
    monkeypatch.delenv("TRADING_HALTED")
    exchange.balance_cents = 50
    assert "Your balance is" in web.post("/send", data={"token": token, "approve": "yes"}).text
    exchange.balance_cents = 10_000
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_TRADING_BASE", "https://kalshi.test/trade-api/v2")
    assert "made for LIVE" in web.post("/send", data={"token": token, "approve": "yes"}).text
    assert exchange.posts == []


def test_cancel(web, exchange):
    login(web)
    web.post("/send", data={"token": token_from(review(web).text), "approve": "yes"})
    assert "Cancel" in web.get("/").text
    r = web.post("/cancel", data={"order_id": "ord-1"}, follow_redirects=False)
    assert r.status_code == 303 and exchange.orders["ord-1"]["status"] == "canceled"
    assert "valid order id" in web.post("/cancel", data={"order_id": "../x"}).text


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
