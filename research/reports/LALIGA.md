# Kalshi La Liga history test (Oct 30, 2026)

1430 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 58 | 6% | 2% | -5.1% |
| 10–20¢ | 168 | 15% | 15% | -0.7% |
| 20–30¢ | 439 | 26% | 24% | -3.3% |
| 30–40¢ | 367 | 33% | 31% | -4.2% |
| 40–50¢ | 172 | 44% | 48% | +1.7% |
| 50–60¢ | 106 | 55% | 53% | -3.5% |
| 60–70¢ | 51 | 64% | 65% | -0.9% |
| 70–80¢ | 39 | 74% | 77% | +1.3% |
| 80–90¢ | 25 | 83% | 100% | +16.4% |
| 90–100¢ | 5 | 91% | 100% | +8.2% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1418 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.559, sportsbooks 0.558.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 75 | 29 | +1.6% |
| Kalshi 3+ points cheaper than the books | 4 | 1 | -9.5% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1377 | 1.8 pts | 24 | 13 | +7.7% |
| 48 h | 1391 | 1.6 pts | 20 | 11 | +6.2% |
| 24 h | 1403 | 1.4 pts | 12 | 6 | +2.4% |
| 6 h | 1415 | 1.1 pts | 4 | 2 | -5.6% |
| 1 h | 1418 | 1.0 pts | 4 | 1 | -9.5% |
