# Kalshi La Liga history test (Oct 22, 2026)

1400 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 57 | 6% | 2% | -5.0% |
| 10–20¢ | 163 | 15% | 16% | -0.2% |
| 20–30¢ | 427 | 26% | 23% | -3.5% |
| 30–40¢ | 365 | 33% | 31% | -4.1% |
| 40–50¢ | 169 | 44% | 47% | +1.3% |
| 50–60¢ | 104 | 55% | 53% | -3.5% |
| 60–70¢ | 47 | 64% | 66% | +0.2% |
| 70–80¢ | 38 | 74% | 76% | +0.7% |
| 80–90¢ | 25 | 83% | 100% | +16.4% |
| 90–100¢ | 5 | 91% | 100% | +8.2% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1388 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.559, sportsbooks 0.558.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 72 | 27 | +0.7% |
| Kalshi 3+ points cheaper than the books | 3 | 1 | -2.2% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1347 | 1.8 pts | 23 | 12 | +6.4% |
| 48 h | 1361 | 1.6 pts | 19 | 11 | +8.3% |
| 24 h | 1373 | 1.4 pts | 11 | 6 | +5.6% |
| 6 h | 1385 | 1.1 pts | 3 | 2 | +3.1% |
| 1 h | 1388 | 0.9 pts | 3 | 1 | -2.2% |
