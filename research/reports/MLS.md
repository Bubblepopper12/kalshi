# Kalshi MLS history test (Nov 1, 2026)

1995 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 4 | 8% | 0% | -8.6% |
| 10–20¢ | 201 | 16% | 18% | +0.6% |
| 20–30¢ | 847 | 25% | 26% | -0.6% |
| 30–40¢ | 322 | 35% | 32% | -3.9% |
| 40–50¢ | 284 | 44% | 42% | -4.1% |
| 50–60¢ | 188 | 54% | 49% | -6.5% |
| 60–70¢ | 107 | 64% | 64% | -1.1% |
| 70–80¢ | 40 | 73% | 65% | -9.8% |
| 80–90¢ | 2 | 85% | 100% | +14.1% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1746 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.597, sportsbooks 0.595.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 153 | 69 | +3.7% |
| Kalshi 3+ points cheaper than the books | 32 | 18 | +7.5% |
| Kalshi 5+ points cheaper than the books | 16 | 10 | +15.3% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.