"""Password-protected web app (runs on Vercel; see api/index.py and vercel.json).

It keeps no database: balance, positions, orders, fills and today's spend are
read from Kalshi on every page, so Kalshi's own order history is the record.

Trading follows the same rule as the terminal: nothing is sent until you
approve that exact order. "Make ticket" produces a review page with a signed,
expiring ticket; only ticking "I approve this exact order" and pressing Send
places it, after every limit is checked again against your live account.

Access: a password AND a 6-digit code from an authenticator app (required
whenever Kalshi keys are set). Missing or weak settings lock the whole app.

Settings (Vercel → Project → Settings → Environment Variables, Production only):
  APP_PASSWORD         at least 16 characters; without it the app shows only a setup page
  APP_TOTP_SECRET      base32 authenticator secret (see README "Web app"); required with keys
  KALSHI_ENV           live or demo
  KALSHI_API_KEY_ID    the Key ID
  KALSHI_PRIVATE_KEY   the whole private key text, BEGIN and END lines included
  PICKS_MAX_*          optional limit overrides (see .env.example)
  TRADING_HALTED       set to 1 to block all sending
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from ..config import Settings
from ..kalshi.classify import classify
from ..kalshi.client import KalshiReadOnlyClient, count_field, price_field
from ..kalshi.leagues import LEAGUES
from ..trading.client import KalshiAPIError, KalshiTradingClient, TradingNotConfigured
from ..trading.limits import max_cost, static_checks

MIN_PASSWORD_LENGTH = 16
SESSION_HOURS = 12
COOKIE = "picks_session"
GAME_TYPES = ("moneyline", "spread", "total")
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")


# ---------------------------------------------------------------- signing (sessions and tickets)


def _password() -> str:
    return os.environ.get("APP_PASSWORD", "")


def _totp_secret() -> str:
    return os.environ.get("APP_TOTP_SECRET", "").replace(" ", "").upper()


def totp_code(secret_b32: str, at: float | None = None, step: int = 30) -> str:
    """RFC 6238 six-digit code (what authenticator apps show)."""
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    return f"{(int.from_bytes(mac[offset:offset + 4], 'big') & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_ok(secret_b32: str, code: str, at: float | None = None) -> bool:
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code):
        return False
    now = time.time() if at is None else at
    return any(hmac.compare_digest(code, totp_code(secret_b32, now + drift)) for drift in (-30, 0, 30))


def _secret(settings: Settings) -> bytes:
    material = "\0".join([_password(), _totp_secret(), settings.kalshi_private_key or "",
                          settings.kalshi_api_key_id or ""])
    return hashlib.sha256(b"picks-web-v1\0" + material.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(settings: Settings, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def verify(settings: Settings, token: str | None, kind: str) -> dict | None:
    if not token or token.count(".") != 1:
        return None
    body, mac = token.split(".")
    good = _b64(hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, good):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    if payload.get("k") != kind or payload.get("exp", 0) < time.time():
        return None
    return payload


# ---------------------------------------------------------------- page chrome

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1b1b1b;--muted:#666;--line:#e3e3df;--accent:#0b6e4f;--danger:#b42318;
--warn-bg:#fff4e5;--live:#b42318;--demo:#1f6feb}
@media (prefers-color-scheme:dark){:root{--bg:#111;--card:#1b1b1b;--ink:#eee;--muted:#aaa;--line:#2c2c2c;
--accent:#3ccf91;--danger:#ff6b5e;--warn-bg:#2a2112}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}
nav{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
nav a{color:var(--ink);text-decoration:none;font-weight:600}nav .sp{flex:1}
.banner{padding:8px 16px;color:#fff;font-weight:700;text-align:center}
.live{background:var(--live)}.demo{background:var(--demo)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
h1{font-size:22px;margin:4px 0 8px}h2{font-size:18px;margin:0 0 8px}
.muted{color:var(--muted)}.err{color:var(--danger);font-weight:600}.ok{color:var(--accent);font-weight:600}
.warn{background:var(--warn-bg);border-radius:8px;padding:10px 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat b{display:block;font-size:22px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.scroll{overflow-x:auto}
input,select,button{font:inherit;padding:10px 12px;border-radius:8px;border:1px solid var(--line);
background:var(--card);color:var(--ink)}button{background:var(--accent);color:#fff;border:0;font-weight:700;
cursor:pointer}button.secondary{background:transparent;color:var(--ink);border:1px solid var(--line)}
button.small{padding:6px 10px;font-size:14px}
form.stack{display:grid;gap:10px;max-width:420px}label{display:grid;gap:4px;font-weight:600}
label.check{display:flex;gap:10px;align-items:flex-start;font-weight:600}
label.check input{width:22px;height:22px;margin-top:2px}
code{font-size:13px;word-break:break-all}
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def cents(value) -> str:
    return "—" if value is None else f"{Decimal(value) * 100:.0f}¢"


def page(settings: Settings, title: str, body: str, nav: bool = True) -> HTMLResponse:
    banner = ('<div class="banner live">LIVE — real money</div>' if settings.kalshi_env == "live"
              else '<div class="banner demo">DEMO — practice money</div>')
    links = ('<nav><a href="/">Account</a><a href="/markets">Markets</a><a href="/ticket">New ticket</a>'
             '<span class="sp"></span><a href="/logout" class="muted">Log out</a></nav>') if nav else ""
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta name="robots" content="noindex"><title>{esc(title)} · Kalshi bot</title>'
           f'<style>{CSS}</style></head><body>{banner}<main>{links}{body}</main></body></html>')
    resp = HTMLResponse(doc)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ---------------------------------------------------------------- live account figures


def committed_today(client: KalshiTradingClient, settings: Settings) -> tuple[Decimal, int]:
    """Money today's buys could use (fills since UTC midnight + resting buy orders), and the open-order count."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = Decimal(0)
    for f in client.fills(min_ts=int(start.timestamp())):
        if (f.get("action") or "buy") != "buy":
            continue
        created = f.get("created_time")
        if created:
            try:
                if datetime.fromisoformat(created.replace("Z", "+00:00")) < start:
                    continue
            except ValueError:
                pass
        side = f.get("side") or "yes"
        px, n = price_field(f, f"{side}_price"), count_field(f, "count")
        if px is not None and n:
            total += max_cost(n, px, settings.kalshi_fee_rate)
    resting = [o for o in client.orders("resting") if (o.get("action") or "buy") == "buy"]
    for o in resting:
        side = o.get("side") or "yes"
        px = price_field(o, f"{side}_price")
        n = count_field(o, "remaining_count") or count_field(o, "count")
        if px is not None and n:
            total += max_cost(n, px, settings.kalshi_fee_rate)
    return total, len(resting)


