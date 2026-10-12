# Kalshi La Liga history test (Oct 12, 2026)

1367 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 56 | 6% | 2% | -4.9% |
| 10–20¢ | 157 | 15% | 16% | -0.2% |
| 20–30¢ | 419 | 26% | 23% | -3.5% |
| 30–40¢ | 357 | 33% | 31% | -4.0% |
| 40–50¢ | 163 | 44% | 47% | +1.2% |
| 50–60¢ | 103 | 55% | 52% | -3.9% |
| 60–70¢ | 45 | 64% | 67% | +1.0% |
| 70–80¢ | 38 | 74% | 76% | +0.7% |
| 80–90¢ | 24 | 83% | 100% | +16.3% |
| 90–100¢ | 5 | 91% | 100% | +8.2% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1328 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.561, sportsbooks 0.561.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 67 | 26 | +1.7% |
| Kalshi 3+ points cheaper than the books | 3 | 1 | -2.2% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1290 | 1.8 pts | 23 | 12 | +6.4% |
| 48 h | 1304 | 1.6 pts | 19 | 11 | +8.3% |
| 24 h | 1316 | 1.4 pts | 11 | 6 | +5.6% |
| 6 h | 1328 | 1.1 pts | 3 | 2 | +3.1% |
| 1 h | 1328 | 0.9 pts | 3 | 1 | -2.2% |
