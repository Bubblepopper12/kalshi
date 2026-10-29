# Kalshi Serie A history test (Oct 29, 2026)

1404 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 31 | 8% | 6% | -1.6% |
| 10–20¢ | 217 | 15% | 15% | -0.7% |
| 20–30¢ | 384 | 25% | 22% | -4.4% |
| 30–40¢ | 378 | 33% | 29% | -5.5% |
| 40–50¢ | 142 | 44% | 57% | +11.0% |
| 50–60¢ | 100 | 55% | 51% | -5.5% |
| 60–70¢ | 84 | 65% | 64% | -1.9% |
| 70–80¢ | 56 | 74% | 75% | +0.0% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1400 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.563, sportsbooks 0.563.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 86 | 37 | +0.7% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1371 | 1.9 pts | 28 | 14 | +8.3% |
| 48 h | 1384 | 1.7 pts | 28 | 14 | +7.0% |
| 24 h | 1393 | 1.6 pts | 22 | 12 | +9.0% |
| 6 h | 1394 | 1.1 pts | 4 | 2 | +16.8% |
| 1 h | 1400 | 1.0 pts | 2 | 0 | -30.4% |