# ---------------------------------------------------------------- app


def create_app(trading_transport: httpx.BaseTransport | None = None,
               market_transport: httpx.BaseTransport | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def settings() -> Settings:
        return Settings.from_env()

    def setup_problem(s: Settings) -> str | None:
        if len(_password()) < MIN_PASSWORD_LENGTH:
            return (f"Set APP_PASSWORD (at least {MIN_PASSWORD_LENGTH} characters) in Vercel → Settings → "
                    "Environment Variables, then redeploy. The app stays locked until then.")
        secret = _totp_secret()
        if secret:
            try:
                totp_code(secret)
            except (ValueError, base64.binascii.Error):
                return "APP_TOTP_SECRET isn't a valid authenticator secret. The app stays locked until it's fixed."
        elif s.trading_keys_set:
            return ("Kalshi keys are set, so a two-step code is required. Set APP_TOTP_SECRET in Vercel and "
                    "add the same secret to your authenticator app, then redeploy. The app stays locked until then.")
        return None

    def logged_in(request: Request, s: Settings) -> bool:
        return verify(s, request.cookies.get(COOKIE), "session") is not None

    def trading_client(s: Settings) -> KalshiTradingClient:
        return KalshiTradingClient.from_settings(s, transport=trading_transport)

    def guard(request: Request):
        """None if the visitor may continue, else the response to send instead."""
        s = settings()
        problem = setup_problem(s)
        if problem:
            return page(s, "Setup needed", f'<div class="card"><h1>Setup needed</h1><p>{esc(problem)}</p></div>',
                        nav=False)
        if not logged_in(request, s):
            return RedirectResponse("/login", status_code=303)
        return None

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return "ok"

    # ------------------------------------------------------------ login

    @app.get("/login")
    def login_form(error: str = ""):
        s = settings()
        problem = setup_problem(s)
        if problem:
            return page(s, "Setup needed", f'<div class="card"><h1>Setup needed</h1><p>{esc(problem)}</p></div>',
                        nav=False)
        msg = '<p class="err">Wrong password or code.</p>' if error else ""
        code_field = ('<label>6-digit code from your authenticator app<input name="code" inputmode="numeric" '
                      'autocomplete="one-time-code" pattern="[0-9 ]{6,7}" required></label>') if _totp_secret() else ""
        return page(s, "Log in", f'''<div class="card"><h1>Kalshi bot</h1>{msg}
<form class="stack" method="post" action="/login">
<label>Password<input type="password" name="password" autocomplete="current-password" required autofocus></label>
{code_field}<button>Log in</button></form></div>''', nav=False)

    @app.post("/login")
    def login(password: str = Form(""), code: str = Form("")):
        s = settings()
        if setup_problem(s):
            return RedirectResponse("/login", status_code=303)
        password_ok = hmac.compare_digest(password.encode(), _password().encode())
        code_ok = totp_ok(_totp_secret(), code) if _totp_secret() else True
        if not (password_ok and code_ok):
            time.sleep(1.5)  # slows down guessing
            return RedirectResponse("/login?error=1", status_code=303)
        token = sign(s, {"k": "session", "exp": int(time.time()) + SESSION_HOURS * 3600})
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, secure=True, samesite="strict")
        return resp

    @app.get("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    # ------------------------------------------------------------ account

    @app.get("/")
    def account(request: Request):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        if not s.trading_keys_set:
            return page(s, "Account", '<div class="card"><h1>Account</h1><p>Kalshi keys aren\'t set yet. Add '
                        '<code>KALSHI_API_KEY_ID</code> and <code>KALSHI_PRIVATE_KEY</code> in Vercel, then '
                        'redeploy. Markets still work.</p></div>')
        try:
            with trading_client(s) as c:
                balance = c.balance_dollars()
                committed, open_n = committed_today(c, s)
                positions = [p for p in c.positions() if p.get("position")]
                resting = c.orders("resting")
                fills = c.fills()[:20]
        except (KalshiAPIError, TradingNotConfigured, ValueError, PermissionError, httpx.HTTPError) as exc:
            return page(s, "Account", f'<div class="card"><h1>Account</h1><p class="err">Couldn\'t read your '
                        f'Kalshi account: {esc(exc)}</p></div>')

        halted = os.environ.get("TRADING_HALTED") == "1"
        stats = f'''<div class="grid">
<div class="stat"><span class="muted">Balance</span><b>${balance:,.2f}</b></div>
<div class="stat"><span class="muted">Committed today (UTC)</span><b>${committed:,.2f}</b>
<span class="muted">of ${s.max_daily_dollars:,.0f} limit</span></div>
<div class="stat"><span class="muted">Open orders</span><b>{open_n}</b><span class="muted">of {s.max_open_orders}</span></div>
<div class="stat"><span class="muted">Sending</span><b>{"HALTED" if halted else "Needs approval"}</b></div></div>'''

        pos_rows = "".join(
            f"<tr><td><code>{esc(p.get('ticker'))}</code></td><td>{esc(p.get('position'))}</td>"
            f"<td>{esc(p.get('market_exposure_dollars') or p.get('market_exposure'))}</td></tr>" for p in positions)
        ord_rows = "".join(
            f"<tr><td><code>{esc(o.get('ticker'))}</code></td><td>{esc((o.get('side') or '').upper())}</td>"
            f"<td>{esc(count_field(o, 'remaining_count'))}</td>"
            f"<td>{cents(price_field(o, (o.get('side') or 'yes') + '_price'))}</td>"
            f"<td><form method=post action=/cancel><input type=hidden name=order_id value='{esc(o.get('order_id'))}'>"
            f"<button class='small secondary'>Cancel</button></form></td></tr>" for o in resting)
        fill_rows = "".join(
            f"<tr><td>{esc((f.get('created_time') or '')[:16].replace('T', ' '))}</td>"
            f"<td><code>{esc(f.get('ticker'))}</code></td><td>{esc(f.get('action'))} {esc((f.get('side') or '').upper())}</td>"
            f"<td>{esc(count_field(f, 'count'))}</td><td>{cents(price_field(f, (f.get('side') or 'yes') + '_price'))}</td></tr>"
            for f in fills)

        def table(head, rows, empty):
            if not rows:
                return f'<p class="muted">{empty}</p>'
            return f'<div class="scroll"><table><tr>{"".join(f"<th>{h}</th>" for h in head)}</tr>{rows}</table></div>'

        body = (f'<div class="card"><h1>Account</h1>{stats}</div>'
                f'<div class="card"><h2>Positions</h2>{table(["Market", "Contracts", "Exposure"], pos_rows, "No open positions.")}</div>'
                f'<div class="card"><h2>Resting orders</h2>{table(["Market", "Side", "Left", "Limit", ""], ord_rows, "No resting orders.")}</div>'
                f'<div class="card"><h2>Recent fills</h2>{table(["When (UTC)", "Market", "Action", "Contracts", "Price"], fill_rows, "No fills yet.")}</div>')
        return page(s, "Account", body)

    @app.post("/cancel")
    def cancel(request: Request, order_id: str = Form("")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", order_id):
            return page(s, "Cancel", '<div class="card"><p class="err">That isn\'t a valid order id.</p></div>')
        try:
            with trading_client(s) as c:
                c.cancel(order_id)
        except (KalshiAPIError, TradingNotConfigured, ValueError, httpx.HTTPError) as exc:
            return page(s, "Cancel", f'<div class="card"><p class="err">Not canceled: {esc(exc)}</p>'
                        '<p><a href="/">Back to account</a></p></div>')
        return RedirectResponse("/", status_code=303)

    # ------------------------------------------------------------ markets

    @app.get("/markets")
    def markets(request: Request, league: str = "NFL", kind: str = "moneyline"):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        league = league.upper() if league.upper() in LEAGUES else "NFL"
        kind = kind if kind in GAME_TYPES else "moneyline"
        rows, error = [], ""
        try:
            with KalshiReadOnlyClient(s.kalshi_api_base, requests_per_second=20, transport=market_transport) as rc:
                series = [x for x in rc.series(category="Sports")
                          if LEAGUES[league].matches(x) and classify(x["ticker"], x.get("title") or "") == kind][:6]
                for sr in series:
                    for ev in rc.events(sr["ticker"], status="open", with_nested_markets=True):
                        for m in ev.get("markets") or []:
                            rows.append((m.get("close_time") or "", ev.get("title") or ev.get("event_ticker"), m))
        except httpx.HTTPError as exc:
            error = f"Couldn't load markets from Kalshi: {exc}"
        rows.sort(key=lambda r: (r[0], r[1]))
        opts = lambda values, cur: "".join(  # noqa: E731
            f'<option value="{v}"{" selected" if v == cur else ""}>{v}</option>' for v in values)
        body = [f'''<div class="card"><h1>Markets</h1>
<form method="get" action="/markets" style="display:flex;gap:8px;flex-wrap:wrap">
<select name="league">{opts(list(LEAGUES), league)}</select><select name="kind">{opts(GAME_TYPES, kind)}</select>
<button class="secondary">Show</button></form>''']
        if error:
            body.append(f'<p class="err">{esc(error)}</p>')
        elif not rows:
            body.append('<p class="muted">No open markets of this kind right now.</p>')
        else:
            trs = []
            for close, title, m in rows[:300]:
                yes_ask, no_ask = price_field(m, "yes_ask"), price_field(m, "no_ask")
                buy = lambda side, ask: (  # noqa: E731
                    f'<a href="{esc("/ticket?" + urlencode({"ticker": m["ticker"], "side": side, "price": int(ask * 100)}))}">'
                    f'{side.upper()} {cents(ask)}</a>' if ask and 0 < ask < 1 else "—")
                trs.append(f"<tr><td>{esc(title)}<br><span class='muted'>{esc(m.get('yes_sub_title') or m.get('title'))}"
                           f"</span></td><td>{buy('yes', yes_ask)}</td><td>{buy('no', no_ask)}</td>"
                           f"<td class='muted'>{esc(close[:16].replace('T', ' '))}</td></tr>")
            body.append('<p class="muted">Tap a price to make a ticket. Nothing is sent until you approve it.</p>'
                        '<div class="scroll"><table><tr><th>Market</th><th>Buy YES</th><th>Buy NO</th>'
                        f'<th>Closes (UTC)</th></tr>{"".join(trs)}</table></div>')
        body.append("</div>")
        return page(s, "Markets", "".join(body))

    # ------------------------------------------------------------ tickets

    def ticket_form(s: Settings, ticker="", side="yes", price="", contracts="1", errors=()) -> HTMLResponse:
        err = "".join(f'<p class="err">{esc(e)}</p>' for e in errors)
        sel = lambda v: " selected" if side == v else ""  # noqa: E731
        return page(s, "New ticket", f'''<div class="card"><h1>New order ticket</h1>{err}
<p class="muted">Limits: ${s.max_order_dollars:.2f} per order, ${s.max_daily_dollars:.2f} per day,
{s.min_price * 100:.0f}¢–{s.max_price * 100:.0f}¢. A ticket sends nothing; you'll review it next.</p>
<form class="stack" method="post" action="/ticket">
<label>Market ticker<input name="ticker" value="{esc(ticker)}" required autocapitalize="characters"></label>
<label>Side<select name="side"><option value="yes"{sel("yes")}>YES</option><option value="no"{sel("no")}>NO</option></select></label>
<label>Most to pay per contract (¢)<input name="price" type="number" min="1" max="99" value="{esc(price)}" required></label>
<label>Contracts<input name="contracts" type="number" min="1" value="{esc(contracts)}" required></label>
<button>Review ticket</button></form></div>''')

    @app.get("/ticket")
    def new_ticket(request: Request, ticker: str = "", side: str = "yes", price: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        return ticket_form(settings(), ticker, side if side in ("yes", "no") else "yes", price)

    @app.post("/ticket")
    def review_ticket(request: Request, ticker: str = Form(""), side: str = Form("yes"),
                      price: str = Form(""), contracts: str = Form("1")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        ticker = ticker.strip().upper()
        errors = []
        if not TICKER_RE.match(ticker):
            errors.append("That doesn't look like a Kalshi market ticker.")
        if side not in ("yes", "no"):
            errors.append("Side must be YES or NO.")
        try:
            px = Decimal(price) / 100
            n = int(contracts)
        except (InvalidOperation, ValueError):
            errors.append("Price and contracts must be whole numbers.")
            px, n = Decimal(0), 0
        cost = max_cost(n, px, s.kalshi_fee_rate) if n > 0 else Decimal(0)
        if not errors:
            errors += static_checks(s, n, px, cost)
        if errors:
            return ticket_form(s, ticker, side, price, contracts, errors)
        exp = int(time.time()) + s.ticket_ttl_minutes * 60
        token = sign(s, {"k": "ticket", "env": s.kalshi_env, "ticker": ticker, "side": side, "count": n,
                         "price": str(px), "coid": str(uuid.uuid4()), "exp": exp})
        when = datetime.fromtimestamp(exp, timezone.utc).strftime("%H:%M UTC")
        live = ('<p class="warn"><b>This uses real money</b> from your Kalshi account.</p>'
                if s.kalshi_env == "live" else "")
        return page(s, "Review ticket", f'''<div class="card"><h1>Review ticket</h1>
<p><b>Buy {n} {side.upper()}</b> on <code>{esc(ticker)}</code></p>
<p>Pay at most <b>{cents(px)}</b> per contract. Most this can cost: <b>${cost}</b> (including Kalshi's fee).</p>
<p class="muted">It's a limit order: it only fills at {cents(px)} or better, and stops waiting after
{s.order_expiry_minutes} minutes. This ticket expires at {when} if you don't send it.</p>{live}
<form class="stack" method="post" action="/send"><input type="hidden" name="token" value="{esc(token)}">
<label class="check"><input type="checkbox" name="approve" value="yes" required>
I approve this exact order: buy {n} {side.upper()} at up to {cents(px)} (max ${cost})</label>
<button>Send to Kalshi</button></form><p><a href="/markets">Don't send — back to markets</a></p></div>''')

    @app.post("/send")
    def send(request: Request, token: str = Form(""), approve: str = Form("")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()

        def refuse(msg: str) -> HTMLResponse:
            return page(s, "Not sent", f'<div class="card"><h1>Not sent</h1><p class="err">{esc(msg)}</p>'
                        '<p><a href="/">Account</a> · <a href="/markets">Markets</a></p></div>')

        t = verify(s, token, "ticket")
        if t is None:
            return refuse("This ticket is expired or invalid. Make a new one.")
        if approve != "yes":
            return refuse("You didn't tick the approval box, so nothing was sent.")
        if t["env"] != s.kalshi_env:
            return refuse(f"This ticket was made for {t['env'].upper()}, but the app is now set to "
                          f"{s.kalshi_env.upper()}.")
        if os.environ.get("TRADING_HALTED") == "1":
            return refuse("Trading is halted (TRADING_HALTED=1 in Vercel).")
        px, n = Decimal(t["price"]), int(t["count"])
        cost = max_cost(n, px, s.kalshi_fee_rate)
        problems = static_checks(s, n, px, cost)
        if problems:
            return refuse(" ".join(problems))
        try:
            with trading_client(s) as c:
                committed, open_n = committed_today(c, s)
                if committed + cost > Decimal(str(s.max_daily_dollars)):
                    return refuse(f"Today's orders could already cost ${committed:.2f}; this one (${cost}) "
                                  f"would pass the ${s.max_daily_dollars:.2f} daily limit.")
                if open_n >= s.max_open_orders:
                    return refuse(f"You already have {open_n} open orders (the limit is {s.max_open_orders}).")
                balance = c.balance_dollars()
                if balance < cost:
                    return refuse(f"Your balance is ${balance:.2f}; this order could cost ${cost}.")
                expiration = (int((datetime.now(timezone.utc) + timedelta(minutes=s.order_expiry_minutes)).timestamp())
                              if s.order_expiry_minutes > 0 else None)
                result = c.create_limit_buy(ticker=t["ticker"], side=t["side"], count=n, price=px,
                                            client_order_id=t["coid"], expiration_ts=expiration)
        except KalshiAPIError as exc:
            hint = " (This ticket may already have been sent — check your account.)" if exc.status == 409 else ""
            return refuse(f"Kalshi rejected the order: {exc}{hint}")
        except httpx.HTTPError as exc:
            return refuse(f"The connection dropped ({exc}). The order may or may not have reached Kalshi — "
                          "check Resting orders and Recent fills on the Account page before trying again.")
        except (TradingNotConfigured, ValueError, PermissionError) as exc:
            return refuse(str(exc))
        order = result.get("order") or {}
        return page(s, "Sent", f'''<div class="card"><h1 class="ok">Sent to Kalshi</h1>
<p>Buy {n} {t["side"].upper()} on <code>{esc(t["ticker"])}</code> at up to {cents(px)}.</p>
<p>Kalshi order <code>{esc(order.get("order_id"))}</code>: <b>{esc(order.get("status"))}</b>,
filled {esc(order.get("fill_count", 0))} of {n}.</p><p><a href="/">See it on your account</a></p></div>''')

    return app
