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
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from .. import grading
from ..config import Settings
from ..kalshi.client import KalshiReadOnlyClient, amount_field, count_field, price_field
from ..kalshi.leagues import LEAGUES
from ..live import espn
from ..live.odds_api import OddsAPIError
from ..live.picks import STRONG_EDGE, size
from ..pricing.fees import kalshi_fee
from ..trading.client import KalshiAPIError, KalshiTradingClient, TradingNotConfigured
from ..trading.limits import max_cost, static_checks
from .account import committed_today, holdings, lookup_names, name_market
from .data import QUOTA_FLOOR, Sources, clear_caches
from .describe import KIND_LABELS, bet_sentence, cents, local_zone, money, qty, when
from .security import (COOKIE, MIN_PASSWORD_LENGTH, SESSION_HOURS, _password, _totp_secret, sign,  # noqa: F401
                       totp_code, totp_ok, verify)
from .ui import esc, page, steps
from . import ask as asking
from . import mdlite
from .views import SEARCH_JS, ask_box, bet_href, game_card, league_chips, patient_price, pick_card, search_bar

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")
MAX_GAMES = 300
MAX_ALL_BOARD = 60
MAX_GRADED = 60  # most recent markets graded per page load
RECENT_GRADED = 8  # orders graded on the Account page
RESEARCH_DIR = Path(os.environ.get("RESEARCH_DIR") or Path(__file__).resolve().parents[3] / "research" / "reports")
TAGS = {"edge": ("pos", "Edge found"), "watch": ("lean", "Worth watching"), "none": ("neg", "No edge"),
        "few": ("warn", "Too few games"), "check": ("warn", "Needs checking"), "kalshi-only": ("neg", "Kalshi-only test"), "error": ("bad", "Not loaded")}
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
               clock=None, ask_transport: httpx.BaseTransport | None = None,
               espn_transport: httpx.BaseTransport | None = None,
               reference_transport: httpx.BaseTransport | None = None) -> FastAPI:
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
        return sources(s).kalshi()

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

    @app.get("/favicon.ico")
    def favicon():
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" '
               'fill="#0b6e4f"/><path d="M9 22l5-6 4 3 5-8" stroke="#fff" stroke-width="3" fill="none" '
               'stroke-linecap="round" stroke-linejoin="round"/></svg>')
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

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
                recent = grading.fills_from(c.fills(), s.kalshi_fee_rate, s.kalshi_maker_fee_rate)[:RECENT_GRADED]
        except TRADING_ERRORS as exc:
            return page(s, "My account", f'<h1>My account</h1><div class="card bad">Couldn\'t read your Kalshi account: '
                        f'{esc(exc)}</div>', tab="home")
        with market_client(s) as rc:
            names = lookup_names(rc, [p.get("ticker") for p in positions if amount_field(p, "position")]
                                 + [o.get("ticker") for o in resting])
            graded = grading.grade(recent, grade_lookups(s, rc), now=now_utc())
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
<p style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap"><a class="btn" href="/">See today's picks</a>
<a class="btn ghost" href="/grades">Grade my past bets</a></p></div>''')

        rows = []
        for h in held:
            worth = f" · worth about {money(h.worth_now)} now" if h.worth_now is not None else ""
            rows.append(f'''<div class="row"><div class="what"><b>{esc(bet_sentence(h.name.statement, h.side))}</b>
<span class="muted small">{esc(h.name.question)}</span><br>
<span class="small">{qty(h.contracts)} contracts · pays {money(h.pays_if_right)} if right{worth}</span></div></div>''')
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

        parts.append('<div class="card"><h2>Recent trades, graded</h2><p class="muted small">Each grade is how much '
                     'less (or more) you paid than the bet was worth at kickoff, fees included. Winning or losing '
                     'doesn\'t change it. <a href="/grades">All grades and your luck →</a></p>'
                     + ("".join(grade_card(g) for g in graded.grades) or '<p class="muted">Nothing yet.</p>')
                     + "</div>")
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
    def picks_page(request: Request, league: str = "ALL", refresh: str = "", q: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        league = league.upper() if league.upper() in LEAGUES or league.upper() == "ALL" else "ALL"
        parts = [f'''<h1>Picks</h1>
<p class="lead">Bets where Kalshi's price is lower than what the sportsbooks think the outcome is worth.
It's math, not a guarantee, so keep bets small.</p>
{ask_box("")}
{league_chips(league, lambda code: "/?league=" + code, include_all=True)}''']
        if not s.odds_api_key:
            parts.append('''<div class="card warn"><h2>One more setup step</h2>
