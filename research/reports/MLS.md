# Kalshi MLS history test (Nov 6, 2026)

2013 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 8% | 0% | -8.6% |
| 10–20¢ | 203 | 16% | 18% | +0.4% |
| 20–30¢ | 855 | 25% | 25% | -0.7% |
| 30–40¢ | 324 | 35% | 32% | -4.1% |
| 40–50¢ | 286 | 44% | 42% | -3.7% |
| 50–60¢ | 190 | 54% | 50% | -6.0% |
| 60–70¢ | 109 | 64% | 64% | -1.4% |
| 70–80¢ | 40 | 73% | 65% | -9.8% |
| 80–90¢ | 2 | 85% | 100% | +14.1% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1785 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.596, sportsbooks 0.593.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 159 | 72 | +4.0% |
| Kalshi 3+ points cheaper than the books | 32 | 18 | +7.5% |
| Kalshi 5+ points cheaper than the books | 16 | 10 | +15.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.