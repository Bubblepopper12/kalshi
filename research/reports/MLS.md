# Kalshi MLS history test (Nov 11, 2026)

2058 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 8% | 0% | -8.6% |
| 10–20¢ | 207 | 16% | 18% | +0.6% |
| 20–30¢ | 877 | 25% | 25% | -1.1% |
| 30–40¢ | 330 | 35% | 32% | -4.1% |
| 40–50¢ | 289 | 44% | 43% | -3.2% |
| 50–60¢ | 196 | 54% | 51% | -5.0% |
| 60–70¢ | 112 | 64% | 64% | -1.3% |
| 70–80¢ | 41 | 73% | 63% | -11.3% |
| 80–90¢ | 2 | 85% | 100% | +14.1% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1824 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.594, sportsbooks 0.592.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 166 | 76 | +4.6% |
| Kalshi 3+ points cheaper than the books | 34 | 20 | +9.6% |
| Kalshi 5+ points cheaper than the books | 18 | 12 | +18.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.