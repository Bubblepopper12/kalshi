# Kalshi Ligue 1 history test (Oct 18, 2026)

1095 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 26 | 7% | 4% | -4.1% |
| 10–20¢ | 150 | 15% | 11% | -5.0% |
| 20–30¢ | 406 | 25% | 26% | -0.8% |
| 30–40¢ | 186 | 33% | 31% | -3.8% |
| 40–50¢ | 116 | 44% | 50% | +3.9% |
| 50–60¢ | 99 | 54% | 54% | -2.3% |
| 60–70¢ | 60 | 64% | 58% | -7.4% |
| 70–80¢ | 35 | 74% | 69% | -6.6% |
| 80–90¢ | 16 | 83% | 81% | -2.6% |
| 90–100¢ | 1 | 90% | 100% | +9.3% |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

975 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.573, sportsbooks 0.575.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 73 | 26 | -0.5% |
| Kalshi 3+ points cheaper than the books | 5 | 1 | -21.0% |
| Kalshi 5+ points cheaper than the books | 1 | 0 | -31.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.

## 3. Does Kalshi lag earlier in the week?

Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).
A big early gap that buying would have profited from means Kalshi lags the books.

| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |
| --- | --- | --- | --- | --- | --- |
| 72 h | 965 | 2.1 pts | 36 | 13 | -10.9% |
| 48 h | 974 | 1.9 pts | 35 | 14 | -5.6% |
| 24 h | 972 | 1.8 pts | 27 | 13 | -0.6% |
| 6 h | 975 | 1.2 pts | 5 | 3 | +14.8% |
| 1 h | 975 | 1.1 pts | 5 | 1 | -21.0% |
