# Kalshi Ligue 1 history test (Nov 27, 2026)

1218 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 28 | 7% | 4% | -4.2% |
| 10–20¢ | 170 | 15% | 11% | -5.1% |
| 20–30¢ | 446 | 25% | 25% | -1.9% |
| 30–40¢ | 212 | 33% | 34% | -1.0% |
| 40–50¢ | 132 | 44% | 48% | +1.7% |
| 50–60¢ | 106 | 54% | 55% | -1.1% |
| 60–70¢ | 65 | 64% | 58% | -7.4% |
| 70–80¢ | 40 | 74% | 70% | -5.1% |
| 80–90¢ | 18 | 83% | 83% | -0.6% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1092 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.570, sportsbooks 0.571.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 82 | 33 | +2.6% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -9.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -31.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1082 | 2.1 pts | 43 | 17 | -7.8% |
| 48 h | 1091 | 1.9 pts | 38 | 16 | -3.7% |
| 24 h | 1089 | 1.8 pts | 28 | 14 | +0.9% |
| 6 h | 1092 | 1.2 pts | 7 | 5 | +20.0% |
| 1 h | 1092 | 1.1 pts | 6 | 2 | -9.0% |
