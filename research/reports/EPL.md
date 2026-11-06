# Kalshi Premier League history test (Nov 6, 2026)

1410 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 22 | 6% | 5% | -2.0% |
| 10–20¢ | 176 | 15% | 15% | -1.0% |
| 20–30¢ | 568 | 25% | 28% | +1.3% |
| 30–40¢ | 227 | 34% | 32% | -3.6% |
| 40–50¢ | 163 | 45% | 44% | -2.8% |
| 50–60¢ | 116 | 55% | 41% | -15.8% |
| 60–70¢ | 88 | 64% | 65% | -1.0% |
| 70–80¢ | 37 | 73% | 70% | -4.4% |
| 80–90¢ | 13 | 83% | 77% | -7.3% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1407 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.593, sportsbooks 0.593.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 77 | 28 | -2.9% |
| Kalshi 3+ points cheaper than the books | 0 | 0 | +0.0% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1407 | 1.9 pts | 22 | 10 | +6.2% |
| 48 h | 1407 | 1.7 pts | 15 | 10 | +23.3% |
| 24 h | 1407 | 1.7 pts | 19 | 8 | -4.1% |
| 6 h | 1407 | 1.3 pts | 7 | 2 | -16.3% |
| 1 h | 1407 | 1.0 pts | 0 | 0 | +0.0% |
