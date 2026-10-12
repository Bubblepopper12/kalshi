# Kalshi Premier League history test (Oct 12, 2026)

1320 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 1143 | 0% | 33% | +32.8% |
| 10–20¢ | 22 | 15% | 18% | +2.0% |
| 20–30¢ | 77 | 26% | 31% | +4.2% |
| 30–40¢ | 25 | 34% | 24% | -11.8% |
| 40–50¢ | 23 | 45% | 43% | -3.5% |
| 50–60¢ | 14 | 54% | 36% | -20.4% |
| 60–70¢ | 9 | 64% | 67% | +1.4% |
| 70–80¢ | 4 | 72% | 75% | +1.6% |
| 80–90¢ | 3 | 82% | 67% | -16.7% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1287 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 1.434, sportsbooks 0.596.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 1146 | 383 | +32.8% |
| Kalshi 3+ points cheaper than the books | 1122 | 379 | +33.3% |
| Kalshi 5+ points cheaper than the books | 1122 | 379 | +33.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1287 | 29.3 pts | 1137 | 381 | +33.0% |
| 48 h | 1287 | 29.3 pts | 1137 | 381 | +33.0% |
| 24 h | 1287 | 29.3 pts | 1137 | 381 | +33.0% |
| 6 h | 1287 | 29.3 pts | 1136 | 380 | +33.0% |
| 1 h | 1287 | 29.3 pts | 1135 | 379 | +33.0% |
