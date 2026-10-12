"""NFL Elo ratings (FiveThirtyEight-style) and an honest backtest against closing moneylines.

Rating update (the version Gemini found, plus the standard improvements):
  expected = 1 / (1 + 10 ** ((away - (home + hfa)) / 400))   hfa = 0 at neutral sites
  change   = K * mov_mult * (result - expected)               result: 1 win, 0.5 tie, 0 loss
  mov_mult = ln(|margin| + 1) * 2.2 / (winner_elo_diff * 0.001 + 2.2)   bigger wins count more,
                                                                        but less for heavy favourites
Each new season, ratings move part of the way back to 1505 (`revert`).

Backtest result (Oct 2026, nflverse games 1999-2025, tuned on 2002-2014, tested on 2015-2025):
Elo log loss 0.638 vs closing market 0.612; it lost to the market in every season, blending made
the market worse, and betting Elo-vs-market disagreements returned about -5% per bet. So Elo is
NOT used to create picks; picks come from Kalshi vs. sportsbook prices.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EloParams:
    k: float = 25.0
    hfa: float = 65.0
    revert: float = 0.5
    start: float = 1505.0
    mov: bool = True


@dataclass
class Game:
    season: int
    home: str
    away: str
    home_score: float | None = None
    away_score: float | None = None
    neutral: bool = False
    home_moneyline: float | None = None
    away_moneyline: float | None = None


@dataclass
class EloModel:
    params: EloParams = field(default_factory=EloParams)
    ratings: dict[str, float] = field(default_factory=dict)
    season: int | None = None

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self.params.start)

    def new_season(self, season: int) -> None:
        if self.season is not None and season != self.season:
            p = self.params
            self.ratings = {t: p.start + (r - p.start) * (1 - p.revert) for t, r in self.ratings.items()}
        self.season = season

    def home_win_prob(self, home: str, away: str, neutral: bool = False) -> float:
        hfa = 0.0 if neutral else self.params.hfa
        return 1.0 / (1.0 + 10.0 ** ((self.rating(away) - (self.rating(home) + hfa)) / 400.0))

    def update(self, g: Game) -> float:
        """Predict, then learn from the result. Returns the pre-game home win probability."""
        self.new_season(g.season)
        p = self.home_win_prob(g.home, g.away, g.neutral)
        if g.home_score is None or g.away_score is None:
            return p
        margin = g.home_score - g.away_score
        result = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        mult = 1.0
        if self.params.mov and margin != 0:
            hfa = 0.0 if g.neutral else self.params.hfa
            diff = self.rating(g.home) + hfa - self.rating(g.away)
            winner_diff = diff if margin > 0 else -diff
            mult = math.log(abs(margin) + 1) * 2.2 / (winner_diff * 0.001 + 2.2)
        delta = self.params.k * mult * (result - p)
        self.ratings[g.home] = self.rating(g.home) + delta
        self.ratings[g.away] = self.rating(g.away) - delta
        return p


def _implied(odds: float) -> float:
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


@dataclass
class Backtest:
    games: int
    model_log_loss: float
    market_log_loss: float
    model_accuracy: float
    market_accuracy: float
    bets: int
    roi: float  # profit per 1-unit bet at the closing price, betting when model beats market by `edge`


def backtest(games: Iterable[Game], test_seasons: set[int], params: EloParams | None = None,
             edge: float = 0.05) -> Backtest:
    """Run Elo through every game in order; score only test seasons with closing moneylines."""
    model = EloModel(params or EloParams())
    ll_m = ll_k = acc_m = acc_k = 0.0
    n = bets = 0
    pnl = 0.0
    for g in games:
        p = model.update(g)
        if (g.season not in test_seasons or g.home_moneyline is None or g.away_moneyline is None
                or g.home_score is None or g.home_score == g.away_score):
            continue
        ph, pa = _implied(g.home_moneyline), _implied(g.away_moneyline)
        mkt = ph / (ph + pa)
        y = 1.0 if g.home_score > g.away_score else 0.0
        ll_m += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        ll_k += -(y * math.log(mkt) + (1 - y) * math.log(1 - mkt))
        acc_m += (p > 0.5) == (y == 1)
        acc_k += (mkt > 0.5) == (y == 1)
        n += 1
        for model_p, market_p, odds, won in ((p, mkt, g.home_moneyline, y == 1),
                                            (1 - p, 1 - mkt, g.away_moneyline, y == 0)):
            if model_p - market_p >= edge:
                bets += 1
                payout = odds / 100 if odds > 0 else 100 / -odds
                pnl += payout if won else -1.0
    n = max(n, 1)
    return Backtest(n, ll_m / n, ll_k / n, acc_m / n, acc_k / n, bets, pnl / max(bets, 1))


def games_from_nflverse(rows: Iterable[dict]) -> list[Game]:
    """Rows of nflverse's games.csv (github.com/nflverse/nfldata, data/games.csv), in order."""
    def num(v):
        try:
            return None if v in (None, "", "NA") else float(v)
        except ValueError:
            return None
    out = []
    for r in rows:
        out.append(Game(season=int(r["season"]), home=r["home_team"], away=r["away_team"],
                        home_score=num(r.get("home_score")), away_score=num(r.get("away_score")),
                        neutral=(r.get("location") == "Neutral"),
                        home_moneyline=num(r.get("home_moneyline")), away_moneyline=num(r.get("away_moneyline"))))
    return out
