# Kalshi Serie A history test (Nov 7, 2026)

1449 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 31 | 8% | 6% | -1.6% |
| 10–20¢ | 223 | 15% | 15% | -0.7% |
| 20–30¢ | 401 | 25% | 22% | -4.6% |
| 30–40¢ | 386 | 33% | 29% | -5.6% |
| 40–50¢ | 149 | 44% | 57% | +11.0% |
| 50–60¢ | 103 | 55% | 51% | -5.1% |
| 60–70¢ | 87 | 65% | 64% | -1.9% |
| 70–80¢ | 57 | 74% | 75% | +0.4% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1436 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.561, sportsbooks 0.562.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 90 | 38 | +0.1% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1407 | 1.9 pts | 30 | 15 | +7.5% |
| 48 h | 1420 | 1.7 pts | 29 | 14 | +4.5% |
| 24 h | 1429 | 1.6 pts | 23 | 12 | +5.8% |
| 6 h | 1430 | 1.1 pts | 5 | 2 | +0.3% |
| 1 h | 1436 | 1.0 pts | 2 | 0 | -30.4% |
