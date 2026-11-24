# Kalshi Premier League history test (Nov 24, 2026)

1470 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 23 | 6% | 4% | -2.1% |
| 10–20¢ | 184 | 15% | 16% | -0.6% |
| 20–30¢ | 595 | 25% | 28% | +1.2% |
| 30–40¢ | 233 | 34% | 32% | -3.6% |
| 40–50¢ | 169 | 45% | 43% | -3.2% |
| 50–60¢ | 122 | 55% | 42% | -14.5% |
| 60–70¢ | 92 | 64% | 64% | -1.6% |
| 70–80¢ | 38 | 73% | 68% | -6.2% |
| 80–90¢ | 14 | 83% | 79% | -5.9% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1467 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.594, sportsbooks 0.594.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 83 | 31 | -2.2% |
| Kalshi 3+ points cheaper than the books | 1 | 1 | +38.3% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1467 | 1.8 pts | 22 | 10 | +6.2% |
| 48 h | 1467 | 1.7 pts | 16 | 11 | +26.4% |
| 24 h | 1467 | 1.7 pts | 20 | 9 | -0.3% |
| 6 h | 1467 | 1.3 pts | 7 | 2 | -16.3% |
| 1 h | 1467 | 1.0 pts | 1 | 1 | +38.3% |
