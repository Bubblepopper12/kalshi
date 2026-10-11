"""Password-protected web app (runs on Vercel; see api/index.py and vercel.json).

Pages, in plain English:
  Picks       where Kalshi sells an outcome for less than the sportsbooks think it's worth, with the why
  All bets    full-game markets grouped by game: "Philadelphia wins · 62¢ · pays $1.00 if right"
  My account  your cash, today's spending vs. your limit, your bets, waiting orders, recent activity
  Bet         1. Choose how many  2. Review exactly what you pay / win / lose  3. Approve and send

It keeps no database: everything is read from Kalshi on each page, so Kalshi's
own history is the record. Nothing is sent until you tick "I approve this bet"
on the review page; every limit is checked again against your live account
right before sending.

Access: a password AND a 6-digit code from an authenticator app (required
whenever Kalshi keys are set). Missing or weak settings lock the whole app.

Settings (Vercel → Project → Settings → Environment Variables, Production only):
  APP_PASSWORD         at least 16 characters; without it the app shows only a setup page
  APP_TOTP_SECRET      base32 authenticator secret (see README "Web app"); required with keys
  KALSHI_API_KEY_ID    the Key ID
  KALSHI_PRIVATE_KEY   the whole private key text, BEGIN and END lines included
  TRADING_HALTED       set to 1 to block all sending
  APP_TIMEZONE         optional, default America/Chicago
Plain defaults (live, $5 per bet, $20 per day) are in web/web.env.
"""

from __future__ import annotations

import hmac
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from ..config import Settings
from ..kalshi.client import KalshiReadOnlyClient, count_field, price_field
from ..kalshi.leagues import LEAGUES
from ..live.odds_api import OddsAPIError
from ..live.picks import size
from ..pricing.fees import kalshi_fee
from ..trading.client import KalshiAPIError, KalshiTradingClient, TradingNotConfigured
from ..trading.limits import max_cost, static_checks
from .account import committed_today, holdings, lookup_names, name_market
from .data import Sources, clear_caches
from .describe import KIND_LABELS, bet_sentence, cents, money, when
from .security import (COOKIE, MIN_PASSWORD_LENGTH, SESSION_HOURS, _password, _totp_secret, sign,  # noqa: F401
                       totp_code, totp_ok, verify)
from .ui import esc, page, steps
from .views import SEARCH_JS, game_card, league_chips, pick_card, search_bar

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")
MAX_GAMES = 300
TRADING_ERRORS = (KalshiAPIError, TradingNotConfigured, ValueError, PermissionError, httpx.HTTPError)

ORDER_STATUS = {
    "resting": ("Waiting for a seller", "Your order is on Kalshi, waiting for someone to sell at your price or "
                "better. If nobody does within {mins} minutes, it cancels itself and you pay nothing."),
    "executed": ("Done: you bought it", "Your bet went through. It now shows under “Your bets” in My account."),
    "canceled": ("Not filled", "Nobody sold at your price, so Kalshi canceled it. You paid nothing."),
}


