# Kalshi Premier League history test (Oct 12, 2026)

1320 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 21 | 6% | 5% | -1.6% |
| 10–20¢ | 167 | 15% | 16% | -0.7% |
| 20–30¢ | 532 | 25% | 28% | +1.7% |
| 30–40¢ | 207 | 34% | 31% | -3.8% |
| 40–50¢ | 150 | 45% | 43% | -3.7% |
| 50–60¢ | 112 | 54% | 41% | -15.2% |
| 60–70¢ | 83 | 64% | 64% | -2.0% |
| 70–80¢ | 35 | 73% | 69% | -6.0% |
| 80–90¢ | 13 | 83% | 77% | -7.3% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1287 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.596, sportsbooks 0.596.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 66 | 23 | -3.6% |
| Kalshi 3+ points cheaper than the books | 0 | 0 | +0.0% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1287 | 1.8 pts | 17 | 7 | -0.2% |
| 48 h | 1287 | 1.7 pts | 12 | 8 | +22.6% |
| 24 h | 1287 | 1.7 pts | 15 | 6 | -7.4% |
| 6 h | 1287 | 1.3 pts | 5 | 1 | -19.9% |
| 1 h | 1287 | 1.0 pts | 0 | 0 | +0.0% |
