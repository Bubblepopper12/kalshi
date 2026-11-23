# Kalshi La Liga history test (Nov 23, 2026)

1520 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 64 | 6% | 2% | -5.3% |
| 10–20¢ | 180 | 15% | 16% | -0.5% |
| 20–30¢ | 467 | 26% | 24% | -3.3% |
| 30–40¢ | 383 | 33% | 31% | -3.9% |
| 40–50¢ | 182 | 44% | 47% | +0.7% |
| 50–60¢ | 113 | 54% | 53% | -3.1% |
| 60–70¢ | 55 | 64% | 65% | -0.3% |
| 70–80¢ | 41 | 74% | 76% | +0.0% |
| 80–90¢ | 30 | 83% | 100% | +16.1% |
| 90–100¢ | 5 | 91% | 100% | +8.2% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1505 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.556, sportsbooks 0.555.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 84 | 33 | +1.4% |
| Kalshi 3+ points cheaper than the books | 4 | 1 | -9.5% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1464 | 1.8 pts | 26 | 15 | +10.5% |
| 48 h | 1478 | 1.6 pts | 21 | 12 | +8.3% |
| 24 h | 1490 | 1.4 pts | 13 | 7 | +6.0% |
| 6 h | 1502 | 1.2 pts | 4 | 2 | -5.6% |
| 1 h | 1505 | 1.0 pts | 4 | 1 | -9.5% |
