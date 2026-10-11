# Kalshi Picks Engine

It stores picks, results, odds and Kalshi prices, scores every tipster by their
real track record, gives Logan a ranked pick board, and can place orders on
Kalshi, **but only an order Logan has approved, one ticket at a time.** It
starts on Kalshi's practice exchange (demo). The full design is in
[CONCEPT.md](CONCEPT.md).

## How trading works: nothing happens unless you approve it

1. **Ticket.** You make an order ticket from a pick card on the board, or with
   `picks trade propose`. A ticket says: which market, YES or NO, how many
   contracts, and the most you'll pay per contract. **Nothing is sent.**
2. **Approve.** You approve that exact ticket. On the board, tick *"I approve
   this exact order"* and press **Send to Kalshi**. In the terminal, run
   `picks trade approve <id>` and type the market ticker back. Tickets you
   don't approve within 30 minutes expire.
3. **Checks.** Right before sending, the bot checks the limits below again. If
   any check fails, nothing is sent and it says why in plain words.
4. **Send.** One *limit* buy order at your price or better. If it doesn't fill,
   it stops resting after 15 minutes. Every step is saved in `trade_audit`
   (`picks trade log <id>`).

What the bot will never do:

- Trade on its own. There's no auto-trade mode and no setting that turns
  approval off. Board picks are suggestions until you approve a ticket.
- Use market orders, sell, or call anything except: read balance, positions,
  orders and fills; place a limit buy; cancel an order. Any other Kalshi call
  is refused before it leaves the machine.
- Send a demo ticket to the live exchange, or the reverse.
- Send the same ticket twice (double-clicks included).

### Limits (set in `.env`, checked before every order)

| Limit | Default |
| --- | --- |
| Most one order can cost (contracts × price + fee) | $10 |
| Most all of today's orders can cost (UTC day) | $50 |
| Contracts per order | 100 |
| Open orders at once | 5 |
| Price range | 3¢–95¢ |
| Ticket must be approved within | 30 min |
| Unfilled order stops resting after | 15 min |
| Account balance | must cover the order |

**Stop switch:** `picks trade halt` (or **Halt all trading** on the board)
blocks every order until `picks trade resume`.

### Trading setup

