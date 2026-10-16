# Kalshi Serie A history test (Oct 16, 2026)

1320 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 30 | 7% | 7% | -1.3% |
| 10–20¢ | 203 | 15% | 15% | -1.1% |
| 20–30¢ | 355 | 25% | 23% | -3.5% |
| 30–40¢ | 363 | 33% | 29% | -5.1% |
| 40–50¢ | 135 | 44% | 55% | +8.7% |
| 50–60¢ | 91 | 55% | 52% | -4.8% |
| 60–70¢ | 78 | 65% | 63% | -3.4% |
| 70–80¢ | 53 | 74% | 74% | -1.4% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1316 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.566, sportsbooks 0.566.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 73 | 32 | -1.0% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1287 | 1.9 pts | 25 | 12 | +6.1% |
| 48 h | 1300 | 1.7 pts | 27 | 13 | +5.6% |
| 24 h | 1309 | 1.6 pts | 21 | 11 | +7.4% |
| 6 h | 1310 | 1.1 pts | 3 | 1 | +8.4% |
| 1 h | 1316 | 1.0 pts | 2 | 0 | -30.4% |
