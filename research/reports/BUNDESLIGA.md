# Kalshi Bundesliga history test (Oct 28, 2026)

1113 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 35 | 7% | 6% | -1.5% |
| 10–20¢ | 135 | 15% | 12% | -4.5% |
| 20–30¢ | 428 | 25% | 24% | -2.4% |
| 30–40¢ | 187 | 34% | 32% | -3.9% |
| 40–50¢ | 118 | 44% | 47% | +0.9% |
| 50–60¢ | 102 | 54% | 54% | -1.7% |
| 60–70¢ | 53 | 64% | 72% | +6.0% |
| 70–80¢ | 31 | 73% | 77% | +2.8% |
| 80–90¢ | 17 | 83% | 76% | -7.8% |
| 90–100¢ | 7 | 91% | 71% | -20.5% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1041 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.562, sportsbooks 0.563.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 85 | 33 | -4.0% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -5.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -40.7% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1024 | 1.8 pts | 27 | 16 | +10.3% |
| 48 h | 1035 | 1.7 pts | 22 | 11 | +3.3% |
| 24 h | 1032 | 1.6 pts | 16 | 7 | -1.6% |
| 6 h | 1035 | 1.2 pts | 4 | 2 | +5.1% |
| 1 h | 1041 | 1.1 pts | 6 | 2 | -5.0% |
