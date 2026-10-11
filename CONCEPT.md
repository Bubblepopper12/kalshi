# Kalshi Picks Engine — Concept

> **Update (trading added):** the original concept below never trades. The
> engine can now place orders, but only an order Logan approves one ticket at a
> time, within hard limits, starting on Kalshi's demo exchange. There is still no
> autonomous trading. See "How trading works" in the README.

## Overview

The Kalshi Picks Engine is a research tool, not a trading bot. It collects millions of rows of picks, results, odds and Kalshi prices, scores every tipster by their real track record, and gives Logan a ranked pick board. Logan reviews the board and places every trade himself. The engine never logs in, holds funds or submits orders.

Goals for the build:

- **Follow the proven sources, not the loud ones.** Store and grade every pick from every tipster, so the engine knows who actually wins over hundreds of picks.
- **Price against Kalshi.** A pick only reaches the board when the engine's estimated probability is meaningfully higher than what the Kalshi contract costs.
- **Cover every pick type Logan plays.** Moneylines, spreads, totals, player props and combos across college football, NFL, NBA and the major soccer leagues.
- **Show the why.** Each suggested pick lists the tipsters behind it, the model's number, the Kalshi price and the edge, so Logan can agree or pass in seconds.

Pipeline:
Tipster picks + Stats/results + Sportsbook odds + Kalshi prices → Warehouse → (Tipster scoring + Models) → Edge vs Kalshi → Pick board → Logan decides (Took it / Pass) → decisions logged back to Warehouse

## Leagues and pick types

The engine covers ten leagues and five pick types. It only suggests a pick when Kalshi actually lists a matching contract. Soccer depth varies a lot by league, so the engine reads live listings from the Kalshi API each day instead of hard-coding them.

| League | Season window | Kalshi coverage to expect | Priority |
| --- | --- | --- | --- |
| NFL | Sep–Feb | Games, spreads, totals, player props, combos, futures | 1 |
| College football / CFP | Aug–Jan | Games, spreads, totals, player props, playoff futures | 1 |
| NBA | Oct–Jun | Games, spreads, totals, player stats, combos, futures | 1 |
| Premier League | Aug–May | Match results, title and top-four futures, awards | 2 |
| Champions League | Sep–May | Match results, winner futures | 2 |
| MLS | Feb–Dec | Match results, MLS Cup and conference futures | 2 |
| La Liga | Aug–May | Match results, title futures | 3 |
| Serie A, Bundesliga, Ligue 1 | Aug–May | Unconfirmed; check listings before building scrapers | 3 |

Pick types:
- **Moneyline:** which side wins (soccer: home / draw / away).
- **Spread:** which side covers a point margin.
- **Total:** over or under on points or goals.
- **Player props:** yards, touchdowns, points, rebounds, assists, threes, shots and goalscorer markets where Kalshi lists them.
- **Combos:** two to four legs built from the picks above, checked for correlation before they reach the board.

Kalshi also lists Europa League and Liga MX. Both can be added later with little extra work once the soccer pipeline exists.

## Data sources

