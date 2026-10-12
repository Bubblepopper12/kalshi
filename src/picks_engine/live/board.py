"""One shared picture of a game: its outcomes, Kalshi prices, and (when known) the sportsbooks' view.

Both the Picks page and All bets are built from these, so a game always looks
the same wherever it appears.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from ..kalshi.classify import parse_event_ticker
from ..kalshi.client import price_field
from .nicknames import extra_words

STRETCH_WARN = Decimal("1.10")  # a full set of outcomes costing over $1.10 means thin, stretched prices


def outcome_text(m: dict, kind: str | None = None) -> str:
    """What has to happen for YES to win, as a short sentence."""
    if combo := combo_legs(m):
        return f"{len(combo)}-leg combo: " + "; ".join(combo)
    sub = (m.get("yes_sub_title") or m.get("subtitle") or "").strip()
    title = (m.get("title") or "").strip().rstrip("?")
    if kind == "moneyline" and sub:
        low = sub.lower()
        if low in ("tie", "draw"):
            return "It ends in a draw" if low == "draw" else "It ends in a tie"
        return sub if re.search(r"\bwins?\b", low) else f"{sub} wins"
    return sub or title or m.get("ticker", "")


def combo_legs(m: dict) -> list[str]:
    """Kalshi combos read "yes Texas,yes Ohio St.,no Josh Allen: 30+": one plain line per leg."""
    text = (m.get("title") or m.get("yes_sub_title") or "").strip()
    if not ((m.get("event_ticker") or m.get("ticker") or "").upper().startswith("KXMVE") or m.get("mve_selected_legs")):
        return []
    legs = []
    for part in re.split(r",(?=\s*(?:yes|no)\s)", text, flags=re.I):
        part = part.strip()
        if mt := re.match(r"(yes|no)\s+(.*)", part, re.I):
            part = mt.group(2) if mt.group(1).lower() == "yes" else f"NOT {mt.group(2)}"
        if part:
            legs.append(part)
    return legs


@dataclass
class Choice:
    ticker: str
    name: str  # Kalshi's name for the outcome ("Philadelphia", "Tie", "Over 45.5 points scored")
    statement: str  # "Philadelphia wins"
    yes_ask: Decimal | None
    yes_bid: Decimal | None
    no_ask: Decimal | None
    # Filled in when the game is matched with the sportsbooks:
    book: float | None = None  # their fair chance, margin removed (median across books)
    books: list[str] = field(default_factory=list)
    book_low: float | None = None
    book_high: float | None = None
    pinnacle: float | None = None  # the sharpest book's own number, when it's in the feed
    fee: Decimal | None = None  # Kalshi fee per contract at the ask
    edge: float | None = None  # book - (ask + fee); positive = cheaper on Kalshi

    @property
    def cost(self) -> Decimal | None:
        return None if self.yes_ask is None else self.yes_ask + (self.fee or Decimal(0))

    @property
    def gap(self) -> Decimal | None:
        """Buy price minus sell price; wide gaps mean few traders."""
        if self.yes_ask is None or self.yes_bid is None:
            return None
        return self.yes_ask - self.yes_bid

    @property
    def buyable(self) -> bool:
        return self.yes_ask is not None and 0 < self.yes_ask < 1


@dataclass
class Game:
    league: str
    kind: str  # moneyline | spread | total
    event_ticker: str
    title: str
    day: date | None
    choices: list[Choice]
    starts: datetime | None = None  # known once matched with the sportsbooks
    matched: bool = False
    names: list[str] = field(default_factory=list)  # extra searchable names (sportsbook full names)

    @property
    def stretch(self) -> Decimal | None:
        """Total cost of every outcome (winner markets only). About $1.00 in a healthy market."""
        if self.kind != "moneyline" or not self.choices or not all(c.buyable for c in self.choices):
            return None
        return sum((c.yes_ask for c in self.choices), Decimal(0))

    @property
    def stretched(self) -> bool:
        return self.stretch is not None and self.stretch > STRETCH_WARN

    @property
    def best_edge(self) -> float | None:
        edges = [c.edge for c in self.choices if c.edge is not None]
        return max(edges) if edges else None

    def keywords(self, league_name: str = "") -> str:
        parts = [self.title, league_name, self.league, *self.names]
        for c in self.choices:
            parts += [c.name, extra_words(self.league, c.name)]
        if self.day:
            parts += [self.day.strftime("%a %A %b %B %-d"), self.day.isoformat()]
        return " ".join(p for p in parts if p).lower()


def games_from_events(events: list[dict], league: str, kind: str) -> list[Game]:
    """Kalshi events (with nested markets) -> games with readable choices, soonest first."""
    games: list[Game] = []
    for ev in events:
        markets = [m for m in ev.get("markets") or [] if (m.get("status") or "active") in ("active", "open")]
        if not markets:
            continue
        day, _ = parse_event_ticker(ev.get("event_ticker") or "")
        choices = [Choice(ticker=m["ticker"], name=(m.get("yes_sub_title") or "").strip(),
                          statement=outcome_text(m, kind), yes_ask=price_field(m, "yes_ask"),
                          yes_bid=price_field(m, "yes_bid"), no_ask=price_field(m, "no_ask")) for m in markets]
        if kind == "moneyline":  # teams first, the draw last
            choices.sort(key=lambda c: c.name.lower() in ("tie", "draw"))
        else:
            choices.sort(key=lambda c: c.statement)
        games.append(Game(league=league, kind=kind, event_ticker=ev.get("event_ticker") or "",
                          title=(ev.get("title") or "").strip(), day=day, choices=choices))
    games.sort(key=lambda g: (g.day or date.max, g.title))
    return games
