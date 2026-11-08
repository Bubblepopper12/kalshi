# Kalshi Ligue 1 history test (Nov 8, 2026)

1176 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 28 | 7% | 4% | -4.2% |
| 10–20¢ | 160 | 15% | 11% | -5.6% |
| 20–30¢ | 436 | 25% | 25% | -1.7% |
| 30–40¢ | 202 | 33% | 33% | -2.3% |
| 40–50¢ | 125 | 44% | 49% | +2.7% |
| 50–60¢ | 106 | 54% | 56% | -0.1% |
| 60–70¢ | 62 | 64% | 58% | -7.7% |
| 70–80¢ | 38 | 74% | 71% | -4.1% |
| 80–90¢ | 18 | 83% | 83% | -0.6% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1044 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.570, sportsbooks 0.571.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 78 | 30 | +1.6% |
| Kalshi 3+ points cheaper than the books | 5 | 1 | -21.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -31.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1034 | 2.1 pts | 40 | 16 | -7.4% |
| 48 h | 1043 | 1.9 pts | 37 | 15 | -5.0% |
| 24 h | 1041 | 1.8 pts | 27 | 13 | -0.6% |
| 6 h | 1044 | 1.2 pts | 5 | 3 | +14.8% |
| 1 h | 1044 | 1.1 pts | 5 | 1 | -21.0% |
