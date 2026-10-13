"""Every Kalshi line priced: winners, spreads ("Bayern wins by 3+"), totals ("over 3.5 goals"),
both teams to score — on both sides (YES and NO), so "under 3.5" is a pick too.

Winners are priced straight from the sportsbooks (see picks.py). Spreads, totals and both-teams-
to-score are priced by the models in pricing/models.py, fitted to the same sportsbooks' main
lines for that game; a line far from the books' own needs a bigger edge to count.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ..kalshi.client import price_field
from ..pricing.devig import devig
from ..pricing.fees import fee_per_contract
from ..pricing.models import PointsModel, SoccerModel, fit_points, fit_soccer
from ..pricing.soccer_calibration import calibrated
from .picks import LONGSHOT_EDGE, LONGSHOT_PRICE, SHARP_BOOKS, Pick, book_views
from .teams import name_matches

KINDS = {"winner": "Winners", "spread": "Spreads", "total": "Totals", "btts": "Both teams score"}
MODEL_EDGE = 0.05  # model-priced lines need 5+ points (the model adds its own error)
LIQUID_SPREAD = Decimal("0.06")  # lines with a tighter buy/sell gap than this say where Kalshi really is
LEVEL_FLOOR = 0.02  # disagreements smaller than this across a game's ladder are noise
LEAN_EDGE = 0.01  # a "lean": at least 1 point under fair value after fees, but short of the pick bar
STRETCH = {"soccer": 1.0, "points": 4.0}  # lines further than this from the books' own are "far"
# Leagues whose margin/total shape hasn't been checked against enough real results: only price lines this
# close to the books' own (spread, total). The NFL uses real results (see pricing/football_margins.py).
NEAR_ONLY = {"NBA": (4.0, 6.0), "CFB": (4.0, 6.0)}


@dataclass
class Bet:
    league: str
    game: str
    starts: datetime | None
    kind: str  # winner | spread | total | btts
    ticker: str
    side: str  # yes | no
    headline: str  # "Bayern Munich wins by 3+ goals", "Under 3.5 goals"
    ask: Decimal
    fee: Decimal
    fair: float
    source: str
    books: list[str] = field(default_factory=list)
    exact: bool = True  # priced from the books' own line, not extrapolated by the model
    notes: list[str] = field(default_factory=list)
    strength: str = "Good"
    contracts: int = 0
    stake: Decimal = Decimal(0)
    pinnacle: float | None = None
    level_gap: float = 0.0  # how far the model sits above Kalshi on this side across the game's whole ladder

    @property
    def cost(self) -> Decimal:
        return self.ask + self.fee

    @property
    def edge(self) -> float:
        return self.fair - float(self.cost)


def from_pick(p: Pick, league: str) -> Bet:
    c, g = p.choice, p.game
    b = Bet(league, g.title, g.starts, "winner", c.ticker, "yes", c.statement, c.yes_ask, p.fee, p.fair,
            f"Sportsbooks ({len(c.books)} books)", list(c.books), True, list(p.notes), p.strength,
            p.contracts, p.stake, c.pinnacle)
    return b


# ---------------------------------------------------------------- the sportsbooks' main spread / total


@dataclass
class MainLines:
    spread: float | None = None  # home team's line, e.g. -3.5
    p_home_cover: float | None = None
    total: float | None = None
    p_over: float | None = None
    books: list[str] = field(default_factory=list)


def _mode(values: list[float]) -> float | None:
    return statistics.mode(values) if values else None


def main_lines(oe: dict) -> MainLines:
    home, away = oe.get("home_team", ""), oe.get("away_team", "")
    spreads: list[tuple[float, float]] = []
    totals: list[tuple[float, float]] = []
    names = set()
    for bk in oe.get("bookmakers") or []:
        for m in bk.get("markets") or []:
            outs = m.get("outcomes") or []
            try:
                if m.get("key") == "spreads":
                    h = next(o for o in outs if o.get("name") == home)
                    a = next(o for o in outs if o.get("name") == away)
                    if h.get("point") is None or float(h["point"]) != -float(a.get("point", 0)):
                        continue
                    p_h, _ = devig([float(h["price"]), float(a["price"])])
                    spreads.append((float(h["point"]), p_h))
                elif m.get("key") == "totals":
                    o = next(x for x in outs if (x.get("name") or "").lower() == "over")
                    u = next(x for x in outs if (x.get("name") or "").lower() == "under")
                    if o.get("point") is None or o.get("point") != u.get("point"):
                        continue
                    p_o, _ = devig([float(o["price"]), float(u["price"])])
                    totals.append((float(o["point"]), p_o))
                else:
                    continue
            except (StopIteration, ValueError, TypeError, KeyError):
                continue
            names.add(bk.get("title") or bk.get("key") or "?")
    out = MainLines(books=sorted(names))
    if spreads:
        out.spread = _mode([s for s, _ in spreads])
        out.p_home_cover = statistics.median([p for s, p in spreads if s == out.spread])
    if totals:
        out.total = _mode([t for t, _ in totals])
        out.p_over = statistics.median([p for t, p in totals if t == out.total])
    return out


def model_for(league: str, sport: str, oe: dict) -> tuple[SoccerModel | PointsModel | None, MainLines]:
    soccer = sport == "soccer"
    views = book_views(oe, three_way=soccer)
    lines = main_lines(oe)
    if soccer:
        if not all(k in views for k in ("home", "draw", "away")):
            return None, lines
        return fit_soccer(views["home"].fair, views["draw"].fair, views["away"].fair, lines.total, lines.p_over), lines
    p_home = views["home"].fair if "home" in views else None
    return fit_points(league, p_home, lines.spread, lines.p_home_cover, lines.total, lines.p_over), lines


# ---------------------------------------------------------------- reading Kalshi's line markets

_SPREAD = re.compile(r"^(?P<team>.+?)\s+wins?\s+by\s+(?P<how>more than|over|at least|\d)", re.I)
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def parse_line(m: dict, kind: str) -> dict | None:
    """{"team", "line"} for spreads, {"line"} for totals, {} for both-teams-to-score; None if unreadable."""
    text = (m.get("yes_sub_title") or m.get("title") or "").strip()
    strike = m.get("floor_strike")
    if kind == "btts":
        return {} if re.search(r"both teams", f"{text} {m.get('title') or ''}", re.I) or not text else None
    if kind == "spread":
        mt = _SPREAD.search(text)
        if not mt:
            return None
        rest = text[mt.start("how"):]
        num = float(strike) if strike not in (None, "") else (float(n.group(1)) if (n := _NUM.search(rest)) else None)
        if num is None:
            return None
        if "at least" in rest.lower() and float(num).is_integer():
            num -= 0.5  # "at least 3" = more than 2.5
        return {"team": mt.group("team").strip(), "line": num}
    if kind == "total":
        if re.search(r"\bunder\b", text, re.I):
            return None
        num = float(strike) if strike not in (None, "") else (float(n.group(1)) if (n := _NUM.search(text)) else None)
        return {"line": num} if num is not None else None
    return None


def _goals(sport: str) -> str:
    return "goals" if sport == "soccer" else "points"


def _plus(line: float) -> str:
    """2.5 -> "3+", 3 -> "more than 3"."""
    return f"{int(line + 0.5)}+" if (line * 2) % 2 == 1 else f"more than {line:g}"


def price_markets(markets: list[dict], kind: str, league: str, sport: str, oe: dict, model, lines: MainLines,
                  fee_rate: float = 0.07, fee_contracts: int = 10, code_sides: dict[str, str] | None = None) -> list[Bet]:
    """Both sides of every readable line market, priced by the model.

    code_sides maps Kalshi's team codes to "home"/"away" (from the matched winner market: ...-SGE is
    Frankfurt); a spread ticker ends in the same code (...-SGE3), which beats matching names."""
    if model is None:
        return []
    home, away = oe.get("home_team", ""), oe.get("away_team", "")
    title = f"{away} at {home}" if sport != "soccer" else f"{home} vs {away}"
    from .picks import _parse  # ISO time reader

    starts = _parse(oe.get("commence_time"))
    unit = _goals(sport)
    out = []
    gaps: list[float] = []  # model minus Kalshi's mid, YES side, on every liquid line of this game
    for m in markets:
        if (m.get("status") or "active") not in ("active", "open"):
            continue
        info = parse_line(m, kind)
        if info is None:
            continue
        exact, p_yes = True, None
        if kind == "spread":
            team = info["team"]
            code = re.sub(r"\d+$", "", (m.get("ticker") or "").rsplit("-", 1)[-1])
            sides = [code_sides[code]] if code_sides and code in code_sides else \
                [s for s, n in (("home", home), ("away", away)) if name_matches(team, n) or name_matches(n, team)]
            if len(sides) != 1:
                continue
            side, line = sides[0], info["line"]
            p_yes = model.wins_by_more_than(side, line)
            if isinstance(model, SoccerModel):
                fav = model.home_win() >= model.away_win() if side == "home" else model.away_win() > model.home_win()
                p_yes = calibrated(f"{'fav' if fav else 'dog'} by {line:g}", p_yes)
            yes_txt = f"{team} wins by {_plus(line)} {unit}"
            no_txt = f"{team} doesn't win by {_plus(line)} {unit}"
            if sport != "soccer" and lines.spread is not None:
                book = -lines.spread if side == "home" else lines.spread  # e.g. home -3.5 -> home wins by 3.5
                exact = abs(line - book) <= 0.5
                if league in NEAR_ONLY and abs(line - book) > NEAR_ONLY[league][0]:
                    continue
            else:
                exact = False
                if league in NEAR_ONLY:
                    continue
            far = sport != "soccer" and lines.spread is not None and abs(line - abs(lines.spread)) > STRETCH["points"]
        elif kind == "total":
            line = info["line"]
            p_yes = model.total_over(line)
            if isinstance(model, SoccerModel):
                p_yes = calibrated(f"over {line:g}", p_yes)
            yes_txt, no_txt = f"Over {line:g} {unit}", f"Under {line:g} {unit}"
            exact = lines.total is not None and abs(line - lines.total) < 0.01
            if league in NEAR_ONLY and (lines.total is None or abs(line - lines.total) > NEAR_ONLY[league][1]):
                continue
            far = lines.total is not None and abs(line - lines.total) > STRETCH["soccer" if sport == "soccer" else "points"]
        else:  # btts
            if not isinstance(model, SoccerModel):
                continue
            p_yes = calibrated("both score", model.both_score())
            yes_txt, no_txt = "Both teams score", "Not both teams score (at least one shut out)"
            exact, far = False, False
        if p_yes is None:
            continue
        bid, ask_y = price_field(m, "yes_bid"), price_field(m, "yes_ask")
        if bid is not None and ask_y is not None and 0 < bid <= ask_y < 1 and ask_y - bid <= LIQUID_SPREAD:
            gaps.append(p_yes - float((bid + ask_y) / 2))
        for side, ask, fair, text in (("yes", price_field(m, "yes_ask"), p_yes, yes_txt),
                                      ("no", price_field(m, "no_ask"), 1 - p_yes, no_txt)):
            if ask is None or not Decimal("0.01") < ask < Decimal("0.99"):
                continue
            fee = Decimal(str(fee_per_contract(float(ask), fee_contracts, fee_rate))).quantize(Decimal("0.0001"))
            src = "Sportsbooks' own line" if exact else "Model from the sportsbooks' lines"
            bet = Bet(league, title, starts, kind, m.get("ticker", ""), side, text, ask, fee, fair, src,
                      list(lines.books), exact)
            if far:
                bet.notes.append(f"This line is far from the sportsbooks' own ({_book_line_text(kind, lines)}), "
                                 "so the model's price is rougher.")
            out.append(bet)
    if len(gaps) >= 2:
        level = statistics.median(gaps)
        for b in out:
            b.level_gap = level if b.side == "yes" else -level
    return out


def winner_no_bets(g, league: str, sport: str, fee_rate: float = 0.07, fee_contracts: int = 10) -> list[Bet]:
    """NO on a winner market, priced from the sportsbooks: "Bayern doesn't win", "Not a draw"."""
    from .teams import is_draw

    out = []
    names = [c.name for c in g.choices if not is_draw(c.name)]
    for c in g.choices:
        if c.book is None or c.no_ask is None or not Decimal("0.01") < c.no_ask < Decimal("0.99") or len(c.books) < 2:
            continue
        if is_draw(c.name):
            text = "Not a draw (either team wins)"
        else:
            others = [n for n in names if n != c.name]
            text = f"{c.name} doesn't win" + (f" (draw or {others[0]})" if sport == "soccer" and others else "")
        fee = Decimal(str(fee_per_contract(float(c.no_ask), fee_contracts, fee_rate))).quantize(Decimal("0.0001"))
        pin = None if c.pinnacle is None else 1 - c.pinnacle
        out.append(Bet(league, g.title, g.starts, "winner", c.ticker, "no", text, c.no_ask, fee, 1 - c.book,
                       f"Sportsbooks ({len(c.books)} books)", list(c.books), True, [], "Good", pinnacle=pin))
    return out


def _book_line_text(kind: str, lines: MainLines) -> str:
    if kind == "total" and lines.total is not None:
        return f"{lines.total:g}"
    if lines.spread is not None:
        return f"{lines.spread:+g}"
    return "none"


def grade_bet(b: Bet, min_edge: float) -> str | None:
    """"pick" (clears the bar), "lean" (a smaller real edge worth a look) or None. Sets strength and notes.

    The bar: min_edge on the books' own line, MODEL_EDGE on model-priced lines, more for longshots, plus
    any game-wide disagreement with Kalshi. A lean must still be at least LEAN_EDGE above that
    disagreement and fees, and isn't a longshot."""
    need = min_edge if b.exact else max(min_edge, MODEL_EDGE)
    penalty = b.level_gap if b.level_gap > LEVEL_FLOOR else 0.0
    need += penalty
    longshot = b.ask < LONGSHOT_PRICE
    if longshot:
        need = max(need, LONGSHOT_EDGE)
    if b.edge < need:
        if longshot or b.edge - penalty < LEAN_EDGE:
            return None
        b.strength = "Lean"
        if not b.exact:
            b.notes.append("Priced by the bot's model from the sportsbooks' main lines.")
        if penalty:
            b.notes.append(f"Kalshi sits about {penalty * 100:.0f} points below the model on this game's other "
                           "lines, so the real edge may be smaller.")
        return "lean"
    sharp_ok = b.kind != "winner" or (b.pinnacle is not None and b.pinnacle - float(b.cost) >= 0.01)
    if b.kind == "winner" and b.pinnacle is not None and b.pinnacle < float(b.cost):
        b.notes.append("Pinnacle, the sharpest sportsbook, doesn't agree this is cheap.")
    if b.exact and b.edge >= 0.05 and len(b.books) >= 3 and not longshot and not b.notes and sharp_ok:
        b.strength = "Strong"
    else:
        b.strength = "Good" if b.exact else "Model"
    if not b.exact:
        b.notes.append("Priced by the bot's model from the sportsbooks' main lines (they don't post this exact line).")
    if penalty:
        b.notes.append(f"Across this game's other lines, Kalshi sits about {penalty * 100:.0f} points below the model, "
                       "so that much of the edge may be a different read of the game; it had to clear that too.")
    if len(b.books) < 3:
        b.notes.append(f"Only {len(b.books)} sportsbooks to build the price from.")
    if longshot:
        b.notes.append("Longshot: it needed an extra-big edge to make the list.")
    return "pick"


def judge_bet(b: Bet, min_edge: float) -> bool:
    """Is it a pick? (See grade_bet.)"""
    return grade_bet(b, min_edge) == "pick"


def spread_out(bets: list[Bet], per_game: int = 2, limit: int | None = None) -> list[Bet]:
    """Best first, at most `per_game` bets from any one game, so one match can't fill the page."""
    seen: dict[tuple[str, str], int] = {}
    out = []
    for b in sorted(bets, key=lambda b: -(b.edge - max(b.level_gap, 0.0))):
        key = (b.league, b.game)
        if seen.get(key, 0) >= per_game:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(b)
        if limit and len(out) >= limit:
            break
    return out


def has_sharp(books: list[str]) -> bool:
    return any(s in (b or "").lower() for b in books for s in SHARP_BOOKS)
