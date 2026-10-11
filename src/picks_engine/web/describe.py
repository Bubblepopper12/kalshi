"""Turn Kalshi's market data into plain sentences people can act on.

Kalshi lists many markets per game (full game, halves, quarters, spreads at
several lines). The site shows full-game markets grouped by game, each choice as
"<what happens> · costs X¢ · pays $1.00 if right".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from ..kalshi.classify import parse_event_ticker
from ..kalshi.client import price_field

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

KIND_LABELS = {
    "moneyline": ("Who wins", "Pick the team you think wins the whole game."),
    "spread": ("Win by how much", "Bet on a team winning by more than a number of points."),
    "total": ("Total points", "Bet on whether both teams together score over a number."),
}

# Half, quarter and period markets (series like KXNFL2H, KXNBA1HWINNER, KXNCAAF1H).
_PARTIAL_TICKER = re.compile(r"[1-4]H|[1-4]Q|HALF|QUARTER|QTR|PERIOD", re.I)
_PARTIAL_TITLE = re.compile(r"\b(1st|2nd|3rd|4th|first|second|third|fourth)\s+(half|quarter|period)\b"
                            r"|\bhalftime\b|\bquarter\b", re.I)


def is_partial_game(series_ticker: str, *titles: str) -> bool:
    """True for half/quarter/period markets, which the site hides to keep things simple."""
    core = (series_ticker or "").upper().removeprefix("KX")
    if _PARTIAL_TICKER.search(core):
        return True
    return any(_PARTIAL_TITLE.search(t or "") for t in titles)


def local_zone():
    name = os.environ.get("APP_TIMEZONE", "America/Chicago")
    try:
        return ZoneInfo(name) if ZoneInfo else timezone.utc
    except Exception:  # unknown zone name or no tz database
        return timezone.utc


def when(value: str | datetime | None) -> str:
    """'Sun, Oct 18 · 3:25 PM' in the app's time zone (Central by default)."""
    if not value:
        return ""
    dt = value if isinstance(value, datetime) else None
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(local_zone())
    return local.strftime("%a, %b %-d · %-I:%M %p")


def day_label(d: date | None) -> str:
    return d.strftime("%a, %b %-d") if d else ""


def money(value: Decimal | float | int) -> str:
    return f"${Decimal(str(value)):,.2f}"


def cents(value: Decimal | None) -> str:
    return "—" if value is None else f"{Decimal(value) * 100:.0f}¢"


def outcome(m: dict, kind: str | None = None) -> str:
    """What has to happen for YES to win, as a short sentence."""
    sub = (m.get("yes_sub_title") or m.get("subtitle") or "").strip()
    title = (m.get("title") or "").strip().rstrip("?")
    if kind == "moneyline" and sub:
        low = sub.lower()
        if low in ("tie", "draw"):
            return "It ends in a draw" if low == "draw" else "It ends in a tie"
        return sub if re.search(r"\bwins?\b", low) else f"{sub} wins"
    return sub or title or m.get("ticker", "")


def bet_sentence(statement: str, side: str) -> str:
    return statement if side == "yes" else f"NOT: {statement}"


@dataclass
class Choice:
    ticker: str
    statement: str
    yes_ask: Decimal | None
    no_ask: Decimal | None


@dataclass
class Game:
    event_ticker: str
    title: str
    day: date | None
    choices: list[Choice] = field(default_factory=list)


def group_games(events: list[dict], kind: str) -> list[Game]:
    """Events with nested markets -> games with readable choices, soonest first."""
    games: list[Game] = []
    for ev in events:
        day, _ = parse_event_ticker(ev.get("event_ticker") or "")
        markets = [m for m in ev.get("markets") or [] if (m.get("status") or "active") in ("active", "open")]
        if not markets:
            continue
        g = Game(event_ticker=ev.get("event_ticker") or "", title=(ev.get("title") or "").strip(), day=day)
        for m in markets:
            g.choices.append(Choice(m["ticker"], outcome(m, kind), price_field(m, "yes_ask"), price_field(m, "no_ask")))
        if kind != "moneyline":
            g.choices.sort(key=lambda c: c.statement)
        games.append(g)
    games.sort(key=lambda g: (g.day or date.max, g.title))
    return games


def today_local() -> date:
    return datetime.now(local_zone()).date()
