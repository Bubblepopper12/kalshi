# Kalshi NFL history test (Nov 7, 2026)

992 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 2 | 1% | 50% | +48.9% |
| 10–20¢ | 46 | 15% | 7% | -9.0% |
| 20–30¢ | 101 | 25% | 28% | +1.6% |
| 30–40¢ | 154 | 35% | 42% | +4.7% |
| 40–50¢ | 180 | 44% | 46% | -0.4% |
| 50–60¢ | 163 | 55% | 50% | -7.1% |
| 60–70¢ | 169 | 64% | 61% | -4.4% |
| 70–80¢ | 117 | 74% | 71% | -4.6% |
| 80–90¢ | 52 | 84% | 83% | -2.5% |
| 90–100¢ | 8 | 90% | 100% | +9.0% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

806 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.625, sportsbooks 0.619.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 76 | 57 | -1.9% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 804 | 2.3 pts | 31 | 23 | +9.8% |
| 48 h | 804 | 1.9 pts | 18 | 11 | -3.4% |
| 24 h | 804 | 1.6 pts | 10 | 8 | +8.1% |
| 6 h | 804 | 1.3 pts | 6 | 3 | -19.6% |
| 1 h | 804 | 1.2 pts | 1 | 1 | +10.3% |
