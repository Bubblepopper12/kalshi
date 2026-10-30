# Kalshi Premier League history test (Oct 30, 2026)

1380 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 22 | 6% | 5% | -2.0% |
| 10–20¢ | 175 | 15% | 15% | -0.9% |
| 20–30¢ | 553 | 25% | 28% | +1.4% |
| 30–40¢ | 221 | 34% | 32% | -3.6% |
| 40–50¢ | 157 | 45% | 43% | -3.0% |
| 50–60¢ | 114 | 54% | 40% | -15.9% |
| 60–70¢ | 88 | 64% | 65% | -1.0% |
| 70–80¢ | 37 | 73% | 70% | -4.4% |
| 80–90¢ | 13 | 83% | 77% | -7.3% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1377 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.593, sportsbooks 0.593.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 76 | 28 | -2.4% |
| Kalshi 3+ points cheaper than the books | 0 | 0 | +0.0% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1377 | 1.8 pts | 21 | 10 | +7.6% |
| 48 h | 1377 | 1.7 pts | 14 | 10 | +26.7% |
| 24 h | 1377 | 1.7 pts | 18 | 8 | -3.0% |
| 6 h | 1377 | 1.3 pts | 7 | 2 | -16.3% |
| 1 h | 1377 | 1.0 pts | 0 | 0 | +0.0% |
