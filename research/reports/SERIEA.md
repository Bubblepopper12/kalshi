# Kalshi Serie A history test (Oct 25, 2026)

1368 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 30 | 7% | 7% | -1.3% |
| 10–20¢ | 211 | 15% | 15% | -1.2% |
| 20–30¢ | 370 | 25% | 22% | -3.9% |
| 30–40¢ | 374 | 33% | 29% | -5.4% |
| 40–50¢ | 140 | 44% | 56% | +10.4% |
| 50–60¢ | 94 | 55% | 51% | -5.4% |
| 60–70¢ | 83 | 65% | 64% | -2.3% |
| 70–80¢ | 54 | 74% | 74% | -0.9% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1346 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.566, sportsbooks 0.566.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 78 | 35 | +1.3% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1317 | 1.9 pts | 26 | 12 | +5.1% |
| 48 h | 1330 | 1.7 pts | 27 | 13 | +5.6% |
| 24 h | 1339 | 1.6 pts | 21 | 11 | +7.4% |
| 6 h | 1340 | 1.1 pts | 3 | 1 | +8.4% |
| 1 h | 1346 | 1.0 pts | 2 | 0 | -30.4% |
