# Kalshi La Liga history test (Nov 4, 2026)

1460 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 61 | 6% | 2% | -5.2% |
| 10–20¢ | 174 | 15% | 16% | -0.7% |
| 20–30¢ | 444 | 26% | 24% | -3.3% |
| 30–40¢ | 374 | 33% | 30% | -4.2% |
| 40–50¢ | 176 | 44% | 48% | +1.7% |
| 50–60¢ | 106 | 55% | 53% | -3.5% |
| 60–70¢ | 52 | 64% | 65% | -0.3% |
| 70–80¢ | 41 | 74% | 76% | +0.0% |
| 80–90¢ | 27 | 83% | 100% | +16.2% |
| 90–100¢ | 5 | 91% | 100% | +8.2% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1448 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.557, sportsbooks 0.556.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 78 | 31 | +1.6% |
| Kalshi 3+ points cheaper than the books | 4 | 1 | -9.5% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1407 | 1.8 pts | 25 | 14 | +8.9% |
| 48 h | 1421 | 1.6 pts | 20 | 11 | +6.2% |
| 24 h | 1433 | 1.4 pts | 12 | 6 | +2.4% |
| 6 h | 1445 | 1.1 pts | 4 | 2 | -5.6% |
| 1 h | 1448 | 1.0 pts | 4 | 1 | -9.5% |
