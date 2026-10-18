# Kalshi Bundesliga history test (Oct 18, 2026)

1080 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 35 | 7% | 6% | -1.5% |
| 10–20¢ | 127 | 15% | 12% | -4.5% |
| 20–30¢ | 417 | 25% | 24% | -2.5% |
| 30–40¢ | 184 | 34% | 32% | -4.0% |
| 40–50¢ | 114 | 44% | 46% | +0.8% |
| 50–60¢ | 100 | 54% | 55% | -0.5% |
| 60–70¢ | 49 | 64% | 69% | +3.8% |
| 70–80¢ | 30 | 73% | 80% | +5.4% |
| 80–90¢ | 17 | 83% | 76% | -7.8% |
| 90–100¢ | 7 | 91% | 71% | -20.5% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

987 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.560, sportsbooks 0.561.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 76 | 29 | -4.5% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -5.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -40.7% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 970 | 1.8 pts | 24 | 14 | +9.7% |
| 48 h | 981 | 1.7 pts | 21 | 10 | +1.1% |
| 24 h | 978 | 1.6 pts | 14 | 6 | -2.1% |
| 6 h | 981 | 1.2 pts | 4 | 2 | +5.1% |
| 1 h | 987 | 1.1 pts | 6 | 2 | -5.0% |
