# Kalshi MLS history test (Oct 13, 2026)

1791 finished winner markets, priced before each game.

## 1. Are cheap contracts overpriced? (longshot bias)

Buying at the pre-game ask price, including Kalshi's fee:

| Price | Markets | Average price | Actually won | Return per bet |
| --- | --- | --- | --- | --- |
| 0–10¢ | 3 | 8% | 0% | -8.5% |
| 10–20¢ | 176 | 16% | 18% | +0.4% |
| 20–30¢ | 763 | 25% | 25% | -1.0% |
| 30–40¢ | 295 | 35% | 33% | -3.7% |
| 40–50¢ | 253 | 44% | 42% | -3.8% |
| 50–60¢ | 169 | 54% | 50% | -6.3% |
| 60–70¢ | 92 | 64% | 65% | -0.1% |
| 70–80¢ | 39 | 73% | 67% | -8.2% |
| 80–90¢ | 1 | 89% | 100% | +10.3% |
| 90–100¢ | 0 | | | |

If cheap buckets win less often than their price, longshots are overpriced.

## 2. Buying when Kalshi was cheaper than the sportsbooks

Closing lines from football-data.co.uk (Pinnacle closing odds).

1596 Kalshi prices matched with closing sportsbook lines.

Prediction error (log loss, lower is better): Kalshi 0.596, sportsbooks 0.594.

| Rule | Bets | Won | Return per bet |
| --- | --- | --- | --- |
| Kalshi any points cheaper than the books | 131 | 59 | +4.5% |
| Kalshi 3+ points cheaper than the books | 28 | 15 | +5.4% |
| Kalshi 5+ points cheaper than the books | 13 | 8 | +13.5% |

Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof.