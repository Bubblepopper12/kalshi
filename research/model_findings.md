# Model research log

## NFL Elo vs. closing moneylines (Oct 12, 2026)

Data: nflverse `games.csv` (1999-2025 results; closing moneylines 2015-2025).
Model: `src/picks_engine/models/elo.py` (Gemini's Elo + margin of victory, season reversion,
neutral sites). Tuned on 2002-2014 (K=25, home field 65, revert 0.5), tested on 2015-2025.

| 3,017 test games | Elo | Closing line |
| --- | --- | --- |
| Picked the winner | 63.7% | 66.2% |
| Log loss (lower is better) | 0.638 | 0.612 |

- The closing line beat Elo in all 11 test seasons. Blending 10-30% Elo into the line made it worse.
- Betting at closing odds whenever Elo was 3/5/8+ points above the line: -5.2% / -5.5% / -3.0% per bet.
- Conclusion: Elo does not create picks. Picks use sportsbook consensus as the fair price and look
  for Kalshi prices that are out of line with it.

## Code from Gemini, reviewed

- Elo update: correct (standard formula). Used as the base of `models/elo.py`.
- Poisson match probabilities: correct; independent Poisson slightly under-predicts draws
  (Dixon-Coles fixes this). Needs per-team expected goals as input. Not used yet: soccer
  history (football-data.co.uk) is blocked from the build server.
- remove_vig (decimal odds, proportional): correct; `pricing/devig.py` already does this.
- add_rolling_features: **bug**. `groupby(...).shift(1).rolling(...)` rolls across all teams
  mixed together, leaking other teams' games into each team's average. Correct version:

```python
def add_rolling_features(df, group_col, roll_cols, N=10):
    df = df.sort_values("date").copy()
    for c in roll_cols:
        df[f"{c}_roll_{N}"] = (df.groupby(group_col)[c]
                               .transform(lambda s: s.shift(1).rolling(N, min_periods=N).mean()))
    return df
```

## Walk-forward logistic regression: Elo difference + rest days (Oct 12, 2026)

Gemini's `walk_forward_backtest` (train on all earlier seasons, test the next one), with the
comparison it was missing: the closing line's Brier score on the same games.

| Season | Model Brier | Market Brier |
| --- | --- | --- |
| 2015 | 0.2258 | 0.2287 |
| 2016 | 0.2168 | 0.2170 |
| 2017 | 0.2181 | 0.2031 |
| 2018 | 0.2213 | 0.2124 |
| 2019 | 0.2252 | 0.2141 |
| 2020 | 0.2161 | 0.2019 |
| 2021 | 0.2358 | 0.2177 |
| 2022 | 0.2215 | 0.2093 |
| 2023 | 0.2326 | 0.2186 |
| 2024 | 0.2128 | 0.2010 |
| 2025 | 0.2213 | 0.2109 |
| **Average** | **0.2225** | **0.2122** |

The market wins 10 of 11 seasons. Rest-day difference adds almost nothing (coefficient 0.023).

## Other snippets

- stats.nba.com player game logs: fine code, but the endpoint usually blocks cloud servers;
  the `nba_api` package wraps it. Works from a home computer.
- nfl_data_py play-by-play EPA: the best-known Elo improvement (QB quality). Needs nflverse
  release files, which this build server can't download.

## Gemini's Kalshi research, checked (Oct 12, 2026)

| Claim | Verdict |
| --- | --- |
| PillarLab "Kalshi Market Inefficiency Map" | Not found; no numbers given anyway |
| Reddit cross-platform "0.8¢ locked in" example | Arithmetic wrong (buy 50.2¢, sell 49.8¢ loses 0.4¢); needs Polymarket |
| Taker fee = round_up(0.07 × C × P × (1−P)) | Correct (matches `pricing/fees.py`) |
| "Maker orders are free on sports" | Wrong for NFL/NBA/NHL games: maker fee round_up(0.0175 × C × P × (1−P)) since July 1, 2025 |
| vcorp-dev/kalshi-price-data archive | Not found |

Real, useful findings from checking it:
- Favorite-longshot bias on Kalshi: a VoxEU/CEPR study of 300,000+ contracts found low-priced
  contracts win less often than their prices imply → built as the longshot guard.
- Maker fees are a quarter of taker fees → built as patient orders.
- Kalshi candlesticks endpoint (`/series/{series}/markets/{ticker}/candlesticks`, 1/60/1440-minute
  periods) and Dune's daily Kalshi trade tables → built as `picks history download/analyze`.

## Kalshi NFL history test (run Oct 12, 2026 on Logan's Mac)

154 finished NFL winner markets since Sep 1, 2026 (109,681 hourly prices), priced 1 hour before kickoff,
compared with nflverse closing moneylines (all 154 matched).

- Kalshi was as accurate as the sportsbooks' closing lines: log loss 0.645 vs 0.649.
- Kalshi 3+ points cheaper than the closing line: 0 of 154. Any amount cheaper: 8 bets, 5 won, -13.1%/bet.
- Longshot bias by price bucket: nothing clear in this small sample (10–30¢ won slightly more than priced;
  each bucket has only 5–29 markets).
- Conclusion: no edge on NFL moneylines in the last hour before kickoff. Next test: the same data at
  72/48/24/6 hours before kickoff (does Kalshi lag earlier in the week?), and thinner leagues.
