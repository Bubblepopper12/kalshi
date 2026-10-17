# Kalshi NFL history test (Oct 17, 2026)

908 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 2 | 1% | 50% | +48.9% |
| 10–20¢ | 43 | 15% | 5% | -10.9% |
| 20–30¢ | 91 | 25% | 27% | +1.2% |
| 30–40¢ | 141 | 35% | 43% | +6.4% |
| 40–50¢ | 167 | 44% | 47% | +0.7% |
| 50–60¢ | 148 | 55% | 49% | -8.2% |
| 60–70¢ | 153 | 64% | 59% | -5.9% |
| 70–80¢ | 108 | 74% | 70% | -5.1% |
| 80–90¢ | 47 | 84% | 85% | -0.2% |
| 90–100¢ | 8 | 90% | 100% | +9.0% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

722 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.624, sportsbooks 0.618.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 71 | 53 | -2.0% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 720 | 2.3 pts | 27 | 19 | +4.7% |
| 48 h | 720 | 2.0 pts | 17 | 10 | -6.5% |
| 24 h | 720 | 1.7 pts | 9 | 7 | +4.0% |
| 6 h | 720 | 1.4 pts | 6 | 3 | -19.6% |
| 1 h | 720 | 1.2 pts | 1 | 1 | +10.3% |
