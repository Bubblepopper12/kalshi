# Kalshi NFL history test (Nov 22, 2026)

1050 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 2 | 1% | 50% | +48.9% |
| 10–20¢ | 48 | 15% | 6% | -9.4% |
| 20–30¢ | 109 | 25% | 26% | -0.4% |
| 30–40¢ | 167 | 35% | 40% | +3.2% |
| 40–50¢ | 185 | 44% | 45% | -0.5% |
| 50–60¢ | 168 | 55% | 49% | -7.3% |
| 60–70¢ | 184 | 64% | 62% | -2.9% |
| 70–80¢ | 121 | 74% | 72% | -3.7% |
| 80–90¢ | 58 | 84% | 84% | -0.5% |
| 90–100¢ | 8 | 90% | 100% | +9.0% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

864 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.615, sportsbooks 0.609.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 84 | 65 | +0.3% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 862 | 2.3 pts | 33 | 25 | +12.0% |
| 48 h | 862 | 1.9 pts | 20 | 13 | +1.5% |
| 24 h | 862 | 1.6 pts | 11 | 9 | +10.6% |
| 6 h | 862 | 1.3 pts | 7 | 4 | -11.6% |
| 1 h | 862 | 1.2 pts | 1 | 1 | +10.3% |
