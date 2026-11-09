# Kalshi Serie A history test (Nov 9, 2026)

1470 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 31 | 8% | 6% | -1.6% |
| 10–20¢ | 226 | 15% | 15% | -0.9% |
| 20–30¢ | 410 | 25% | 22% | -4.6% |
| 30–40¢ | 388 | 33% | 29% | -5.7% |
| 40–50¢ | 153 | 44% | 57% | +10.8% |
| 50–60¢ | 105 | 55% | 52% | -4.2% |
| 60–70¢ | 87 | 65% | 64% | -1.9% |
| 70–80¢ | 58 | 74% | 76% | +0.9% |
| 80–90¢ | 12 | 82% | 92% | +8.6% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1466 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.561, sportsbooks 0.561.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 91 | 38 | -0.4% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1437 | 1.9 pts | 32 | 16 | +7.2% |
| 48 h | 1450 | 1.7 pts | 30 | 14 | +2.9% |
| 24 h | 1459 | 1.6 pts | 26 | 13 | +3.6% |
| 6 h | 1460 | 1.1 pts | 6 | 2 | -6.8% |
| 1 h | 1466 | 1.0 pts | 2 | 0 | -30.4% |