| Feed | Sources to start with | What it gives | Access |
| --- | --- | --- | --- |
| Tipster picks | Action Network expert pages, Covers, Pickswise, VegasInsider, RotoGrinders, selected X and Reddit accounts | Each pick with side, line, odds, units and timestamp | Mostly web pages. Check each site's terms; use feeds or manual import where scraping is barred |
| Stats and results | nflverse (NFL play-by-play), CollegeFootballData.com, nba_api, football-data.co.uk, StatsBomb open data | Final scores, box scores, player game logs, play-by-play | Free, open datasets and APIs |
| Sportsbook odds | The Odds API or OddsPapi | Opening and closing lines, player prop lines, line movement | Free tiers; historical data is paid |
| Kalshi markets | Kalshi Trade API (https://external-api.kalshi.com/trade-api/v2) | Every open sports market, yes/no prices, order book depth, settlement | Market data is public; no API key needed |

Build notes:
- **Timestamp every pick when it's captured.** A pick can only be graded if the engine knows the line and price when it was posted. Picks found after kickoff are stored but never scored.
- **Closing lines are the grading backbone.** Historical odds snapshots (The Odds API goes back to 2020) let the engine score old picks against the closing price, not just win/loss.
- **Kalshi needs no login for this tool.** Series, events, markets and order books are readable without an API key. Only trading needs one, and this engine never trades.

## Data model and scale

Most of the millions of rows come from odds snapshots, price snapshots and historical play-by-play, not from tipster picks. Row counts below are rough planning estimates.

| Table | One row is | Approx. rows after backfill | Grows by |
| --- | --- | --- | --- |
| odds_snapshots | One book's line on one market at one time | 10M+ | Every pull, all day |
| kalshi_price_snapshots | One Kalshi market's bid/ask at one time | 5M+ in year one | Every 5 min per open market |
| plays | One play or event (NFL, CFB, NBA, soccer) | 2–5M | Each game |
| player_game_stats | One player's line in one game | 1M+ | Each game |
| picks | One tipster pick with line, price, units, capture time | 100k–1M | Daily scraping |
| pick_grades | Result, units won, closing-line value for one pick | Same as picks | After each game settles |
| games, teams, players | Reference records with IDs mapped across sources | Tens of thousands | Season start |
| tipsters | One source with sport-by-sport scores | Hundreds to low thousands | New sources |
| kalshi_markets | One Kalshi contract and its rules | Tens of thousands | Daily listing sync |
| suggestions | One pick the engine put on the board | Thousands | Daily |
| logan_decisions | Logan's call on a suggestion: took it, passed, price paid | Thousands | Daily |

The hardest part is **ID matching**. Each tipster site, sportsbook and Kalshi ticker names the same player or game differently. Build a mapping table per entity (source name → internal ID) with a manual review queue for misses.

The logan_decisions table lets the engine compare Logan's own record against the board's and learn which suggestions he trusts.

## Tipster scoring

A tipster earns weight only by beating the closing line over a real sample. Each tipster is scored separately per sport and pick type (e.g. "NBA player props"). Win rate alone misleads: 60% on heavy favorites can lose money. Long-run records above 70% are usually fake. Strong handicappers sit around the mid-50s to 60% over big samples.

Inputs:
1. **Closing-line value (CLV):** how much better the posted price was than the final price before kickoff. This is the most reliable skill signal and needs far fewer picks than ROI.
2. **ROI per unit:** profit per unit risked, at the posted price.
3. **Sample size:** number of graded picks. Small samples are pulled hard toward zero.
4. **Recency:** older picks count less (half-life of about one season).

Formulas (starting points; tune by backtest):
- ROI_shrunk = (n / (n + k)) × ROI_observed, with k ≈ 200
- Trust = 0.6 × z(CLV) + 0.4 × z(ROI_shrunk), where z = standardized against all tipsters in that sport and pick type

Tiers:
- **Proven:** top 10% with 300+ graded picks
- **Promising:** positive score, under 300 picks
- **Neutral**
- **Fade:** reliably negative CLV over 300+ picks; their side counts as a small signal the other way

## Pick generation

A pick reaches the board only when three independent views agree it is underpriced on Kalshi: trusted tipsters, the engine's own model, and the sharp sportsbook market. Run each morning and again 90 minutes before each game.

1. **Tipster consensus.** For each market, sum the trust scores of tipsters on each side. Proven backing bumps the probability; Fade backing cuts it.
2. **Model probability.** One model per sport and pick type:
   - Game lines: Elo-style power ratings adjusted for injuries, rest, travel and home field.
   - Soccer: expected-goals models giving home/draw/away and over/under probabilities.
   - Player props: projections from recent game logs, minutes or snaps, usage, opponent defense and pace.
3. **Market probability.** Remove the vig from the sharpest sportsbook lines to get a fair probability.
4. **Blend.** Combine all three into one fair probability per side. Set the weights by backtesting.
5. **Edge against Kalshi.** Compare fair probability to the Kalshi ask plus its trading fee. A contract at 54¢ implies 54%; if the engine says 60%, the edge is about 6 points before fees.
6. **Filters.** Drop anything with under 3 points of edge, thin order books, or a key injury still unconfirmed.

**Combos:** Legs in the same game are rarely independent. For example, a QB passing over and his team's moneyline tend to hit together. Simulate each game thousands of times to get the true joint probability. Only suggest a combo when that probability beats the Kalshi combo price. Cap combos at four legs.

**Stake guide (optional):** quarter-Kelly, capped at 2% of a bankroll figure Logan enters. The engine never sees his account.

## What Logan sees

A daily pick board sorted by edge. Each row links to its Kalshi market and its evidence. The rows below are made-up examples showing the layout.

| Game | Pick | Type | Kalshi price | Fair price | Edge | Tipsters for / against | Model | Stake guide |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Example: Team A at Team B | Team B to win | Moneyline | 54¢ | 60¢ | +6 | 3 Proven / 0 | Agrees | 1.0% |
| Example: Team C vs Team D | Over 2.5 goals | Total | 47¢ | 52¢ | +5 | 1 Proven, 2 Promising / 1 Neutral | Agrees | 0.7% |
| Example: Player X | 70+ receiving yards | Player prop | 41¢ | 45¢ | +4 | 2 Promising / 0 | Agrees | 0.5% |
| Example: 3-leg combo | B win + X 70+ yds + Over | Combo | 14¢ | 17¢ | +3 | Built from legs above | Simulated | 0.3% |

Pick card (opens from a row):
- Every tipster on each side, with tier, record in that pick type, and post time.
- Model number, de-vigged sportsbook number, and the blend.
- Kalshi order book depth at the current price.
- Injury and lineup notes since the last refresh.
- Two buttons: **Took it** (records price and size) and **Pass**. Both write to logan_decisions.

Filters: sport, league, pick type, minimum edge, Proven-tipster-only, game start window.
Weekly report: the board's record, Logan's record, and each tipster tier's record side by side.

## Tech stack and build phases

| Layer | Suggested tool | Why |
| --- | --- | --- |
| Language | Python | Every listed sports dataset has a Python client |
| Database | Postgres + TimescaleDB | Handles tens of millions of time-stamped rows |
| Cold history | Parquet + DuckDB | Cheap storage for old play-by-play and odds |
| Scraping | httpx (APIs), Playwright (browser pages) | Covers both feed types |
| Scheduling | Prefect or cron | Morning run, pre-game runs, nightly grading |
| Models | pandas, scikit-learn, LightGBM | Ratings, prop projections, blend weights |
| Board | Streamlit to start | A working board in days |
| Alerts | Discord or Slack webhook | Pushes high-edge picks to Logan's phone |

Build order (each phase gated before the next starts):
1. **Kalshi sync + NFL.** Pull every NFL market daily and store price snapshots. Gate: every open NFL game market on Kalshi is in the database.
2. **NFL odds and results backfill.** Gate: closing lines found for 95%+ of past games.
3. **NFL tipster ingestion.** Capture picks from 5–10 sources with timestamps, and backfill what's public. Gate: 98%+ of picks matched to the correct game and market.
4. **Scoring and backtest.** Grade every pick, compute trust scores, and backtest on last season. Gate: positive edge against Kalshi-style prices after fees. If the backtest fails, fix the pipeline before expanding.
5. **Pick board v1.** Streamlit board with pick cards and Took it / Pass buttons.
6. **Expand.** Add CFB and NBA, then Premier League, Champions League and MLS, then the remaining soccer leagues. Add player props and combos after each league's game lines work.

## Risks and guardrails

- **Most tipsters don't beat the closing line.** The engine must be allowed to conclude that a source, or a whole sport, has no edge.
- **Overfitting.** Tune on past seasons, test on a held-out season the models never saw, and keep a running out-of-sample record.
- **Scraping terms.** Check each site's terms. Use official feeds where they exist, and fall back to manual entry for sites that bar scraping.
- **Kalshi rules.** API use falls under Kalshi's Developer Agreement. Kalshi is 18+ and blocked in some states (AZ, CT, ID, LA, MI, MT, NV, NJ, NY, TN, WA), and state rules are still shifting.
- **Thin markets.** Soccer and prop books can be shallow. The board shows depth so a large edge on a tiny market isn't mistaken for a real opportunity.
- **No autonomy, by design.** The engine has no trading key and no access to Logan's account.
- **Bankroll discipline.** Cap each pick at 2% of bankroll and show daily exposure.
