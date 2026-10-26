# Kalshi Ligue 1 history test (Oct 26, 2026)

1134 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 26 | 7% | 4% | -4.1% |
| 10–20¢ | 152 | 15% | 11% | -5.1% |
| 20–30¢ | 425 | 25% | 26% | -1.0% |
| 30–40¢ | 192 | 33% | 32% | -2.7% |
| 40–50¢ | 122 | 44% | 48% | +2.3% |
| 50–60¢ | 103 | 54% | 54% | -1.4% |
| 60–70¢ | 62 | 64% | 58% | -7.7% |
| 70–80¢ | 35 | 74% | 69% | -6.6% |
| 80–90¢ | 16 | 83% | 81% | -2.6% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

999 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.572, sportsbooks 0.574.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 76 | 28 | +0.4% |
| Kalshi 3+ points cheaper than the books | 5 | 1 | -21.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -31.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 989 | 2.1 pts | 38 | 14 | -9.5% |
| 48 h | 998 | 2.0 pts | 36 | 14 | -6.1% |
| 24 h | 996 | 1.8 pts | 27 | 13 | -0.6% |
| 6 h | 999 | 1.2 pts | 5 | 3 | +14.8% |
| 1 h | 999 | 1.2 pts | 5 | 1 | -21.0% |