def create_app(trading_transport: httpx.BaseTransport | None = None,
               market_transport: httpx.BaseTransport | None = None,
               odds_transport: httpx.BaseTransport | None = None,
               clock=None) -> FastAPI:
    """clock: optional function returning the current UTC datetime (tests pin it)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    clear_caches()

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
            except ValueError:
                return "APP_TOTP_SECRET isn't a valid authenticator secret. The app stays locked until it's fixed."
        elif s.trading_keys_set:
            return ("Kalshi keys are set, so a two-step code is required. Set APP_TOTP_SECRET in Vercel and "
                    "add the same secret to your authenticator app, then redeploy. The app stays locked until then.")
        return None

    def trading_client(s: Settings) -> KalshiTradingClient:
        return KalshiTradingClient.from_settings(s, transport=trading_transport)

    def market_client(s: Settings) -> KalshiReadOnlyClient:
        return KalshiReadOnlyClient(s.kalshi_api_base, requests_per_second=20, transport=market_transport)

    def setup_page(s: Settings, problem: str) -> HTMLResponse:
        return page(s, "Setup needed", f'<div class="card"><h1>Setup needed</h1><p>{esc(problem)}</p></div>',
                    nav=False)

    def guard(request: Request):
        """None if the visitor may continue, else the response to send instead."""
        s = settings()
        problem = setup_problem(s)
        if problem:
            return setup_page(s, problem)
        if verify(s, request.cookies.get(COOKIE), "session") is None:
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
            return setup_page(s, problem)
        msg = '<p class="bad">That password or code didn\'t match. Try again with a fresh code.</p>' if error else ""
        code_field = ('<label>6-digit code<span class="muted small" style="font-weight:400">From the Passwords '
                      'app → Kalshi bot → Code</span><input name="code" inputmode="numeric" '
                      'autocomplete="one-time-code" pattern="[0-9 ]{6,7}" required></label>') if _totp_secret() else ""
        return page(s, "Log in", f'''<div class="card"><h1>Log in</h1>
<p class="lead">Only you can use this site. It needs your password and the code from your phone.</p>{msg}
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

    # ------------------------------------------------------------ home

    @app.get("/account")
    def home(request: Request):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        how = '''<details class="card"><summary>How this works</summary><ol style="margin:10px 0 0 18px;padding:0">
<li><b>Pick a bet.</b> Take one of today's Picks, or choose any game under All bets.</li>
<li><b>Review it.</b> You see exactly what you pay, what you get back if you're right, and what you lose if you're wrong.</li>
<li><b>Approve it.</b> Nothing is sent to Kalshi until you tick “I approve this bet” and press Send.</li>
</ol><p class="muted small" style="margin-top:10px">Each contract pays $1.00 if you're right and $0 if you're wrong.
The price (like 62¢) is roughly the chance the market gives it (62%).</p></details>'''
        if not s.trading_keys_set:
            return page(s, "My account", '<h1>My account</h1><div class="card"><p>Kalshi keys aren\'t set yet, so your '
                        'account can\'t be shown. Add <code>KALSHI_API_KEY_ID</code> and <code>KALSHI_PRIVATE_KEY'
                        '</code> in Vercel, then redeploy.</p></div>' + how, tab="home")
        try:
            with trading_client(s) as c:
                cash = c.balance_dollars()
                committed, open_n = committed_today(c, s)
                positions = c.positions()
                resting = c.orders("resting")
                fills = c.fills()[:10]
        except TRADING_ERRORS as exc:
            return page(s, "My account", f'<h1>My account</h1><div class="card bad">Couldn\'t read your Kalshi account: '
                        f'{esc(exc)}</div>', tab="home")
        with market_client(s) as rc:
            names = lookup_names(rc, [p.get("ticker") for p in positions if count_field(p, "position")]
                                 + [o.get("ticker") for o in resting] + [f.get("ticker") for f in fills])
        held = holdings(positions, names)
        halted = os.environ.get("TRADING_HALTED") == "1"
        left_today = max(Decimal(str(s.max_daily_dollars)) - committed, Decimal(0))

        parts = ['<h1>My account</h1><p class="lead">Your own Kalshi money and bets, read live from Kalshi. '
                 'These are not recommendations; those are on the Picks tab.</p>']
        cash_note = ""
        if cash < Decimal("1"):
            cash_note = ('<p class="warn" style="margin-top:12px">You have no cash to bet with. Add money on '
                         'kalshi.com → Funds, then come back.</p>')
        parts.append(f'''<div class="card"><div class="grid">
<div><div class="muted">Cash you can bet</div><div class="big">{money(cash.quantize(Decimal("0.01")))}</div></div>
<div><div class="muted">You can still spend today</div><div class="big">{money(left_today)}</div>
<div class="muted small">of your {money(s.max_daily_dollars)} daily limit · {money(s.max_order_dollars)} max per bet</div></div>
</div>{cash_note}{'<p class="bad" style="margin-top:12px">Sending bets is turned off (TRADING_HALTED).</p>' if halted else ''}
<p style="margin-top:14px"><a class="btn" href="/">See today's picks</a></p></div>''')

        rows = []
        for h in held:
            worth = f" · worth about {money(h.worth_now)} now" if h.worth_now is not None else ""
            rows.append(f'''<div class="row"><div class="what"><b>{esc(bet_sentence(h.name.statement, h.side))}</b>
<span class="muted small">{esc(h.name.question)}</span><br>
<span class="small">{h.contracts:,} contracts · pays {money(h.pays_if_right)} if right{worth}</span></div></div>''')
        parts.append('<div class="card"><h2>Your bets</h2>' + ("".join(rows) or
                     '<p class="muted">No open bets.</p>') + "</div>")

        rows = []
        for o in resting:
            side = o.get("side") or "yes"
            nm = names.get(o.get("ticker", ""))
            rows.append(f'''<div class="row"><div class="what"><b>{esc(bet_sentence(nm.statement if nm else o.get("ticker"), side))}</b>
<span class="small">{count_field(o, "remaining_count") or 0} contracts left · at up to {cents(price_field(o, side + "_price"))} each</span></div>
<form method="post" action="/cancel"><input type="hidden" name="order_id" value="{esc(o.get("order_id"))}">
<button class="ghost sm">Cancel</button></form></div>''')
        parts.append('<div class="card"><h2>Waiting orders</h2><p class="muted small">Orders sent to Kalshi that '
                     'haven\'t filled yet. They cancel themselves after a few minutes.</p>'
                     + ("".join(rows) or '<p class="muted">None right now.</p>') + "</div>")

        rows = []
        for f in fills:
            side = f.get("side") or "yes"
            nm = names.get(f.get("ticker", ""))
            verb = "Bought" if (f.get("action") or "buy") == "buy" else "Sold"
            rows.append(f'''<div class="row"><div class="what"><b>{esc(bet_sentence(nm.statement if nm else f.get("ticker"), side))}</b>
<span class="small">{verb} {count_field(f, "count") or 0} at {cents(price_field(f, side + "_price"))} · {esc(when(f.get("created_time")))}</span></div></div>''')
        parts.append('<div class="card"><h2>Recent activity</h2>' + ("".join(rows) or
                     '<p class="muted">Nothing yet.</p>') + "</div>")
        parts.append(how)
        return page(s, "My account", "".join(parts), tab="home")

    @app.post("/cancel")
    def cancel(request: Request, order_id: str = Form("")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", order_id):
            return page(s, "Cancel", '<div class="card bad">That isn\'t a valid order.</div>', tab="home")
        try:
            with trading_client(s) as c:
                c.cancel(order_id)
        except TRADING_ERRORS as exc:
            return page(s, "Cancel", f'<div class="card"><p class="bad">Not canceled: {esc(exc)}</p>'
                        '<p><a href="/account">Back to My account</a></p></div>', tab="home")
        return RedirectResponse("/account", status_code=303)

    # ------------------------------------------------------------ picks

    def sources(s: Settings) -> Sources:
        return Sources(s, market_transport=market_transport, odds_transport=odds_transport, clock=clock)

    def now_utc() -> datetime:
        return clock() if clock else datetime.now(timezone.utc)

    def cash_balance(s: Settings) -> Decimal | None:
        if not s.trading_keys_set:
            return None
        try:
            with trading_client(s) as c:
                return c.balance_dollars()
        except TRADING_ERRORS:
            return None

    @app.get("/")
    def picks_page(request: Request, league: str = "NFL", refresh: str = "", q: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        league = league.upper() if league.upper() in LEAGUES else "NFL"
        parts = [f'''<h1>Picks</h1>
<p class="lead">Bets where Kalshi's price is lower than what the sportsbooks think the outcome is worth.
It's math, not a guarantee, so keep bets small.</p>
{league_chips(league, lambda code: "/?league=" + code)}''']
        if not s.odds_api_key:
            parts.append('''<div class="card warn"><h2>One more setup step</h2>
<p>Picks compare Kalshi with sportsbook prices, which come from The Odds API. Get a free key at
the-odds-api.com, then add it in Vercel → Settings → Environment Variables as <b>ODDS_API_KEY</b>
(Production, Sensitive) and redeploy.</p></div>''')
            return page(s, "Picks", "".join(parts), tab="picks")
        try:
            result, left, fetched = sources(s).picks(league, refresh == "1")
        except (httpx.HTTPError, OddsAPIError) as exc:
            parts.append(f'<div class="card bad">Couldn\'t load prices right now: {esc(exc)}</div>')
            return page(s, "Picks", "".join(parts), tab="picks")

        cash = cash_balance(s)
        for p in result.picks:
            size(p, cash, s.max_order_dollars)
        age = int((time.time() - fetched) // 60)
        name = LEAGUES[league].name
        status = [f"{result.games_matched} of {result.games_checked} {esc(name)} games compared with the sportsbooks",
                  "updated just now" if age == 0 else f"updated {age} min ago"]
        if left is not None:
            status.append(f"{left} sportsbook lookups left this month")
        status.append(f'<a href="/?league={league}&refresh=1">Refresh</a>')
        parts.append('<p class="status">' + "".join(f"<span>{x}</span>" for x in status) + "</p>")

        parts.append(f'<section><h2>Best picks <span class="muted small">{len(result.picks)}</span></h2>')
        if result.picks:
            parts.extend(pick_card(p, cash) for p in result.picks)
        else:
            parts.append(f'''<div class="card empty"><h3>No strong picks in {esc(name)} right now</h3>
<p class="muted">Nothing is at least {s.picks_min_edge * 100:.0f} points cheaper on Kalshi than at the sportsbooks.
That's normal: Kalshi's prices usually stay close. Check closer to game time, try another league, or look through
every game below.</p></div>''')
        parts.append("</section>")

        board = sorted(result.board, key=lambda g: (-(g.best_edge if g.best_edge is not None else -9),
                                                   g.starts or datetime.max.replace(tzinfo=timezone.utc)))
        parts.append('<section><h2>Every game <span class="muted small">Kalshi price vs. sportsbooks</span></h2>'
                     '<p class="muted small">Each box: the team, what it costs on Kalshi, the sportsbooks\' chance, '
                     'and the difference in points (green = cheaper on Kalshi).</p>')
        parts.append(search_bar(q, "Search: team, nickname or day", picks_filter=True))
        if board:
            parts.extend(game_card(g, s.picks_min_edge, now_utc()) for g in board)
            parts.append('<p class="muted empty" id="none" style="display:none">No games match your search.</p>')
        else:
            parts.append(f'<div class="card empty"><p class="muted">No upcoming {esc(name)} games on Kalshi right now.</p></div>')
        if result.unmatched:
            parts.append('<p class="muted small">Not compared (the sportsbooks don\'t list these the same way): '
                         + esc(", ".join(result.unmatched[:8])) + ("…" if len(result.unmatched) > 8 else "") + "</p>")
        parts.append("</section>")
        parts.append('''<details class="card"><summary>How picks work</summary>
<p style="margin-top:10px">1. The bot reads the odds from several sportsbooks (Pinnacle, DraftKings, FanDuel and others)
and removes their built-in profit margin, which gives a fair chance for each outcome.</p>
<p>2. It compares that chance with Kalshi's price plus Kalshi's fee. If Kalshi is at least
3 points cheaper, it's a pick.</p>
<p>3. <b>Strong</b> means at least 5 points, 3+ sportsbooks, Pinnacle agrees, and Kalshi prices aren't stretched.
<b>Good</b> means it clears 3 points but misses one of those.</p>
<p>4. Suggested size is a quarter of the "Kelly" amount for your cash, never above your per-bet limit.</p>
<p class="muted small">Coming later: tipster track records and the bot's own model.</p></details>''')
        parts.append(SEARCH_JS)
        return page(s, "Picks", "".join(parts), tab="picks")

    # ------------------------------------------------------------ all bets

    @app.get("/markets")
    def markets_alias(league: str = "ALL", kind: str = "moneyline"):
        return RedirectResponse("/find?" + urlencode({"league": league, "kind": kind}), status_code=303)

    @app.get("/find")
    def find(request: Request, league: str = "ALL", kind: str = "moneyline", q: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        league = league.upper() if league.upper() in LEAGUES or league.upper() == "ALL" else "ALL"
        kind = kind if kind in KIND_LABELS else "moneyline"
        games, error = [], ""
        try:
            games = sources(s).games(list(LEAGUES) if league == "ALL" else [league], kind)
        except httpx.HTTPError as exc:
            error = f"Couldn't load games from Kalshi right now ({exc}). Try again in a minute."
        games.sort(key=lambda g: (g.day or date.max, g.title))
        games = games[:MAX_GAMES]

        link = lambda **kw: "/find?" + urlencode({"league": league, "kind": kind} | kw)  # noqa: E731
        kind_chips = "".join(f'<a class="{"on" if k == kind else ""}" href="{esc(link(kind=k))}">{label}</a>'
                             for k, (label, _) in KIND_LABELS.items())
        parts = [f'''<h1>All bets</h1>
<p class="lead">Every game Kalshi offers. These are not recommendations (those are on Picks). Each box shows what
it costs; it pays $1.00 if you're right.</p>
{search_bar(q, "Search: eagles, lakers, sunday…")}
{league_chips(league, lambda code: link(league=code), include_all=True)}
<div class="chips">{kind_chips}</div><p class="muted small">{esc(KIND_LABELS[kind][1])} Full-game bets only.</p>''']
        if error:
            parts.append(f'<div class="card bad">{esc(error)}</div>')
        elif not games:
            parts.append('<div class="card empty"><p class="muted">No open bets of this kind right now.</p></div>')
        else:
            parts.extend(game_card(g, s.picks_min_edge, now_utc()) for g in games)
            parts.append('<p class="muted empty" id="none" style="display:none">No games match your search.</p>')
        parts.append(SEARCH_JS)
        return page(s, "All bets", "".join(parts), tab="find")

    # ------------------------------------------------------------ bet: choose → review → send

    def market_info(s: Settings, ticker: str):
        try:
            with market_client(s) as rc:
                m = rc.market(ticker)
        except httpx.HTTPError:
            m = {}
        return name_market(m) if m else None

    def choose_page(s: Settings, ticker: str, side: str, contracts: str = "1", price: str = "",
                    errors=()) -> HTMLResponse:
        info = market_info(s, ticker) if ticker else None
        err = "".join(f'<p class="bad">{esc(e)}</p>' for e in errors)
        if info is None:
            return page(s, "Bet", f'''{steps(0)}<h1>Choose a bet</h1>{err}
<div class="card"><p>Start from <a href="/">Picks</a> or <a href="/find">All bets</a> and tap the outcome you want.</p>
<details><summary>Advanced: enter a market ticker</summary>
<form class="stack" method="get" action="/bet" style="margin-top:12px">
<label>Market ticker<input name="ticker" value="{esc(ticker)}" autocapitalize="characters" required></label>
<label>Side<select name="side"><option value="yes">YES (it happens)</option><option value="no">NO (it doesn't)</option></select></label>
<button>Continue</button></form></details></div>''', tab="find")
        ask = info.yes_ask if side == "yes" else info.no_ask
        price = price or (str(int(ask * 100)) if ask is not None and 0 < ask < 1 else "")
        statement = bet_sentence(info.statement, side)
        rate = s.kalshi_fee_rate
        return page(s, "Bet", f'''{steps(0)}<h1>How many?</h1>{err}
<div class="card"><div class="muted small">You're betting</div><h2 style="margin:4px 0">{esc(statement)}</h2>
<p class="muted small">{esc(info.question)}</p>
<p>Right now it costs <b>{cents(ask)}</b> per contract. Each contract pays <b>$1.00</b> if you're right.</p>
<form class="stack" method="post" action="/bet" oninput="calc()">
<input type="hidden" name="ticker" value="{esc(info.ticker)}"><input type="hidden" name="side" value="{esc(side)}">
<label>Number of contracts<input id="n" name="contracts" type="number" min="1" step="1" value="{esc(contracts)}" required></label>
<details><summary>Advanced: most you'll pay per contract</summary>
<label style="margin-top:10px">Max price (¢)<input id="p" name="price" type="number" min="1" max="99" value="{esc(price)}" required></label>
<p class="muted small">Your order only fills at this price or cheaper.</p></details>
<div class="note" id="sum">…</div>
<button>Review bet →</button></form>
<p class="muted small" style="margin-top:12px">Your limits: {money(s.max_order_dollars)} per bet, {money(s.max_daily_dollars)} per day.</p></div>
<script>function calc(){{var n=parseInt(document.getElementById('n').value)||0,p=(parseInt(document.getElementById('p').value)||0)/100;
var fee=Math.ceil({rate}*n*p*(1-p)*100-1e-9)/100,cost=n*p+fee;
document.getElementById('sum').innerHTML=n>0&&p>0?'You pay up to <b>$'+cost.toFixed(2)+'</b> (includes $'+fee.toFixed(2)+' Kalshi fee). '+
'If you\\'re right you get back <b>$'+n.toFixed(2)+'</b>.':'Enter how many contracts.';}}calc();</script>''', tab="find")

    @app.get("/ticket")
    def ticket_alias(ticker: str = "", side: str = "yes"):
        return RedirectResponse("/bet?" + urlencode({"ticker": ticker, "side": side}), status_code=303)

    @app.get("/bet")
    def bet(request: Request, ticker: str = "", side: str = "yes", contracts: str = "1", price: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        ticker = ticker.strip().upper()
        if ticker and not TICKER_RE.match(ticker):
            return choose_page(s, "", "yes", errors=["That doesn't look like a Kalshi market ticker."])
        contracts = contracts if contracts.isdigit() and int(contracts) > 0 else "1"
        price = price if price.isdigit() and 0 < int(price) < 100 else ""
        return choose_page(s, ticker, side if side in ("yes", "no") else "yes", contracts, price)

    @app.post("/bet")
    def review(request: Request, ticker: str = Form(""), side: str = Form("yes"),
               price: str = Form(""), contracts: str = Form("1")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        ticker = ticker.strip().upper()
        side = side if side in ("yes", "no") else ""
        errors = []
        if not TICKER_RE.match(ticker):
            errors.append("That doesn't look like a Kalshi market ticker.")
        if not side:
            errors.append("Pick YES or NO.")
        try:
            px, n = Decimal(price) / 100, int(contracts)
        except (InvalidOperation, ValueError):
            errors.append("Price and number of contracts must be whole numbers.")
            px, n = Decimal(0), 0
        cost = max_cost(n, px, s.kalshi_fee_rate) if n > 0 else Decimal(0)
        if not errors:
            errors += static_checks(s, n, px, cost)
        if errors:
            return choose_page(s, ticker if TICKER_RE.match(ticker) else "", side or "yes", contracts, price, errors)

        info = market_info(s, ticker)
        statement = bet_sentence(info.statement if info else ticker, side)
        question = info.question if info else ""
        fee = Decimal(str(kalshi_fee(float(px), n, s.kalshi_fee_rate)))
        exp = int(time.time()) + s.ticket_ttl_minutes * 60
        token = sign(s, {"k": "ticket", "env": s.kalshi_env, "ticker": ticker, "side": side, "count": n,
                         "price": str(px), "coid": str(uuid.uuid4()), "exp": exp, "label": statement[:200]})

        cash_line = ""
        if s.trading_keys_set:
            try:
                with trading_client(s) as c:
                    cash = c.balance_dollars()
                cash_line = (f'<p class="bad">You have {money(cash.quantize(Decimal("0.01")))} cash, less than this bet '
                             f'could cost. Add money on kalshi.com → Funds first, or Kalshi will refuse it.</p>'
                             if cash < cost else "")
            except TRADING_ERRORS:
                pass
        live = ('<p class="warn">This uses <b>real money</b> from your Kalshi account.</p>'
                if s.kalshi_env == "live" else "")
        return page(s, "Review bet", f'''{steps(1)}<h1>Review your bet</h1>
<p class="lead">Check every line. Nothing has been sent yet.</p>
<div class="card"><dl class="sum">
<dt>Your bet</dt><dd>{esc(statement)}</dd>
<dt>Market</dt><dd style="font-weight:400">{esc(question) or esc(ticker)}</dd>
<dt>Contracts</dt><dd>{n:,} at up to {cents(px)} each</dd>
<dt>You pay at most</dt><dd>{money(cost)} <span class="muted small" style="font-weight:400">(includes {money(fee)} Kalshi fee)</span></dd>
<dt>If you're right</dt><dd style="color:var(--accent)">You get {money(n)} back (profit {money(Decimal(n) - cost)})</dd>
<dt>If you're wrong</dt><dd style="color:var(--danger)">You lose {money(cost)}</dd>
</dl></div>
<div class="card">{live}{cash_line}
<p class="muted small">Limit order: it only fills at {cents(px)} or cheaper. If nobody sells within
{s.order_expiry_minutes} minutes, it cancels itself and you pay nothing. This review expires in {s.ticket_ttl_minutes} minutes.</p>
<form class="stack" method="post" action="/send"><input type="hidden" name="token" value="{esc(token)}">
<label class="check"><input type="checkbox" name="approve" value="yes" required>
I approve this bet: {esc(statement)}, {n:,} contracts, at most {money(cost)}</label>
<button>Send bet to Kalshi</button></form>
<p style="margin-top:12px"><a href="/find">Cancel, don't send</a></p></div>''', tab="find")

    @app.post("/send")
    def send(request: Request, token: str = Form(""), approve: str = Form("")):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()

        def refuse(msg: str) -> HTMLResponse:
            return page(s, "Not sent", f'''{steps(2)}<h1>Not sent</h1><div class="card"><p class="bad">{esc(msg)}</p>
<p>Nothing was bought.</p><p><a class="btn ghost" href="/">Back to Picks</a> <a href="/account">My account</a></p></div>''',
                        tab="find")

        t = verify(s, token, "ticket")
        if t is None:
            return refuse("This review is expired or invalid. Start the bet again from Picks or All bets.")
        if approve != "yes":
            return refuse("You didn't tick “I approve this bet”, so nothing was sent.")
        if t["env"] != s.kalshi_env:
            return refuse(f"This bet was reviewed for {t['env'].upper()}, but the site is now set to "
                          f"{s.kalshi_env.upper()}. Start again.")
        if os.environ.get("TRADING_HALTED") == "1":
            return refuse("Sending bets is turned off (TRADING_HALTED=1 in Vercel).")
        px, n = Decimal(t["price"]), int(t["count"])
        cost = max_cost(n, px, s.kalshi_fee_rate)
        problems = static_checks(s, n, px, cost)
        if problems:
            return refuse(" ".join(problems))
        try:
            with trading_client(s) as c:
                committed, open_n = committed_today(c, s)
                if committed + cost > Decimal(str(s.max_daily_dollars)):
                    return refuse(f"Today's bets could already cost {money(committed)}; this one ({money(cost)}) "
                                  f"would go over your {money(s.max_daily_dollars)} daily limit.")
                if open_n >= s.max_open_orders:
                    return refuse(f"You already have {open_n} waiting orders (the limit is {s.max_open_orders}). "
                                  "Cancel one in My account or wait for them to fill.")
                balance = c.balance_dollars()
                if balance < cost:
                    return refuse(f"Your cash is {money(balance.quantize(Decimal('0.01')))}; this bet could cost "
                                  f"{money(cost)}. Add money on kalshi.com → Funds first.")
                expiration = (int((datetime.now(timezone.utc) + timedelta(minutes=s.order_expiry_minutes)).timestamp())
                              if s.order_expiry_minutes > 0 else None)
                result = c.create_limit_buy(ticker=t["ticker"], side=t["side"], count=n, price=px,
                                            client_order_id=t["coid"], expiration_ts=expiration)
        except KalshiAPIError as exc:
            hint = " This bet may already have been sent; check My account." if exc.status == 409 else ""
            return refuse(f"Kalshi said no: {exc}.{hint}")
        except httpx.HTTPError as exc:
            return refuse(f"The connection dropped ({exc}). The bet may or may not have reached Kalshi. "
                          "Check “Waiting orders” and “Recent activity” in My account before trying again.")
        except (TradingNotConfigured, ValueError, PermissionError) as exc:
            return refuse(str(exc))
        order = result.get("order") or {}
        status = (order.get("status") or "resting").lower()
        headline, detail = ORDER_STATUS.get(status, (f"Sent ({status})", "Check My account for the latest."))
        filled = count_field(order, "fill_count") or 0
        return page(s, "Sent", f'''{steps(2)}<h1>{esc(headline)}</h1><div class="card good">
<p><b>{esc(t.get("label") or t["ticker"])}</b></p>
<p>{n:,} contracts at up to {cents(px)} · {filled:,} filled so far</p>
<p class="muted small">{esc(detail.format(mins=s.order_expiry_minutes))}</p></div>
<p><a class="btn" href="/account">See it in My account</a> <a class="btn ghost" href="/">Back to Picks</a></p>''', tab="find")

    return app