1. **Start on demo.** Make a free practice account at
   [demo.kalshi.co](https://demo.kalshi.co). It's separate from your real
   Kalshi account and uses play money.
2. **Make an API key on that demo account** (Account & security → API keys).
   Kalshi shows a **Key ID** and downloads a **private key file**.
3. **Keep the key file on the computer that runs the bot**, e.g.
   `~/.kalshi/demo.key`, then `chmod 600 ~/.kalshi/demo.key`. The bot refuses
   key files other users can read. Never paste the private key into a chat,
   email or this repository (`.gitignore` blocks `*.key` and `*.pem`).
4. In `.env`: `KALSHI_ENV=demo`, `KALSHI_API_KEY_ID=<your key id>`,
   `KALSHI_PRIVATE_KEY_PATH=~/.kalshi/demo.key`.
5. Check it: `picks trade status`, then `picks trade balance`.
6. Try a 1-contract ticket:
   ```bash
   picks trade propose --ticker <MARKET-TICKER> --side yes --price 40 --contracts 1
   picks trade approve 1        # shows the ticket, asks you to type the ticker
   picks trade list             # open orders and fills
   picks trade refresh          # update fills from Kalshi
   picks trade cancel 1         # cancel if still resting
   ```
7. **Real money, only when you decide to:** make a key on your real Kalshi
   account, point `KALSHI_PRIVATE_KEY_PATH` at it, set `KALSHI_ENV=live`, and
   set limits you're comfortable losing. The board shows a red LIVE banner,
   and the terminal warns before each approval.

The demo exchange's market tickers can differ from the live ones. Use tickers
from the demo site when trading on demo.

## Web app (Vercel): private to you

The repo deploys to Vercel as a small website (`api/index.py`, `vercel.json`):
your balance, positions, resting orders and fills, live game markets, and the
same approve-before-sending order tickets. It keeps no database; every page
reads your account straight from Kalshi, so Kalshi's history is the record.

**Who can get in:** only someone with your password **and** the 6-digit code
from your authenticator app. The app stays locked (a "Setup needed" page, no
login form) if the password is missing or under 16 characters, or if Kalshi
keys are set without a two-step secret. Sessions last 12 hours. Even when
logged in, each order needs its own "I approve this exact order" tick, and the
limits are checked against your live account before sending.

### Setup (once)

1. **Make a password and a two-step secret on your Mac.** In Terminal:
   ```bash
   python3 -c "import secrets;print(secrets.token_urlsafe(24))"
   python3 -c "import base64,os;print(base64.b32encode(os.urandom(20)).decode())"
   ```
   The first line is your password. Save it in the Passwords app. The
   second is your two-step secret. On a Mac or iPhone, open **Passwords** → the
   entry for your site → **Set Up Verification Code** → **Enter Setup Key** and
   paste it. Google Authenticator works too.
2. **In Vercel → the `kalshi` project → Settings → Environment Variables**, add
   these four, tick **Production only** (not Preview or Development), and mark
   them **Sensitive**:

   | Name | Value |
   | --- | --- |
   | `APP_PASSWORD` | the password from step 1 |
   | `APP_TOTP_SECRET` | the two-step secret from step 1 |
   | `KALSHI_API_KEY_ID` | your Kalshi Key ID |
   | `KALSHI_PRIVATE_KEY` | the whole private key text, from `-----BEGIN` to `-----END ...-----` |

   The plain settings (`KALSHI_ENV=live`, $5 per order, $20 per day) live in
   `src/picks_engine/web/web.env`. Anything you set in Vercel overrides them.

   To copy the key text on your Mac without it showing: `pbcopy < ~/.kalshi/kalshi.key`,
   then paste into the value box.
3. **Redeploy** (Deployments → ⋯ → Redeploy) so the settings take effect.
4. Open your site. Log in with the password and the current 6-digit code.

### Picks (the bot's recommendations)

The **Picks** tab is the first page after login. For each league it compares
Kalshi's full-game winner prices with the sportsbooks' prices for the same game
(Pinnacle, DraftKings, FanDuel, BetMGM, Caesars and others, via The Odds API),
removes the books' built-in margin, and shows a pick when Kalshi sells an outcome
at least 3 points cheaper after Kalshi's fee. Each pick says why (the books'
chance, Kalshi's price, how many books agree), suggests a size (quarter-Kelly on
your cash, never above your per-bet limit) and links to the normal review →
approve flow. Sportsbooks are only a price reference: all trading is on Kalshi.

Setup: get a free key at the-odds-api.com (500 requests a month; each league
refresh uses one, results are reused for 10 minutes), then add `ODDS_API_KEY`
in Vercel (Production, Sensitive) and redeploy. Optional: `PICKS_MIN_EDGE`
(default `0.03`), `ODDS_BOOKMAKERS` (comma-separated bookmaker keys).

Not in picks yet: tipster track records and the bot's own model (they need
collected history first), spreads and totals.

### Emergency stops

- **Cut the bot off from your account:** delete the API key on kalshi.com
  (Account & security → API keys). Nothing can trade without it.
- **Pause sending but keep viewing:** add `TRADING_HALTED` = `1` in Vercel and redeploy.
- **Lock everyone out:** change `APP_PASSWORD` (or `APP_TOTP_SECRET`) and
  redeploy. That also logs out every existing session.

### Good to know

