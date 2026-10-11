import base64
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from picks_engine.config import Settings
from picks_engine.db import schema as t
from picks_engine.trading import orders as tr
from picks_engine.trading.auth import KalshiSigner
from picks_engine.trading.client import KalshiTradingClient, TradingNotConfigured, trading_base_url

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TICKER = "KXNFLGAME-26OCT18DALPHI-PHI"


class FakeExchange:
    """Kalshi portfolio endpoints; rejects any request whose signature doesn't verify."""

    def __init__(self, balance_cents=10_000):
        self.balance_cents = balance_cents
        self.orders: dict[str, dict] = {}
        self.posts: list[dict] = []
        self.fail_next_post: int | None = None
        self.drop_next_post = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        ts = request.headers["KALSHI-ACCESS-TIMESTAMP"]
        sig = base64.b64decode(request.headers["KALSHI-ACCESS-SIGNATURE"])
        msg = (ts + request.method + request.url.path).encode()
        KEY.public_key().verify(sig, msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                      salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
        assert request.headers["KALSHI-ACCESS-KEY"] == "key-123"
        path = request.url.path.split("/trade-api/v2")[1]
        if request.method == "GET" and path == "/portfolio/balance":
            return httpx.Response(200, json={"balance": self.balance_cents})
        if request.method == "POST" and path == "/portfolio/orders":
            body = json.loads(request.content)
            if self.drop_next_post:
                self.drop_next_post = False
                self.orders[body["client_order_id"]] = {"order_id": "ord-lost", "status": "resting",
                                                        "client_order_id": body["client_order_id"], "fill_count": 0}
                raise httpx.ReadTimeout("timed out", request=request)
            if self.fail_next_post:
                status, self.fail_next_post = self.fail_next_post, None
                return httpx.Response(status, json={"error": {"code": "insufficient_balance"}})
            self.posts.append(body)
            order = {"order_id": f"ord-{len(self.posts)}", "status": "resting",
                     "client_order_id": body["client_order_id"], "fill_count": 0,
                     "remaining_count": body["count"]}
            self.orders[order["order_id"]] = order
            return httpx.Response(201, json={"order": order})
        if request.method == "GET" and path == "/portfolio/orders":
            return httpx.Response(200, json={"orders": list(self.orders.values())})
        if request.method == "GET" and path.startswith("/portfolio/orders/"):
            return httpx.Response(200, json={"order": self.orders[path.rsplit("/", 1)[1]]})
        if request.method == "DELETE" and path.startswith("/portfolio/orders/"):
            order = self.orders[path.rsplit("/", 1)[1]]
            order["status"] = "canceled"
            return httpx.Response(200, json={"order": order})
        return httpx.Response(404)


@pytest.fixture
def settings():
    return Settings(database_url="sqlite://", kalshi_env="demo", kalshi_api_key_id="key-123")


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def tclient(exchange):
    c = KalshiTradingClient("https://demo-api.kalshi.co/trade-api/v2", KalshiSigner("key-123", KEY), "demo",
                            transport=httpx.MockTransport(exchange.handler))
    yield c
    c.close()


def ticket(engine, settings, **kw):
    args = dict(ticker=TICKER, side="yes", count=10, price=Decimal("0.54"), reason="test")
    return tr.propose(engine, settings, **(args | kw))


def test_demo_is_the_default_host():
    assert trading_base_url(Settings()) == "https://demo-api.kalshi.co/trade-api/v2"
    assert "elections" in trading_base_url(Settings(kalshi_env="live"))
    with pytest.raises(TradingNotConfigured):
        trading_base_url(Settings(kalshi_env="prod"))
    with pytest.raises(TradingNotConfigured):
        KalshiTradingClient.from_settings(Settings())  # no keys configured


def test_propose_sends_nothing(engine, settings, exchange):
    tk = ticket(engine, settings)
    assert tk.status == "proposed" and tk.env == "demo"
    assert tk.max_cost == Decimal("5.58")  # 10 x 54c + fee: 0.07 x 10 x .54 x .46 = 17.4c, rounded up to 18c
    assert exchange.posts == [] and exchange.orders == {}


def test_full_flow(engine, settings, exchange, tclient):
    tk = ticket(engine, settings)
    sent = tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER.lower(), via="cli")
    assert sent.status == "resting" and sent.kalshi_order_id == "ord-1"
    assert exchange.posts == [{"ticker": TICKER, "client_order_id": tk.client_order_id, "action": "buy",
                               "side": "yes", "type": "limit", "count": 10, "yes_price": 54,
                               "expiration_ts": exchange.posts[0]["expiration_ts"]}]
    with pytest.raises(tr.TradeRefused, match="already|not waiting"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    assert len(exchange.posts) == 1  # never sent twice

    exchange.orders["ord-1"].update(status="executed", fill_count=10)
    assert tr.refresh(engine, tclient) == 1
    with engine.connect() as conn:
        assert tr.get_ticket(conn, tk.id).status == "executed"
        events = conn.execute(sa.select(t.trade_audit.c.event).where(t.trade_audit.c.order_id == tk.id)).scalars().all()
    assert events == ["proposed", "submit_request", "submit_response", "refresh"]


def test_wrong_confirmation_sends_nothing(engine, settings, exchange, tclient):
    tk = ticket(engine, settings)
    with pytest.raises(tr.TradeRefused, match="didn't match"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker="yes", via="cli")
    assert exchange.posts == []


def test_size_and_price_limits(engine, settings):
    with pytest.raises(tr.TradeRefused, match="per-order limit"):
        ticket(engine, settings, count=30)  # ~$16.6 > $10
    with pytest.raises(tr.TradeRefused, match="contract limit"):
        ticket(engine, replace(settings, max_order_dollars=1000), count=500)
    with pytest.raises(tr.TradeRefused, match="range"):
        ticket(engine, settings, price=Decimal("0.97"))
    with pytest.raises(tr.TradeRefused, match="whole number"):
        ticket(engine, settings, price=Decimal("0.545"))
    with pytest.raises(tr.TradeRefused, match="YES or NO"):
        ticket(engine, settings, side="maybe")


def test_daily_and_open_order_limits(engine, settings, exchange, tclient):
    s = replace(settings, max_daily_dollars=12, max_open_orders=5)
    for _ in range(2):
        tk = ticket(engine, s)
        tr.approve_and_submit(engine, s, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    tk = ticket(engine, s)
    with pytest.raises(tr.TradeRefused, match="daily limit"):
        tr.approve_and_submit(engine, s, tclient, tk.id, confirm_ticker=TICKER, via="cli")

    s2 = replace(settings, max_daily_dollars=1000, max_open_orders=2)
    with pytest.raises(tr.TradeRefused, match="open orders"):
        tr.approve_and_submit(engine, s2, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    assert len(exchange.posts) == 2


def test_halt_switch(engine, settings, exchange, tclient):
    tk = ticket(engine, settings)
    tr.set_halt(engine, True, "testing")
    with pytest.raises(tr.TradeRefused, match="halted"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    tr.set_halt(engine, False)
    assert tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli").status == "resting"


def test_expired_and_rejected_tickets(engine, settings, exchange, tclient):
    tk = ticket(engine, settings)
    with engine.begin() as conn:
        conn.execute(t.trade_orders.update().values(expires_at=tr.utcnow() - timedelta(minutes=1)))
    with pytest.raises(tr.TradeRefused, match="expired"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    other = ticket(engine, settings)
    assert tr.reject(engine, other.id).status == "rejected"
    with pytest.raises(tr.TradeRefused):
        tr.approve_and_submit(engine, settings, tclient, other.id, confirm_ticker=TICKER, via="cli")
    assert exchange.posts == []


def test_demo_ticket_cannot_go_live(engine, settings, tclient):
    tk = ticket(engine, settings)
    with pytest.raises(tr.TradeRefused, match="made for DEMO"):
        tr.approve_and_submit(engine, replace(settings, kalshi_env="live"), tclient, tk.id,
                              confirm_ticker=TICKER, via="cli")


def test_balance_and_rejection(engine, settings, exchange, tclient):
    exchange.balance_cents = 300
    tk = ticket(engine, settings)
    with pytest.raises(tr.TradeRefused, match="account has"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    exchange.balance_cents = 10_000
    exchange.fail_next_post = 400
    with pytest.raises(tr.TradeRefused, match="rejected"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    with engine.connect() as conn:
        assert tr.get_ticket(conn, tk.id).status == "failed"


def test_dropped_connection_is_reconciled(engine, settings, exchange, tclient):
    exchange.drop_next_post = True
    tk = ticket(engine, settings)
    with pytest.raises(tr.TradeRefused, match="may or may not"):
        tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    with engine.connect() as conn:
        assert tr.get_ticket(conn, tk.id).status == "unknown"
    tr.refresh(engine, tclient)
    with engine.connect() as conn:
        found = tr.get_ticket(conn, tk.id)
    assert found.status == "resting" and found.kalshi_order_id == "ord-lost"


def test_cancel(engine, settings, exchange, tclient):
    tk = ticket(engine, settings)
    tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="cli")
    assert tr.cancel(engine, tclient, tk.id).status == "canceled"
    with engine.connect() as conn:
        assert tr.spent_today(conn, "demo") == 0  # canceled with nothing filled


def test_client_refuses_other_calls(tclient):
    with pytest.raises(PermissionError):
        tclient._request("POST", "/portfolio/transfer", json={})
    with pytest.raises(PermissionError):
        tclient._request("GET", "/portfolio/settlements")


def test_key_file_permissions(tmp_path):
    pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    path = tmp_path / "kalshi.key"
    path.write_bytes(pem)
    path.chmod(0o644)
    with pytest.raises(PermissionError, match="chmod 600"):
        KalshiSigner.from_file("key-123", path)
    path.chmod(0o600)
    assert KalshiSigner.from_file("key-123", path).headers("GET", "/trade-api/v2/portfolio/balance")


def test_suggestion_ticket_logs_decision(engine, settings, exchange, tclient):
    from tests_helpers import make_candidate
    from picks_engine.picks import evaluate
    from picks_engine.picks.store import save_suggestions

    sid = save_suggestions(engine, "r", [evaluate(make_candidate())])[0]
    tk = ticket(engine, settings, suggestion_id=sid)
    tr.approve_and_submit(engine, settings, tclient, tk.id, confirm_ticker=TICKER, via="board")
    with engine.connect() as conn:
        d = conn.execute(sa.select(t.logan_decisions)).mappings().one()
    assert d["decision"] == "took" and d["contracts"] == 10 and d["suggestion_id"] == sid


def test_ed25519_keys_sign_the_same_text(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    key = ed25519.Ed25519PrivateKey.generate()
    path = tmp_path / "kalshi.key"
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")  # same header Kalshi's Ed25519 keys use
    path.write_bytes(pem)
    path.chmod(0o600)
    signer = KalshiSigner.from_file("key-123", path)
    assert signer.key_type == "ed25519"
    h = signer.headers("GET", "/trade-api/v2/portfolio/balance?limit=1", timestamp_ms=1700000000000)
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]),
                            b"1700000000000GET/trade-api/v2/portfolio/balance")

    ec_path = tmp_path / "ec.key"
    ec_path.write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ec_path.chmod(0o600)
    with pytest.raises(ValueError, match="RSA or Ed25519"):
        KalshiSigner.from_file("key-123", ec_path)
    junk = tmp_path / "junk.key"
    junk.write_text("not a key")
    junk.chmod(0o600)
    with pytest.raises(ValueError, match="readable private key"):
        KalshiSigner.from_file("key-123", junk)
