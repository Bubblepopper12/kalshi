"""Fair prices for any line, built from the sportsbooks' main lines.

Kalshi lists many lines per game (wins by 1.5, 2.5, 3.5; over 2.5, 3.5, 4.5 goals...), while
sportsbooks mostly post one main line. These models are anchored to the books' no-vig prices and
then read off any other line:

Soccer: each team's goals ~ Poisson. The two scoring rates are fitted so the model reproduces the
books' win/draw/loss chances and, when available, their over/under line. Every other soccer market
(margins, totals, both teams to score) comes from the same grid of scores.

American football and basketball: final margin and total points ~ Normal, centred on the books'
spread / total (and moneyline), with the typical spread of real results around closing lines.
Accurate near the books' line, rougher far from it; callers flag lines far from the books' own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from statistics import NormalDist

_N = NormalDist()
MAX_GOALS = 10

# Standard deviation of results around the closing line (points): (margin, total).
SPREAD_SD = {"NFL": (13.0, 13.0), "CFB": (16.0, 16.0), "NBA": (12.0, 18.0)}  # NFL totals: 13.2 in nflverse 2015-25


def _pmf(lam: float) -> list[float]:
    out, p = [], math.exp(-lam)
    for k in range(MAX_GOALS + 1):
        out.append(p)
        p *= lam / (k + 1)
    return out


@dataclass
class SoccerModel:
    home_rate: float  # expected goals
    away_rate: float

    @cached_property
    def cells(self) -> list[tuple[int, int, float]]:
        """(home goals, away goals, chance) for every score up to MAX_GOALS each, normalised."""
        h, a = _pmf(self.home_rate), _pmf(self.away_rate)
        out = [(i, j, ph * pa) for i, ph in enumerate(h) for j, pa in enumerate(a)]
        total = sum(p for _, _, p in out)
        return [(i, j, p / total) for i, j, p in out]

    def prob(self, test) -> float:
        return sum(p for i, j, p in self.cells if test(i, j))

    def home_win(self) -> float:
        return self.prob(lambda h, a: h > a)

    def away_win(self) -> float:
        return self.prob(lambda h, a: a > h)

    def draw(self) -> float:
        return self.prob(lambda h, a: h == a)

    def wins_by_more_than(self, side: str, line: float) -> float:
        return self.prob((lambda h, a: h - a > line) if side == "home" else (lambda h, a: a - h > line))

    def total_over(self, line: float) -> float:
        return self.prob(lambda h, a: h + a > line)

    def total_under(self, line: float) -> float:
        return self.prob(lambda h, a: h + a < line)

    def book_over(self, line: float) -> float:
        """The over chance as a bookmaker prices `line`, Asian lines included (see asian_over)."""
        return asian_over(self.total_over, self.total_under, line)

    def both_score(self) -> float:
        return self.prob(lambda h, a: h > 0 and a > 0)

    def team_over(self, side: str, line: float) -> float:
        return self.prob((lambda h, a: h > line) if side == "home" else (lambda h, a: a > line))


def asian_over(over, under, line: float) -> float:
    """Fair over chance for an Asian total, as books quote it.

    x.5 is a plain over/under. A whole line (3.0) refunds the bet on exactly 3, so its no-margin price
    is P(>3) / (P(>3) + P(<3)). A quarter line (2.75) is half the stake on 2.5 and half on 3.0:
    (wins on both halves) / (wins + losses on both halves).
    """
    halves = [line] if (line * 2).is_integer() else [line - 0.25, line + 0.25]
    win = sum(over(x) for x in halves)
    lose = sum(under(x) for x in halves)
    return win / (win + lose) if win + lose > 0 else 0.5


def _bisect(f, lo: float, hi: float, target: float, steps: int = 30) -> float:
    """x in [lo, hi] with f(x) = target, for f increasing."""
    for _ in range(steps):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fit_soccer(p_home: float, p_draw: float, p_away: float,
               total_line: float | None = None, p_over: float | None = None) -> SoccerModel:
    """Scoring rates matching the books: who's favoured (home vs away), and how many goals
    (the over/under price when given, otherwise the draw chance, which falls as goals rise)."""
    share_target = p_home / (p_home + p_away)
    mu, share = 2.6, 0.5
    for _ in range(4):
        share = _bisect(lambda s: (lambda m: m.home_win() / (m.home_win() + m.away_win()))(
            SoccerModel(mu * s, mu * (1 - s))), 0.02, 0.98, share_target)
        if total_line is not None and p_over is not None:
            mu = _bisect(lambda x: SoccerModel(x * share, x * (1 - share)).book_over(total_line), 0.3, 7.0, p_over)
        else:
            mu = _bisect(lambda x: -SoccerModel(x * share, x * (1 - share)).draw(), 0.3, 7.0, -p_draw)
    return SoccerModel(mu * share, mu * (1 - share))


class MarginShape:
    """How results land around the closing spread, from real games (see football_margins.py).

    Each historical "margin minus spread" is spread evenly over one point, so the curve is smooth
    between whole numbers but keeps football's bunching at 3 and 7."""

    def __init__(self, counts: dict[float, int]):
        self.items = sorted(counts.items())
        self.n = sum(counts.values())

    def above(self, x: float) -> float:
        """P(result - centre > x)."""
        return sum(c * min(max(r + 0.5 - x, 0.0), 1.0) for r, c in self.items) / self.n


