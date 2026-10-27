# Kalshi NFL history test (Oct 27, 2026)

962 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 2 | 1% | 50% | +48.9% |
| 10–20¢ | 44 | 15% | 7% | -8.7% |
| 20–30¢ | 97 | 25% | 28% | +1.7% |
| 30–40¢ | 148 | 35% | 43% | +5.7% |
| 40–50¢ | 178 | 44% | 46% | -0.4% |
| 50–60¢ | 159 | 55% | 50% | -7.1% |
| 60–70¢ | 164 | 64% | 60% | -5.0% |
| 70–80¢ | 113 | 74% | 71% | -4.8% |
| 80–90¢ | 49 | 84% | 82% | -3.6% |
| 90–100¢ | 8 | 90% | 100% | +9.0% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

776 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.629, sportsbooks 0.623.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 74 | 55 | -2.5% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 774 | 2.3 pts | 30 | 22 | +9.7% |
| 48 h | 774 | 2.0 pts | 18 | 11 | -3.4% |
| 24 h | 774 | 1.6 pts | 10 | 8 | +8.1% |
| 6 h | 774 | 1.3 pts | 6 | 3 | -19.6% |
| 1 h | 774 | 1.2 pts | 1 | 1 | +10.3% |
