# Kalshi Bundesliga history test (Nov 10, 2026)

1167 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 35 | 7% | 6% | -1.5% |
| 10–20¢ | 146 | 15% | 12% | -4.7% |
| 20–30¢ | 447 | 25% | 24% | -2.3% |
| 30–40¢ | 195 | 34% | 31% | -4.8% |
| 40–50¢ | 123 | 44% | 46% | +0.6% |
| 50–60¢ | 106 | 54% | 55% | -0.9% |
| 60–70¢ | 57 | 64% | 74% | +7.9% |
| 70–80¢ | 34 | 73% | 76% | +1.7% |
| 80–90¢ | 17 | 83% | 76% | -7.8% |
| 90–100¢ | 7 | 91% | 71% | -20.5% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1095 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.560, sportsbooks 0.560.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 92 | 36 | -3.5% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -5.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -40.7% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1078 | 1.8 pts | 32 | 20 | +13.1% |
| 48 h | 1089 | 1.8 pts | 25 | 13 | +6.0% |
| 24 h | 1086 | 1.7 pts | 20 | 9 | +0.2% |
| 6 h | 1089 | 1.2 pts | 5 | 3 | +13.0% |
| 1 h | 1095 | 1.1 pts | 6 | 2 | -5.0% |