<p>Picks compare Kalshi with sportsbook prices, which come from The Odds API. Get a free key at
the-odds-api.com, then add it in Vercel → Settings → Environment Variables as <b>ODDS_API_KEY</b>
(Production, Sensitive) and redeploy.</p></div>''')
            return page(s, "Picks", "".join(parts), tab="picks")
        notes: list[str] = []
        try:
            if league == "ALL":
                got = sources(s).picks_all(refresh == "1")
                result, left, fetched = got.result, got.left, got.oldest
                if got.quiet:
                    notes.append(f"No games in the next 3 days: {', '.join(got.quiet)}.")
                if got.waiting:
                    notes.append(f"Skipped to save sportsbook lookups (fewer than {QUOTA_FLOOR} left this month): "
                                 f"{', '.join(got.waiting)}.")
                if got.failed:
                    notes.append(f"Couldn't load right now: {', '.join(got.failed)}.")
            else:
                result, left, fetched = sources(s).picks(league, refresh == "1")
        except (httpx.HTTPError, OddsAPIError) as exc:
            parts.append(f'<div class="card bad">Couldn\'t load prices right now: {esc(exc)}</div>')
            return page(s, "Picks", "".join(parts), tab="picks")

        cash = cash_balance(s)
        for p in result.picks:
            size(p, cash, s.max_order_dollars)
        name = "all leagues" if league == "ALL" else LEAGUES[league].name
        label = "" if league == "ALL" else f"{esc(name)} "
        status = [f"{result.games_matched} of {result.games_checked} {label}games compared with the sportsbooks"]
        if result.in_progress:
            status.append(f"{result.in_progress} already started")
        if fetched is not None:
            age = int((time.time() - fetched) // 60)
            status.append("sportsbook odds from just now" if age == 0 else f"sportsbook odds from {age} min ago")
        if left is not None:
            status.append(f"{left} sportsbook lookups left this month")
        status.append(f'<a href="/?league={league}&refresh=1">Refresh</a>')
        parts.append('<p class="status">' + "".join(f"<span>{x}</span>" for x in status) + "</p>")
        if notes:
            parts.append('<p class="muted small">' + esc(" ".join(notes)) + "</p>")

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
        hidden = 0
        if league == "ALL":  # every league at once: just the games that were compared
            shown = [g for g in board if g.matched or g.starts is not None][:MAX_ALL_BOARD]  # compared or underway
            hidden, board = len(board) - len(shown), shown
        parts.append('<section><h2>Every game <span class="muted small">Kalshi price vs. sportsbooks</span></h2>'
                     '<p class="muted small">Each box: the team, what it costs on Kalshi, the sportsbooks\' chance, '
                     'and the difference in points (green = cheaper on Kalshi).</p>')
        parts.append(search_bar(q, "Search: team, nickname or day", picks_filter=True))
        if board:
            parts.extend(game_card(g, s.picks_min_edge, now_utc()) for g in board)
            parts.append('<p class="muted empty" id="none" style="display:none">No games match your search.</p>')
        else:
            parts.append(f'<div class="card empty"><p class="muted">No upcoming {esc(name)} games on Kalshi right now.</p></div>')
        if hidden:
            parts.append(f'<p class="muted small">{hidden} more games weren\'t compared with the sportsbooks: '
                         'see <a href="/find">All bets</a>.</p>')
        elif result.unmatched:
            parts.append('<p class="muted small">Not compared (the sportsbooks don\'t list these the same way): '
                         + esc(", ".join(result.unmatched[:8])) + ("…" if len(result.unmatched) > 8 else "") + "</p>")
        parts.append("</section>")
        min_pts, strong_pts = f"{s.picks_min_edge * 100:g}", f"{max(s.picks_min_edge, STRONG_EDGE) * 100:g}"
        parts.append(f'''<details class="card"><summary>How picks work</summary>
