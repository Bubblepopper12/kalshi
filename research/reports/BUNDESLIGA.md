# Kalshi Bundesliga history test (Nov 7, 2026)

1155 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 35 | 7% | 6% | -1.5% |
| 10–20¢ | 144 | 15% | 12% | -4.5% |
| 20–30¢ | 441 | 25% | 24% | -2.0% |
| 30–40¢ | 195 | 34% | 31% | -4.8% |
| 40–50¢ | 123 | 44% | 46% | +0.6% |
| 50–60¢ | 104 | 54% | 54% | -1.8% |
| 60–70¢ | 55 | 64% | 73% | +6.9% |
| 70–80¢ | 34 | 73% | 76% | +1.7% |
| 80–90¢ | 17 | 83% | 76% | -7.8% |
| 90–100¢ | 7 | 91% | 71% | -20.5% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1068 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.565, sportsbooks 0.566.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 88 | 34 | -3.9% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -5.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -40.7% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1051 | 1.8 pts | 30 | 18 | +11.7% |
| 48 h | 1062 | 1.7 pts | 24 | 12 | +4.3% |
| 24 h | 1059 | 1.6 pts | 19 | 8 | -2.2% |
| 6 h | 1062 | 1.3 pts | 4 | 2 | +5.1% |
| 1 h | 1068 | 1.1 pts | 6 | 2 | -5.0% |
