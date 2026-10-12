# Kalshi NFL history test (Oct 12, 2026)

904 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 656 | 1% | 50% | +49.4% |
| 10–20¢ | 7 | 15% | 14% | -2.1% |
| 20–30¢ | 20 | 25% | 30% | +3.6% |
| 30–40¢ | 38 | 36% | 42% | +4.8% |
| 40–50¢ | 56 | 44% | 50% | +4.2% |
| 50–60¢ | 45 | 55% | 42% | -14.5% |
| 60–70¢ | 49 | 63% | 61% | -3.5% |
| 70–80¢ | 25 | 74% | 72% | -3.6% |
| 80–90¢ | 7 | 84% | 71% | -13.8% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

718 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 1.951, sportsbooks 0.616.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 572 | 287 | +48.5% |
| Kalshi 3+ points cheaper than the books | 559 | 282 | +49.8% |
| Kalshi 5+ points cheaper than the books | 559 | 282 | +49.8% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 716 | 39.2 pts | 565 | 284 | +49.4% |
| 48 h | 716 | 39.2 pts | 562 | 281 | +49.4% |
| 24 h | 716 | 39.1 pts | 562 | 281 | +49.4% |
| 6 h | 716 | 39.1 pts | 562 | 281 | +49.4% |
| 1 h | 716 | 39.1 pts | 562 | 281 | +49.4% |
