# Kalshi Premier League history test (Nov 9, 2026)

1440 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 23 | 6% | 4% | -2.1% |
| 10–20¢ | 179 | 15% | 15% | -1.2% |
| 20–30¢ | 582 | 25% | 28% | +1.3% |
| 30–40¢ | 230 | 34% | 32% | -3.6% |
| 40–50¢ | 167 | 45% | 43% | -3.3% |
| 50–60¢ | 119 | 55% | 41% | -15.2% |
| 60–70¢ | 89 | 64% | 65% | -0.6% |
| 70–80¢ | 37 | 73% | 70% | -4.4% |
| 80–90¢ | 14 | 83% | 79% | -5.9% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1437 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.592, sportsbooks 0.592.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 79 | 29 | -2.5% |
| Kalshi 3+ points cheaper than the books | 0 | 0 | +0.0% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1437 | 1.9 pts | 22 | 10 | +6.2% |
| 48 h | 1437 | 1.8 pts | 16 | 11 | +26.4% |
| 24 h | 1437 | 1.7 pts | 20 | 9 | -0.3% |
| 6 h | 1437 | 1.3 pts | 7 | 2 | -16.3% |
| 1 h | 1437 | 1.0 pts | 0 | 0 | +0.0% |
