# Kalshi Ligue 1 history test (Nov 11, 2026)

1191 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 28 | 7% | 4% | -4.2% |
| 10–20¢ | 162 | 15% | 10% | -5.8% |
| 20–30¢ | 440 | 25% | 25% | -1.7% |
| 30–40¢ | 208 | 33% | 33% | -1.8% |
| 40–50¢ | 127 | 44% | 49% | +2.7% |
| 50–60¢ | 106 | 54% | 55% | -1.1% |
| 60–70¢ | 63 | 64% | 59% | -7.0% |
| 70–80¢ | 38 | 74% | 71% | -4.1% |
| 80–90¢ | 18 | 83% | 83% | -0.6% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1068 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.568, sportsbooks 0.569.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 81 | 32 | +1.6% |
| Kalshi 3+ points cheaper than the books | 6 | 2 | -9.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -31.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1058 | 2.1 pts | 42 | 17 | -7.4% |
| 48 h | 1067 | 1.9 pts | 38 | 16 | -3.7% |
| 24 h | 1065 | 1.8 pts | 28 | 14 | +0.9% |
| 6 h | 1068 | 1.2 pts | 7 | 5 | +20.0% |
| 1 h | 1068 | 1.2 pts | 6 | 2 | -9.0% |
