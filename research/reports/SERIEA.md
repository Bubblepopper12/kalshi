# Kalshi Serie A history test (Nov 26, 2026)

1500 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 33 | 8% | 6% | -2.0% |
| 10–20¢ | 235 | 15% | 14% | -1.5% |
| 20–30¢ | 417 | 25% | 22% | -4.2% |
| 30–40¢ | 391 | 33% | 29% | -5.7% |
| 40–50¢ | 153 | 44% | 57% | +10.8% |
| 50–60¢ | 107 | 55% | 51% | -5.1% |
| 60–70¢ | 91 | 65% | 65% | -1.4% |
| 70–80¢ | 60 | 74% | 77% | +1.7% |
| 80–90¢ | 13 | 82% | 92% | +9.4% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1496 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.559, sportsbooks 0.559.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 95 | 38 | -1.1% |
| Kalshi 3+ points cheaper than the books | 2 | 0 | -30.4% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1467 | 1.9 pts | 33 | 16 | +6.6% |
| 48 h | 1480 | 1.8 pts | 31 | 14 | +2.4% |
| 24 h | 1489 | 1.6 pts | 27 | 13 | +3.1% |
| 6 h | 1490 | 1.1 pts | 6 | 2 | -6.8% |
| 1 h | 1496 | 1.0 pts | 2 | 0 | -30.4% |
