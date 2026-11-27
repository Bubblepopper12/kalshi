# Kalshi NFL history test (Nov 27, 2026)

1082 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 5% | 25% | +19.7% |
| 10–20¢ | 50 | 15% | 6% | -9.7% |
| 20–30¢ | 113 | 25% | 27% | +1.3% |
| 30–40¢ | 170 | 35% | 40% | +3.1% |
| 40–50¢ | 190 | 44% | 45% | -1.2% |
| 50–60¢ | 171 | 55% | 50% | -6.4% |
| 60–70¢ | 189 | 64% | 62% | -3.0% |
| 70–80¢ | 124 | 74% | 71% | -4.6% |
| 80–90¢ | 61 | 84% | 84% | -1.3% |
| 90–100¢ | 10 | 91% | 100% | +8.6% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from nflverse (closing moneylines).

896 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.616, sportsbooks 0.610.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 87 | 68 | +0.7% |
| Kalshi 3+ points cheaper than the books | 3 | 2 | +36.0% |
| Kalshi 5+ points cheaper than the books | 2 | 1 | +48.9% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 894 | 2.3 pts | 34 | 25 | +10.8% |
| 48 h | 894 | 1.9 pts | 20 | 13 | +1.5% |
| 24 h | 894 | 1.6 pts | 11 | 9 | +10.6% |
| 6 h | 894 | 1.3 pts | 7 | 4 | -11.6% |
| 1 h | 894 | 1.2 pts | 1 | 1 | +10.3% |
