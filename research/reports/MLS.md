# Kalshi MLS history test (Nov 27, 2026)

2088 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 8% | 0% | -8.6% |
| 10–20¢ | 210 | 16% | 18% | +0.8% |
| 20–30¢ | 891 | 25% | 25% | -1.2% |
| 30–40¢ | 334 | 35% | 33% | -3.6% |
| 40–50¢ | 292 | 44% | 42% | -3.6% |
| 50–60¢ | 198 | 54% | 52% | -4.4% |
| 60–70¢ | 116 | 64% | 63% | -2.6% |
| 70–80¢ | 41 | 73% | 63% | -11.3% |
| 80–90¢ | 2 | 85% | 100% | +14.1% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1851 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.595, sportsbooks 0.593.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 168 | 77 | +4.4% |
| Kalshi 3+ points cheaper than the books | 34 | 20 | +9.6% |
| Kalshi 5+ points cheaper than the books | 18 | 12 | +18.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.