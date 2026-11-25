# Kalshi Bundesliga history test (Nov 25, 2026)

1194 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 37 | 7% | 8% | +1.0% |
| 10–20¢ | 151 | 15% | 11% | -5.0% |
| 20–30¢ | 456 | 25% | 24% | -2.5% |
| 30–40¢ | 198 | 34% | 32% | -4.3% |
| 40–50¢ | 125 | 44% | 46% | +0.7% |
| 50–60¢ | 107 | 54% | 54% | -1.4% |
| 60–70¢ | 60 | 64% | 75% | +9.3% |
| 70–80¢ | 35 | 73% | 77% | +2.3% |
| 80–90¢ | 17 | 83% | 76% | -7.8% |
| 90–100¢ | 8 | 91% | 62% | -29.4% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1122 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.560, sportsbooks 0.561.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 96 | 38 | -3.2% |
| Kalshi 3+ points cheaper than the books | 7 | 2 | -6.8% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -40.7% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1105 | 1.8 pts | 32 | 20 | +13.1% |
| 48 h | 1116 | 1.8 pts | 25 | 13 | +6.0% |
| 24 h | 1113 | 1.7 pts | 20 | 9 | +0.2% |
| 6 h | 1116 | 1.2 pts | 5 | 3 | +13.0% |
| 1 h | 1122 | 1.1 pts | 7 | 2 | -6.8% |