- Branch previews get no keys (they're Production-only), so they can't trade.
  On the Hobby plan Vercel also puts preview links behind your Vercel login.
- Keep the GitHub repo **private** if you'd rather the code isn't public. It
  never contains your keys either way.
- One person per deployment. Accounts for other users need a different design
  (their own logins, their own keys stored encrypted per user); see CONCEPT.md.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[postgres,board,trading,dev]"

docker compose up -d            # Postgres 16 + TimescaleDB on localhost:5432
cp .env.example .env && set -a && . ./.env && set +a

picks init-db                   # tables + hypertables
picks discover NFL              # which Kalshi series count as NFL today
picks sync NFL                  # series, events, markets + first price snapshot
picks snapshot NFL --every 300  # price snapshot of every open market, every 5 min
picks gate 1 --league NFL       # Phase 1 gate: every open NFL game market stored?
picks board                     # Streamlit pick board on http://localhost:8501
```

No Docker? `PICKS_DATABASE_URL=sqlite:///picks.db` works for a quick try.

### Schedule (cron, UTC)

```cron
# Daily listing sync (new series and markets), morning run
0 11 * * *   picks sync NFL CFB NBA
# Price snapshots every 5 minutes
*/5 * * * *  picks snapshot NFL CFB NBA
# Pull settlements overnight, then rescore tipsters
0 8 * * *    picks settle NFL CFB NBA && picks score
```

## What each command does

| Command | What it does |
| --- | --- |
| `picks leagues` | The ten supported leagues and their priority. |
| `picks discover LEAGUE` | Reads Kalshi's live `/series` listing and shows the series that match the league, with the pick type each maps to. Nothing about soccer depth is hard-coded. |
| `picks sync LEAGUE...` | Upserts series, events and markets (with rules text and raw payload) and stores one price snapshot per market. Re-running is safe. |
| `picks snapshot LEAGUE... [--every 300]` | One paginated `/markets` call per series; one bid/ask row per open market. Markets listed since the last sync are added, so none are missed. |
| `picks settle LEAGUE...` | Refreshes status and result for markets past their close time (feeds the weekly report). |
| `picks gate 1 --league NFL` | Compares Kalshi's live open game markets (moneyline, spread, total) to the database. Exits 1 and lists what's missing if any are absent. |
| `picks link LEAGUE` | Attaches Kalshi game events to `games` using date + team codes. Misses go to `id_review_queue`. |
| `picks score` | Recomputes `tipster_scores` (trust and tier per tipster, league and pick type) from `pick_grades`. |
| `picks board` | Opens the Streamlit board: pick board, pick cards (Took it / Pass, or make an order ticket), the Orders tab (approve, reject, cancel, halt), the raw Kalshi market view and the weekly report. |
| `picks trade ...` | Approval-only trading: `status`, `propose`, `list`, `approve`, `reject`, `cancel`, `refresh`, `balance`, `positions`, `halt`, `resume`, `log`. See "How trading works" above. |

Every sync and snapshot writes a row to `sync_runs` (ok/failed, counts, error).

## Code map

```
src/picks_engine/
  config.py            settings from environment variables
  db/schema.py         every warehouse table (see CONCEPT.md "Data model")
  db/session.py        engine, init (Timescale hypertables), dialect-aware upsert
  kalshi/client.py     read-only HTTP client, price parsing, order book maths
  kalshi/leagues.py    league definitions + how to spot their series in live listings
  kalshi/classify.py   series/market -> moneyline | spread | total | prop | combo | future
  kalshi/sync.py       listing sync, snapshots, order books, settlements, Phase 1 gate
  ids/mapping.py       alias table, review queue, Kalshi event -> game linking
  pricing/             American odds, de-vig (power / multiplicative), Kalshi fee, edge, Kelly
  scoring/grading.py   win/loss/push, units, closing-line value, "seen before kickoff" rule
  scoring/trust.py     recency weights, shrinkage, z-scores, Proven/Promising/Neutral/Fade
  scoring/jobs.py      rescore tipsters from the database
  picks/generate.py    tipster signal, blend, edge vs Kalshi, filters, stake guide
  picks/combos.py      joint probability of correlated legs (Gaussian copula simulation)
  picks/store.py       save suggestions, record Logan's decisions
  trading/auth.py      Kalshi API-key request signing (RSA-PSS)
  trading/client.py    authenticated client limited to portfolio reads, limit buys, cancels
  trading/orders.py    ticket -> approve -> checks -> send; limits, halt switch, audit trail
  trading/limits.py    per-order limits shared by the terminal, board and web app
  web/app.py           password + two-step web app for Vercel (api/index.py is the entry point)
  live/odds_api.py     sportsbook moneylines from The Odds API (read-only)
  live/teams.py        matches Kalshi team names to sportsbook names, refuses ambiguous games
  live/picks.py        de-vigged consensus vs. Kalshi price + fee -> picks, sizing
  board/               Streamlit app and the queries behind it
```

## Starting-point numbers (tune by backtest)

| Setting | Default | Where |
| --- | --- | --- |
| ROI shrinkage k | 200 | `ScoringParams.roi_k` |
| CLV shrinkage k | 50 | `ScoringParams.clv_k` |
| Trust weights | 0.6 CLV, 0.4 ROI | `ScoringParams.w_clv / w_roi` |
| Recency half-life | 365 days | `ScoringParams.half_life_days` |
| Proven | top 10% of the group, 300+ picks, trust > 0 | `ScoringParams` |
| Fade | 300+ picks, CLV t-stat ≤ −2 | `ScoringParams.fade_t` |
| Blend weights | model 0.35, market 0.45, tipsters 0.20 (logit space) | `BlendParams` |
| Minimum edge | 3 points after fees | `BlendParams.min_edge` |
| Minimum depth | 100 contracts at the ask | `BlendParams.min_depth` |
| Stake guide | quarter Kelly, cap 2% | `BlendParams.kelly_fraction / stake_cap` |
| Kalshi fee | `ceil_to_cent(0.07 × C × P × (1−P))`, per contract at C = 100 | `KALSHI_FEE_RATE`, `KALSHI_FEE_CONTRACTS` |

A board pick needs the model and the de-vigged sportsbook number both above the
Kalshi cost (price + fee), tracked tipsters not net against it, 3+ points of
edge, enough depth and no unconfirmed key injury. Both YES and NO are checked
on every contract.

## Build status

| Phase | Status |
| --- | --- |
| 1. Kalshi sync + NFL | **Built.** Discovery, listing sync, 5-minute snapshots, order books, settlements and the gate check. Run `picks gate 1` against live Kalshi to pass the gate. |
| 2. NFL odds and results backfill | Schema ready (`games`, `odds_snapshots` hypertable, `plays`, `player_game_stats`). Loaders for nflverse and The Odds API come next. |
| 3. NFL tipster ingestion | Schema, alias table and review queue ready; grading rule for "captured before kickoff" built. Scrapers come next, one source at a time after checking each site's terms. |
| 4. Scoring and backtest | Grading, CLV, trust and tiers built and tested; backtest harness comes after Phase 2–3 data exists. |
| 5. Pick board v1 | Built (Streamlit). Fills up once suggestions are generated from real data. |
| Trading (added) | Approval-only order tickets, limits, stop switch and audit trail; demo by default. Tested against a fake Kalshi exchange, not yet against demo.kalshi.co. |
| 6. Expand | All ten leagues are defined; `picks sync CFB NBA EPL ...` already works for Kalshi data. Models, props and combos per league come later. |

## Before the first live run

- **API host.** `KALSHI_API_BASE` defaults to Kalshi's documented public host,
  `https://api.elections.kalshi.com/trade-api/v2` (it serves every market, not
  just elections). The concept's `external-api.kalshi.com` can be set there
  instead if Kalshi points you to it. The code was tested against a fake Kalshi API because the build
  machine couldn't reach Kalshi, so the first `picks discover NFL` is the real
  check. Both legacy cent fields (`yes_ask: 54`) and newer dollar fields
  (`yes_ask_dollars: "0.5400"`) are read.
- **Fees.** Check Kalshi's current fee schedule for sports series and set
  `KALSHI_FEE_RATE` if it differs from 0.07.
- **Rules.** API use falls under Kalshi's Developer Agreement. Kalshi is 18+ and
  unavailable in some states. Check each tipster site's terms before scraping it.

## Tests

```bash
pytest                                                     # SQLite
PICKS_TEST_DATABASE_URL=postgresql+psycopg://... pytest    # Postgres (drops and recreates tables)
```