<p style="margin-top:10px">1. The bot reads the odds from several sportsbooks (Pinnacle, DraftKings, FanDuel and others)
and removes their built-in profit margin, which gives a fair chance for each outcome.</p>
<p>2. It compares that chance with Kalshi's live price plus Kalshi's fee. If Kalshi is at least
{min_pts} points cheaper, it's a pick.</p>
<p>3. <b>Strong</b> means at least {strong_pts} points, 3+ sportsbooks, Pinnacle priced it and agrees, and Kalshi
prices aren't stretched. <b>Good</b> means it clears {min_pts} points but misses one of those.</p>
<p>Games that have already started aren't compared: in-game prices move with the score.</p>
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
        games, error, failed = [], "", []
        try:
            loaded = sources(s).games(list(LEAGUES) if league == "ALL" else [league], kind)
            games, failed = loaded.games, loaded.failed
        except httpx.HTTPError as exc:
            error = f"Couldn't load games from Kalshi right now ({exc}). Try again in a minute."
        if failed and not games:
            error = "Couldn't load games from Kalshi right now. Try again in a minute."
        games.sort(key=lambda g: (g.day or date.max, g.title))
        words = q.lower().split()
        if words:  # a search in the address bar is applied before the display limit
            games = [g for g in games if all(w in g.keywords(LEAGUES[g.league].name) for w in words)]
        total = len(games)
        games = games[:MAX_GAMES]

        link = lambda **kw: "/find?" + urlencode({"league": league, "kind": kind} | kw)  # noqa: E731
        kind_chips = "".join(f'<a class="keepq{" on" if k == kind else ""}" href="{esc(link(kind=k))}">{label}</a>'
                             for k, (label, _) in KIND_LABELS.items())
        parts = [f'''<h1>All bets</h1>
<p class="lead">Every game Kalshi offers. These are not recommendations (those are on Picks). Each box shows what
it costs; it pays $1.00 if you're right.</p>
{search_bar(q, "Search: eagles, lakers, sunday…")}
{league_chips(league, lambda code: link(league=code), include_all=True)}
<div class="chips">{kind_chips}</div><p class="muted small">{esc(KIND_LABELS[kind][1])} Full-game bets only.</p>''']
        if failed and games:
            parts.append(f'<p class="thin">Couldn&#x27;t load {esc(", ".join(failed))} right now; showing the rest.</p>')
        if total > len(games):
            parts.append(f'<p class="thin">Showing the first {len(games)} of {total} games by date. Pick a league or '
                         'search to narrow it down.</p>')
        if error:
            parts.append(f'<div class="card bad">{esc(error)}</div>')
        elif not games:
            parts.append('<div class="card empty"><p class="muted">No open bets of this kind right now.</p></div>')
        else:
            parts.extend(game_card(g, s.picks_min_edge, now_utc()) for g in games)
            parts.append('<p class="muted empty" id="none" style="display:none">No games match your search.</p>')
        parts.append(SEARCH_JS)
        return page(s, "All bets", "".join(parts), tab="find")

    # ------------------------------------------------------------ research

    def research_summary() -> dict | None:
        try:
            return json.loads((RESEARCH_DIR / "summary.json").read_text())
        except (OSError, ValueError):
            return None

    @app.get("/research")
    def research_page(request: Request):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        data = research_summary()
        parts = ['''<h1>Research</h1><p class="lead">What Kalshi's past prices say about where the money is.
Each league's finished games are tested: were cheap contracts overpriced, and did buying when Kalshi was cheaper
than the sportsbooks make money?</p>''']
        if not data:
            parts.append('''<div class="card empty"><h3>No research yet</h3><p class="muted">It runs on GitHub every
morning, or anytime from GitHub → your <b>kalshi</b> repository → Actions → Research → Run workflow.
Results show up here a couple of minutes after it finishes.</p></div>''')
            return page(s, "Research", "".join(parts), tab="research")
        parts.append(f'<p class="status"><span>Updated {esc(when(data.get("generated")))}</span>'
                     f'<span>Games since {esc(data.get("since"))}</span></p>')
        for lg in data.get("leagues") or []:
            cls, label = TAGS.get(lg.get("tag"), ("neg", ""))
            if lg.get("source"):
                facts = f'{lg.get("games", 0):,} games · closing lines from {esc(lg["source"])}'
            else:
                facts = f'{lg.get("games", 0):,} games' if lg.get("games") else ""
            points = "".join(f"<li>{esc(p)}</li>" for p in lg.get("points") or [])
            points = f'<ul class="points">{points}</ul>' if points else ""
            more = (f'<p class="actions"><a href="/research/{esc(lg["code"])}">See the full tables →</a></p>'
                    if lg.get("tag") != "error" else "")
            parts.append(f'''<article class="card"><span class="badge {cls}">{esc(label)}</span>
<span class="muted small">{facts}</span><h2 style="margin-top:8px">{esc(lg.get("name"))}</h2>
<p class="verdict">{esc(lg.get("verdict") or lg.get("error"))}</p>{points}{more}</article>''')
        if data.get("pooled"):
            parts.append('<div class="card report">' + mdlite.render("\n".join(data["pooled"]), shift=0) + "</div>")
        parts.append('''<details class="card"><summary>How to read this</summary>
<p style="margin-top:10px"><b>Return per bet</b> is what each $1 bet made or lost on average, after Kalshi's fee.
+5% means about 5¢ profit per dollar.</p>
<p><b>Prediction error</b> (log loss) measures how close prices were to what happened. Lower is better.</p>
<p>A few dozen bets can look great or awful by luck. Only trust a pattern after a few hundred.</p></details>''')
        return page(s, "Research", "".join(parts), tab="research")

    @app.get("/research/{code}")
    def research_league(request: Request, code: str):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        code = code.upper()
        path = RESEARCH_DIR / f"{code}.md"
        if code not in LEAGUES or not path.is_file():
            return page(s, "Research", '<div class="card">No report for that league yet. '
                        '<a href="/research">Back to Research</a></div>', tab="research")
        return page(s, f"Research: {LEAGUES[code].name}", '<p><a href="/research">← All leagues</a></p>'
                    '<div class="card report">' + mdlite.render(path.read_text()) + "</div>", tab="research")

    # ------------------------------------------------------------ ask

    def ask_tools(s: Settings) -> dict[str, asking.Tool]:
        def pick_info(p) -> dict:
            c, g = p.choice, p.game
            return {"league": LEAGUES[g.league].name, "game": g.title,
                    "starts": when(g.starts) if g.starts else str(g.day),
                    "bet": c.statement, "strength": p.strength, "edge_points": round(p.edge * 100, 1),
                    "kalshi_price_cents": float(c.yes_ask * 100), "fee_cents": round(float(p.fee) * 100, 1),
                    "sportsbooks_chance_pct": round(c.book * 100, 1),
                    "pinnacle_chance_pct": round(c.pinnacle * 100, 1) if c.pinnacle is not None else None,
                    "cautions": p.notes, "suggested_contracts": p.contracts,
                    "review_link": bet_href(c.ticker, "yes", max(p.contracts, 1))}

        def get_picks(args: dict) -> dict:
            league = str(args.get("league") or "ALL").upper()
            if not s.odds_api_key:
                return {"error": "Sportsbook odds aren't set up (no ODDS_API_KEY), so there are no picks."}
            cash = cash_balance(s)
            if league in LEAGUES:
                result, left, _ = sources(s).picks(league)
            else:
                got = sources(s).picks_all()
                result, left = got.result, got.left
            for p in result.picks + result.near:
                size(p, cash, s.max_order_dollars)
            return {"picks": [pick_info(p) for p in result.picks[:10]],
                    "close_calls": [pick_info(p) for p in result.near[:5]],
                    "games_compared": result.games_matched, "games_on_kalshi": result.games_checked,
                    "cash_dollars": float(cash) if cash is not None else None,
                    "max_per_bet_dollars": s.max_order_dollars, "sportsbook_lookups_left": left}

        def find_games(args: dict) -> dict:
            league = str(args.get("league") or "ALL").upper()
            words = str(args.get("query") or "").lower().split()
            loaded = sources(s).games(list(LEAGUES) if league not in LEAGUES else [league], "moneyline")
            games = [g for g in loaded.games if all(w in g.keywords(LEAGUES[g.league].name) for w in words)]
            games.sort(key=lambda g: (g.day or date.max, g.title))

            def choice(c) -> dict:
                return {"outcome": c.statement,
                        "kalshi_price_cents": float(c.yes_ask * 100) if c.yes_ask is not None else None,
                        "edge_points": round(c.edge * 100, 1) if c.edge is not None else None,
                        "review_link": bet_href(c.ticker, "yes")}

            return {"games": [{"league": LEAGUES[g.league].name, "game": g.title, "day": str(g.day),
                               "choices": [choice(c) for c in g.choices]} for g in games[:12]],
                    "total_found": len(games), "leagues_not_loaded": loaded.failed}

        def research_results(args: dict) -> dict:
            return research_summary() or {"error": "No research has run yet."}

        def my_account(args: dict) -> dict:
            if not s.trading_keys_set:
                return {"error": "Kalshi keys aren't set up."}
            with trading_client(s) as c:
                cash = c.balance_dollars()
                committed, _ = committed_today(c, s)
                positions = c.positions()
            with market_client(s) as rc:
                names = lookup_names(rc, [p.get("ticker") for p in positions if amount_field(p, "position")])
            return {"cash_dollars": float(cash), "spent_today_dollars": float(committed),
                    "daily_limit_dollars": s.max_daily_dollars, "max_per_bet_dollars": s.max_order_dollars,
                    "open_bets": [{"bet": bet_sentence(h.name.statement, h.side), "contracts": float(h.contracts),
                                   "pays_if_right": float(h.pays_if_right)} for h in holdings(positions, names)]}

        league = {"type": "string", "enum": ["ALL", *LEAGUES], "description": "League code, or ALL for every league"}
        return {
            "get_picks": asking.Tool(
                "Today's best bets: where Kalshi is cheaper than the sportsbooks' fair chance, with review links.",
                {"type": "object", "properties": {"league": league}}, get_picks),
            "find_games": asking.Tool(
                "Search open Kalshi games by team, nickname, league or day, with prices and review links.",
                {"type": "object", "properties": {"query": {"type": "string", "description": "e.g. eagles, sunday"},
                                                  "league": league}, "required": ["query"]}, find_games),
            "research_results": asking.Tool("What testing Kalshi's past prices found, per league.",
                                            {"type": "object", "properties": {}}, research_results),
            "my_account": asking.Tool("The person's Kalshi cash, today's spending, limits and open bets.",
                                      {"type": "object", "properties": {}}, my_account),
        }

    @app.get("/ask")
    def ask(request: Request, q: str = ""):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        q = q.strip()[:500]
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not q:
            return RedirectResponse("/", status_code=303)
        if not key:
            return RedirectResponse(asking.route(q), status_code=303)
        now = now_utc().astimezone(local_zone()).strftime("%A %b %-d, %Y %-I:%M %p %Z")
        reply = asking.answer(q, ask_tools(s), key, os.environ.get("ASK_MODEL") or asking.DEFAULT_MODEL,
                              now=now, transport=ask_transport)
        body = asking.to_html(reply.text) if reply.text else ""
        if reply.error:
            body += (f'<p class="bad">{esc(reply.error)}</p><p>Meanwhile: <a href="{esc(asking.route(q))}">'
                     'the page that matches your words</a>.</p>')
        return page(s, "Ask", f'''<h1>Ask</h1>{ask_box("")}<div class="card"><p class="question">{esc(q)}</p>
<div class="reply">{body}</div><p class="muted small">Answers use live Kalshi and sportsbook prices. Nothing is
bet until you review and approve it.</p></div>''', tab="picks")

    # ------------------------------------------------------------ grades

    def grade_lookups(s: Settings, rc: KalshiReadOnlyClient) -> grading.Lookups:
        def fetch(url: str) -> str:
            with httpx.Client(timeout=30, follow_redirects=True, transport=reference_transport) as http:
                resp = http.get(url)
                resp.raise_for_status()
                return resp.content.decode("utf-8-sig", errors="replace")

        return grading.Lookups(
            market=rc.market,
            event=lambda t: rc.get(f"/events/{t}", {"with_nested_markets": "true"}),
            candles=lambda series, ticker, a, b, mins: rc.candlesticks(series, ticker, a, b, mins),
            start_time=lambda league, day, teams: espn.find_start(league, day, teams, transport=espn_transport),
            books_close=_books_close(fetch),
        )

    books_cache: dict = {}

    def _books_close(fetch):
        if "fn" not in books_cache or time.time() - books_cache["at"] > 6 * 3600:
            books_cache.update(fn=grading.books_close_lookup(fetch), at=time.time())
        return books_cache["fn"]

    def grade_card(g: grading.Grade) -> str:
        f = g.fill
        verb = "Bought" if f.action == "buy" else "Sold"
        side = "" if f.side == "yes" else " (NO side)"
        cls = {"A": "pos", "B": "lean", "C": "neg", "D": "warn", "F": "bad"}.get(g.letter, "neg")
        lines = [f"{verb} {qty(f.contracts)} at {f.price * 100:.1f}¢ + {f.fee * 100:.1f}¢ fee · "
                 f"{esc(when(f.at))}"]
        if g.graded:
            moment = "now" if g.kind == "future" else "at kickoff"
            source = {"Pinnacle's closing line": "Pinnacle's closing line"}.get(g.fair_source, "Kalshi")
            lines.append(f"Worth {g.fair * 100:.1f}¢ {moment} (per {esc(source)}) · "
                         f"<b>{g.edge:+.1f} points</b> per contract · worth {money_signed(g.expected)} when you made it")
            if g.books_close is not None and g.kalshi_close is not None:
                lines.append(f'<span class="muted">Kalshi at kickoff: {g.kalshi_close * 100:.1f}¢</span>')
        if g.actual is not None:
            lines.append(f"{'Won' if g.result == 'won' else 'Lost'}: {money_signed(g.actual)}")
        elif g.result == "open":
            lines.append('<span class="muted">Not settled yet</span>')
        notes = "".join(f"<li>{esc(n)}</li>" for n in g.notes)
        lg = LEAGUES[g.league].name + " · " if g.league in LEAGUES else ""
        return (f'<div class="row grade"><span class="badge {cls} big-letter">{esc(g.letter)}</span>'
                f'<div class="what"><b>{esc(bet_sentence(g.bet, f.side))}{side}</b>'
                f'<span class="muted small">{esc(lg)}{esc(g.question)}</span>'
                + "".join(f'<div class="small">{x}</div>' for x in lines)
                + (f'<ul class="cautions">{notes}</ul>' if notes else "") + "</div></div>")

    def money_signed(x: float) -> str:
        return ("+" if x >= 0 else "−") + money(Decimal(str(abs(x))).quantize(Decimal("0.01")))

    @app.get("/grades")
    def grades_page(request: Request):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        if not s.trading_keys_set:
            return page(s, "Grades", '<h1>Grades</h1><div class="card">Kalshi keys aren\'t set up, so there are no '
                        'trades to grade.</div>', tab="home")
        try:
            with trading_client(s) as c:
                raw = c.all_fills()
        except TRADING_ERRORS as exc:
            return page(s, "Grades", f'<h1>Grades</h1><div class="card bad">Couldn\'t read your trades: {esc(exc)}'
                        '</div>', tab="home")
        fills = grading.fills_from(raw, s.kalshi_fee_rate, s.kalshi_maker_fee_rate)
        recent = list(dict.fromkeys(f.ticker for f in sorted(fills, key=lambda f: f.at, reverse=True)))[:MAX_GRADED]
        fills = [f for f in fills if f.ticker in recent]
        with market_client(s) as rc:
            summary = grading.grade(fills, grade_lookups(s, rc), now=now_utc())

        parts = ['''<h1>Grades</h1><p class="lead">Every bet graded by the math, not by whether it won: did you pay
less than it was really worth just before the game started? That's what predicts long-run profit.</p>''']
        if not summary.grades:
            parts.append('<div class="card empty"><p class="muted">No trades yet.</p></div>')
            return page(s, "Grades", "".join(parts), tab="home")
        if summary.graded:
            luck, sd = summary.luck, summary.luck_sd
            if not summary.settled:
                luck_txt = "Nothing has settled yet."
            elif abs(luck) <= sd:
                luck_txt = "That's normal luck: results are close to what the math expected."
            elif luck > 0:
                luck_txt = "You've won more than the math expected: luck, which tends not to last."
            else:
                luck_txt = "You've won less than the math expected: bad luck, which tends to even out."
            cls = {"A": "pos", "B": "lean", "C": "neg", "D": "warn", "F": "bad"}.get(summary.letter, "neg")
            parts.append(f'''<div class="card"><div class="grid">
<div><div class="muted">Overall grade</div><div class="big"><span class="badge {cls} big-letter">{summary.letter}</span>
{summary.avg_edge:+.1f} pts</div><div class="muted small">average edge per contract, fees included</div></div>
<div><div class="muted">Beat the closing price</div><div class="big">{summary.beat_close} of {len(summary.graded)}</div>
<div class="muted small">bets bought below what they were worth at kickoff</div></div>
<div><div class="muted">Worth when you made them</div><div class="big">{money_signed(summary.expected)}</div>
<div class="muted small">the math's value of all graded bets</div></div>
<div><div class="muted">Actual result (settled)</div><div class="big">{money_signed(summary.actual)}</div>
<div class="muted small">luck {money_signed(luck)} · normal swing ±{money(Decimal(str(sd)).quantize(Decimal("0.01")))}</div></div>
</div><p class="note" style="margin-top:12px">{esc(luck_txt)}</p></div>''')
        ungraded = len(summary.grades) - len(summary.graded)
        parts.append('<div class="card"><h2>Your trades, newest first</h2>'
                     + (f'<p class="muted small">{ungraded} can\'t be graded (reasons shown on each).</p>' if ungraded else "")
                     + "".join(grade_card(g) for g in summary.grades) + "</div>")
        parts.append('''<details class="card"><summary>How grades work</summary>
<p style="margin-top:10px"><b>Fair price.</b> For NFL and soccer winner bets: Pinnacle's closing line (the sharpest
sportsbook, margin removed). Otherwise Kalshi's own middle price one minute before kickoff. Kickoff times come from ESPN.</p>
<p><b>Edge</b> = fair price − what you paid (with the fee). +3 points means you paid 3¢ less than it was worth.
A ≥ +3 · B +1 to +3 · C −1 to +1 · D −3 to −1 · F below −3.</p>
<p><b>Luck</b> = actual result − what the math expected. The "normal swing" is one standard deviation: luck inside
it is ordinary. Over many bets, luck shrinks and your edge is what's left.</p>
<p>Bets placed during a game aren't graded (prices move with the score). Combos use the first leg's kickoff.
Season-long bets are graded by how far the price has moved since you bought.</p></details>''')
        return page(s, "Grades", "".join(parts), tab="home")

    # ------------------------------------------------------------ bet: choose → review → send

    def market_info(s: Settings, ticker: str):
        try:
            with market_client(s) as rc:
                m = rc.market(ticker)
        except httpx.HTTPError:
            m = {}
        return name_market(m) if m else None

    def choose_page(s: Settings, ticker: str, side: str, contracts: str = "1", price: str = "",
                    errors=(), mode: str = "fast") -> HTMLResponse:
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
        bid = info.yes_bid if side == "yes" else info.no_bid
        ask_c = int(ask * 100) if ask is not None and 0 < ask < 1 else None
        patient_c = patient_price(ask, bid)
        mode = mode if mode == "patient" and patient_c else "fast"
        price = price or str(patient_c if mode == "patient" else ask_c or "")
        statement = bet_sentence(info.statement, side)
        if patient_c:
            save = ask_c - patient_c
            patient_opt = f'''<label class="check"><input type="radio" name="mode" value="patient" data-p="{patient_c}"
{"checked" if mode == "patient" else ""}> <span>Patient: offer {patient_c}¢ and wait<br><span class="muted small"
style="font-weight:400">Saves {save}¢ per contract and pays about ¼ of the fee, but it only goes through if someone sells
to you within {s.patient_expiry_minutes} minutes. If not, it cancels and you pay nothing.</span></span></label>'''
        else:
            patient_opt = ('<p class="muted small">Patient offer not available: the buy and sell prices are only 1¢ '
                           'apart, so there\'s nothing to save.</p>')
        return page(s, "Bet", f'''{steps(0)}<h1>How many?</h1>{err}
<div class="card"><div class="muted small">You're betting</div><h2 style="margin:4px 0">{esc(statement)}</h2>
<p class="muted small">{esc(info.question)}</p>
<p>Right now it costs <b>{cents(ask)}</b> per contract. Each contract pays <b>$1.00</b> if you're right.</p>
<form class="stack" method="post" action="/bet" oninput="calc()" onchange="pick(event)">
<input type="hidden" name="ticker" value="{esc(info.ticker)}"><input type="hidden" name="side" value="{esc(side)}">
<label>Number of contracts<input id="n" name="contracts" type="number" min="1" step="1" value="{esc(contracts)}" required></label>
<div class="note" style="display:grid;gap:10px"><b>How do you want to buy?</b>
<label class="check"><input type="radio" name="mode" value="fast" data-p="{ask_c or ""}" {"checked" if mode == "fast" else ""}>
<span>Buy now at {cents(ask)}<br><span class="muted small" style="font-weight:400">Goes through right away.
Normal Kalshi fee.</span></span></label>{patient_opt}</div>
<details><summary>Advanced: set your own max price</summary>
<label style="margin-top:10px">Max price (¢)<input id="p" name="price" type="number" min="1" max="99" value="{esc(price)}" required></label>
<p class="muted small">Your order only fills at this price or cheaper.</p></details>
<div class="note" id="sum">…</div>
<button>Review bet →</button></form>
<p class="muted small" style="margin-top:12px">Your limits: {money(s.max_order_dollars)} per bet, {money(s.max_daily_dollars)} per day.</p></div>
<script>
function mode(){{var r=document.querySelector('input[name=mode]:checked');return r?r.value:'fast';}}
function pick(e){{if(e.target.name==='mode'&&e.target.dataset.p){{document.getElementById('p').value=e.target.dataset.p;calc();}}}}
function calc(){{var n=parseInt(document.getElementById('n').value)||0,p=(parseInt(document.getElementById('p').value)||0)/100;
var rate=mode()==='patient'?{s.kalshi_maker_fee_rate}:{s.kalshi_fee_rate};
var fee=Math.ceil(rate*n*p*(1-p)*100-1e-9)/100,cost=n*p+fee;
document.getElementById('sum').innerHTML=n>0&&p>0?'You pay up to <b>$'+cost.toFixed(2)+'</b> (includes about $'+fee.toFixed(2)+' Kalshi fee). '+
'If you\\'re right you get back <b>$'+n.toFixed(2)+'</b>.':'Enter how many contracts.';}}calc();</script>''', tab="find")

    @app.get("/ticket")
    def ticket_alias(ticker: str = "", side: str = "yes"):
        return RedirectResponse("/bet?" + urlencode({"ticker": ticker, "side": side}), status_code=303)

    @app.get("/bet")
    def bet(request: Request, ticker: str = "", side: str = "yes", contracts: str = "1", price: str = "",
            mode: str = "fast"):
        if (blocked := guard(request)) is not None:
            return blocked
        s = settings()
        ticker = ticker.strip().upper()
        if ticker and not TICKER_RE.match(ticker):
            return choose_page(s, "", "yes", errors=["That doesn't look like a Kalshi market ticker."])
        contracts = contracts if contracts.isdigit() and int(contracts) > 0 else "1"
        price = price if price.isdigit() and 0 < int(price) < 100 else ""
        return choose_page(s, ticker, side if side in ("yes", "no") else "yes", contracts, price, mode=mode)

    @app.post("/bet")
    def review(request: Request, ticker: str = Form(""), side: str = Form("yes"),
               price: str = Form(""), contracts: str = Form("1"), mode: str = Form("fast")):
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
            return choose_page(s, ticker if TICKER_RE.match(ticker) else "", side or "yes", contracts, price, errors,
                               mode=mode)
        mode = "patient" if mode == "patient" else "fast"

        info = market_info(s, ticker)
        statement = bet_sentence(info.statement if info else ticker, side)
        question = info.question if info else ""
        fee_rate = s.kalshi_maker_fee_rate if mode == "patient" else s.kalshi_fee_rate
        fee = Decimal(str(kalshi_fee(float(px), n, fee_rate)))
        likely = (n * px + fee).quantize(Decimal("0.01"))  # what it should cost; limits use the worst case (cost)
        wait = s.patient_expiry_minutes if mode == "patient" else s.order_expiry_minutes
        exp = int(time.time()) + s.ticket_ttl_minutes * 60
        token = sign(s, {"k": "ticket", "env": s.kalshi_env, "ticker": ticker, "side": side, "count": n,
                         "price": str(px), "coid": str(uuid.uuid4()), "exp": exp, "label": statement[:200],
                         "mode": mode})

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
<dt>How</dt><dd>{"Patient offer: waits for a seller at your price" if mode == "patient" else "Buy now"}</dd>
<dt>Contracts</dt><dd>{n:,} at up to {cents(px)} each</dd>
<dt>You pay</dt><dd>{money(likely)} <span class="muted small" style="font-weight:400">(includes about {money(fee)} Kalshi fee)</span></dd>
<dt>If you're right</dt><dd style="color:var(--accent)">You get {money(n)} back (profit {money(Decimal(n) - likely)})</dd>
<dt>If you're wrong</dt><dd style="color:var(--danger)">You lose {money(likely)}</dd>
</dl></div>
<div class="card">{live}{cash_line}
<p class="muted small">Limit order: it only fills at {cents(px)} or cheaper. If nobody sells within
{wait} minutes, it cancels itself and you pay nothing. This review expires in {s.ticket_ttl_minutes} minutes.</p>
<form class="stack" method="post" action="/send"><input type="hidden" name="token" value="{esc(token)}">
<label class="check"><input type="checkbox" name="approve" value="yes" required>
I approve this bet: {esc(statement)}, {n:,} contracts at up to {cents(px)} ({money(likely)})</label>
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
                wait = s.patient_expiry_minutes if t.get("mode") == "patient" else s.order_expiry_minutes
                expiration = (int((datetime.now(timezone.utc) + timedelta(minutes=wait)).timestamp())
                              if wait > 0 else None)
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
<p class="muted small">{esc(detail.format(mins=s.patient_expiry_minutes if t.get("mode") == "patient" else s.order_expiry_minutes))}</p></div>
<p><a class="btn" href="/account">See it in My account</a> <a class="btn ghost" href="/">Back to Picks</a></p>''', tab="find")

    return app