@dataclass
class PointsModel:
    """Final margin (home minus away) and total points. Margin: real NFL shape when given, else normal."""

    margin: float  # expected home margin (the market's centre)
    margin_sd: float
    total: float | None  # expected total points
    total_sd: float
    shape: MarginShape | None = None

    def _above(self, x: float) -> float:
        """P(home margin > x)."""
        if self.shape is not None:
            return self.shape.above(x - self.margin)
        return 1 - _N.cdf((x - self.margin) / self.margin_sd)

    def home_win(self) -> float:
        return self._above(0)

    def wins_by_more_than(self, side: str, line: float) -> float:
        if side == "home":
            return self._above(line)
        return 1 - self._above(-line)

    def total_over(self, line: float) -> float | None:
        if self.total is None:
            return None
        return 1 - _N.cdf((line - self.total) / self.total_sd)


def _clip(p: float) -> float:
    return min(max(p, 1e-4), 1 - 1e-4)


def _shape_for(league: str) -> MarginShape | None:
    if league == "NFL":
        from .football_margins import NFL_RESIDUALS

        global _NFL_SHAPE
        if _NFL_SHAPE is None:
            _NFL_SHAPE = MarginShape(NFL_RESIDUALS)
        return _NFL_SHAPE
    return None


_NFL_SHAPE: MarginShape | None = None


def fit_points(league: str, p_home_win: float | None, home_spread: float | None = None,
               p_home_cover: float | None = None, total_line: float | None = None,
               p_over: float | None = None) -> PointsModel | None:
    """home_spread is the books' line for the home team (-3.5 = home favoured by 3.5)."""
    msd, tsd = SPREAD_SD.get(league, (13.5, 13.0))
    shape = _shape_for(league)

    def centre_for(line: float, p: float) -> float:
        """The expected margin at which P(home margin > line) = p."""
        return _bisect(lambda mu: PointsModel(mu, msd, None, tsd, shape)._above(line), -60, 60, _clip(p))

    guesses = []
    if home_spread is not None and p_home_cover is not None:
        guesses += [centre_for(-home_spread, p_home_cover)] * 2  # the spread is the sharper number: counts double
    if p_home_win is not None:
        guesses.append(centre_for(0.0, p_home_win))
    if not guesses:
        return None
    total = None
    if total_line is not None and p_over is not None:
        total = total_line + tsd * _N.inv_cdf(_clip(p_over))
    return PointsModel(sum(guesses) / len(guesses), msd, total, tsd, shape)
