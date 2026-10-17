# Kalshi MLS history test (Oct 17, 2026)

1836 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 8% | 0% | -8.6% |
| 10–20¢ | 181 | 16% | 17% | -0.1% |
| 20–30¢ | 781 | 25% | 25% | -0.9% |
| 30–40¢ | 301 | 35% | 33% | -3.7% |
| 40–50¢ | 263 | 44% | 42% | -3.9% |
| 50–60¢ | 171 | 54% | 49% | -6.9% |
| 60–70¢ | 94 | 64% | 66% | +0.6% |
| 70–80¢ | 39 | 73% | 67% | -8.2% |
| 80–90¢ | 2 | 85% | 100% | +14.1% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1635 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.595, sportsbooks 0.593.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 137 | 64 | +5.6% |
| Kalshi 3+ points cheaper than the books | 32 | 18 | +7.5% |
| Kalshi 5+ points cheaper than the books | 16 | 10 | +15.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.