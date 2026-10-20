# Kalshi NFL history test (Oct 20, 2026)

934 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 2 | 1% | 50% | +48.9% |
| 10–20¢ | 44 | 15% | 7% | -8.7% |
| 20–30¢ | 95 | 25% | 27% | +1.1% |
| 30–40¢ | 143 | 35% | 43% | +6.5% |
| 40–50¢ | 171 | 44% | 46% | +0.2% |
| 50–60¢ | 155 | 55% | 49% | -7.7% |
| 60–70¢ | 156 | 64% | 60% | -5.8% |
| 70–80¢ | 112 | 74% | 71% | -5.0% |
| 80–90¢ | 48 | 84% | 83% | -2.0% |
| 90–100¢ | 8 | 90% | 100% | +9.0% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

748 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.628, sportsbooks 0.622.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 73 | 55 | -1.4% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 746 | 2.3 pts | 29 | 21 | +8.3% |
| 48 h | 746 | 2.0 pts | 17 | 10 | -6.5% |
| 24 h | 746 | 1.6 pts | 9 | 7 | +4.0% |
| 6 h | 746 | 1.4 pts | 6 | 3 | -19.6% |
| 1 h | 746 | 1.2 pts | 1 | 1 | +10.3% |
