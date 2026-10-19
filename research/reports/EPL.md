# Kalshi Premier League history test (Oct 19, 2026)

1347 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 22 | 6% | 5% | -2.0% |
| 10–20¢ | 171 | 15% | 15% | -1.1% |
| 20–30¢ | 541 | 25% | 28% | +1.4% |
| 30–40¢ | 213 | 34% | 31% | -3.8% |
| 40–50¢ | 153 | 45% | 43% | -3.2% |
| 50–60¢ | 112 | 54% | 41% | -15.2% |
| 60–70¢ | 86 | 64% | 65% | -0.7% |
| 70–80¢ | 36 | 73% | 69% | -5.3% |
| 80–90¢ | 13 | 83% | 77% | -7.3% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1317 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.596, sportsbooks 0.596.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 69 | 23 | -5.2% |
| Kalshi 3+ points cheaper than the books | 0 | 0 | +0.0% |
| Kalshi 5+ points cheaper than the books | 0 | 0 | +0.0% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 1317 | 1.8 pts | 18 | 8 | +3.1% |
| 48 h | 1317 | 1.7 pts | 12 | 8 | +22.6% |
| 24 h | 1317 | 1.7 pts | 16 | 6 | -9.8% |
| 6 h | 1317 | 1.3 pts | 6 | 1 | -24.2% |
| 1 h | 1317 | 1.0 pts | 0 | 0 | +0.0% |
