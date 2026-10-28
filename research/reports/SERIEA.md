# Kalshi Serie A history test (Oct 28, 2026)

1389 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 31 | 8% | 6% | -1.6% |
| 10–20¢ | 213 | 15% | 15% | -1.3% |
| 20–30¢ | 380 | 25% | 22% | -4.2% |
| 30–40¢ | 375 | 33% | 29% | -5.5% |
| 40–50¢ | 142 | 44% | 57% | +11.0% |
| 50–60¢ | 97 | 55% | 52% | -4.9% |
| 60–70¢ | 84 | 65% | 64% | -1.9% |
| 70–80¢ | 55 | 74% | 75% | -0.4% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1376 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.564, sportsbooks 0.564.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 81 | 36 | +1.2% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1347 | 1.9 pts | 26 | 12 | +5.1% |
| 48 h | 1360 | 1.7 pts | 27 | 13 | +5.6% |
| 24 h | 1369 | 1.6 pts | 21 | 11 | +7.4% |
| 6 h | 1370 | 1.1 pts | 3 | 1 | +8.4% |
| 1 h | 1376 | 1.0 pts | 2 | 0 | -30.4% |
