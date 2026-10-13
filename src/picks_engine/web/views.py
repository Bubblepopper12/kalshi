"""HTML pieces: the search bar, game cards and pick cards shared by Picks and All bets."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from ..kalshi.leagues import LEAGUES
from ..live.board import Choice, Game
from ..live.lines import Bet
from ..live.picks import Pick
from .describe import cents, day_label, money, when
from .ui import esc


def pct(x: float | Decimal | None) -> str:
    return "—" if x is None else f"{float(x) * 100:.0f}%"


def bet_href(ticker: str, side: str = "yes", contracts: int | None = None) -> str:
    """Link into the bet flow. No price on purpose: the next page starts from Kalshi's live price."""
    q: dict = {"ticker": ticker, "side": side}
    if contracts:
        q["contracts"] = contracts
    return "/bet?" + urlencode(q)


def patient_price(ask: Decimal | None, bid: Decimal | None) -> int | None:
    """A price (in cents) below the ask that would wait in the order book, or None if there's no room.

    One cent under the ask on tight books; on wide books, halfway between buy and sell prices.
    Resting orders pay Kalshi's maker fee (about a quarter of the taker fee) and skip the spread.
    """
    if ask is None or bid is None or not (0 < ask < 1):
        return None
    a, b = int(ask * 100), int(bid * 100)
    if a - b < 2:
        return None
    return max(b + 1, a - max(1, (a - b) // 2))


# ---------------------------------------------------------------- search + filters


def search_bar(q: str = "", placeholder: str = "Search a team, league or day", picks_filter: bool = False) -> str:
    """Instant search over the game cards below it (client-side), plus quick filters."""
    edge_toggle = ('<label class="toggle"><input type="checkbox" id="f-edge"> Only cheaper on Kalshi</label>'
                   if picks_filter else "")
    return f'''<div class="searchbox">
<input id="q" type="search" value="{esc(q)}" placeholder="{esc(placeholder)}" autocomplete="off" aria-label="Search games">
<div class="filters">
<div class="chips" id="f-day" role="group" aria-label="When">
<a href="#" data-day="all" class="on">Any day</a><a href="#" data-day="today">Today</a>
<a href="#" data-day="tomorrow">Tomorrow</a><a href="#" data-day="week">Next 7 days</a></div>
<label class="toggle"><input type="checkbox" id="f-thin"> Hide stretched prices</label>{edge_toggle}
</div><p class="muted small" id="count"></p></div>'''


SEARCH_JS = """<script>
(function(){
  var q=document.getElementById('q'); if(!q) return;
  var cards=[].slice.call(document.querySelectorAll('article.game[data-k]')), day='all';
  var thin=document.getElementById('f-thin'), edge=document.getElementById('f-edge');
  var count=document.getElementById('count'), empty=document.getElementById('none');
  function iso(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
  function run(){
    var words=q.value.toLowerCase().split(/\\s+/).filter(Boolean), t=new Date(), shown=0;
    var today=iso(t), tom=iso(new Date(t.getTime()+864e5)), wk=iso(new Date(t.getTime()+6*864e5));
    cards.forEach(function(c){
      var k=c.getAttribute('data-k'), d=c.getAttribute('data-day')||'', ok=words.every(function(w){return k.indexOf(w)>=0;});
      if(ok&&day==='today') ok=d===today; if(ok&&day==='tomorrow') ok=d===tom;
      if(ok&&day==='week') ok=d!==''&&d>=today&&d<=wk;
      if(ok&&thin&&thin.checked) ok=c.getAttribute('data-thin')!=='1';
      if(ok&&edge&&edge.checked) ok=parseFloat(c.getAttribute('data-edge')||'-1')>0;
      c.style.display=ok?'':'none'; if(ok) shown++;
    });
    if(count) count.textContent=cards.length?('Showing '+shown+' of '+cards.length+' games'):'';
    if(empty) empty.style.display=(cards.length&&!shown)?'':'none';
    var u=new URL(location.href); if(q.value) u.searchParams.set('q',q.value); else u.searchParams.delete('q');
    history.replaceState(null,'',u);
    [].slice.call(document.querySelectorAll('a.keepq')).forEach(function(a){
      var l=new URL(a.href); if(q.value) l.searchParams.set('q',q.value); else l.searchParams.delete('q'); a.href=l;});
  }
  q.addEventListener('input',run); if(thin) thin.addEventListener('change',run); if(edge) edge.addEventListener('change',run);
  [].slice.call(document.querySelectorAll('#f-day a')).forEach(function(a){a.addEventListener('click',function(e){
    e.preventDefault(); day=a.getAttribute('data-day');
    [].slice.call(document.querySelectorAll('#f-day a')).forEach(function(b){b.classList.toggle('on',b===a);}); run();});});
  run();
})();
</script>"""


def ask_box(q: str = "", placeholder: str = "Ask: best NBA bets, Eagles, my balance…") -> str:
    return (f'<form class="ask" method="get" action="/ask" role="search"><input type="text" name="q" value="{esc(q)}" '
            f'placeholder="{esc(placeholder)}" aria-label="Ask the bot" autocomplete="off" enterkeyhint="go">'
            '<button>Ask</button></form>')


def league_chips(current: str, href, include_all: bool = False) -> str:
    items = ([("ALL", "All leagues")] if include_all else []) + [(c, lg.name) for c, lg in LEAGUES.items()]
    return '<div class="chips scroll">' + "".join(
        f'<a class="keepq{" on" if code == current else ""}" href="{esc(href(code))}">{esc(name)}</a>' for code, name in items
    ) + "</div>"


# ---------------------------------------------------------------- game cards


def _edge_chip(c: Choice, min_edge: float) -> str:
    if c.edge is None:
        return ""
    cls = "pos" if c.edge >= min_edge else "lean" if c.edge > 0 else "neg"
    return f'<span class="edge {cls}">{c.edge * 100:+.1f}</span>'


def _tile(c: Choice, game: Game, min_edge: float, side: str = "yes") -> str:
    price = c.yes_ask if side == "yes" else c.no_ask
    label = (c.name or c.statement) if game.kind == "moneyline" and side == "yes" else \
        (c.statement if side == "yes" else f"NOT: {c.statement}")
    if game.kind == "moneyline" and c.name.lower() in ("tie", "draw"):
        label = c.name.capitalize()
    sub = []
    if side == "yes" and c.book is not None:
        sub.append(f"Books {pct(c.book)}")
    elif side == "yes" and c.yes_bid is not None:
        sub.append(f"sell {cents(c.yes_bid)}")
    chip = _edge_chip(c, min_edge) if side == "yes" else ""
    if price is None or not 0 < price < 1:
        return (f'<div class="out off"><span class="oname">{esc(label)}</span>'
                f'<span class="oprice">—</span><span class="osub">No sellers</span></div>')
    return (f'<a class="out" href="{esc(bet_href(c.ticker, side))}">'
            f'<span class="oname">{esc(label)}</span><span class="oprice">{cents(price)}</span>'
            f'<span class="osub">{" · ".join(sub)} {chip}</span></a>')


def game_card(g: Game, min_edge: float = 0.03, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lg = LEAGUES.get(g.league)
    meta = [lg.name if lg else g.league]
    if g.starts:
        meta.append(when(g.starts) + (" · in progress" if g.starts <= now else ""))
    elif g.day:
        meta.append(day_label(g.day))
    warn = ""
    if g.stretched:
        warn = (f'<p class="thin">Prices add up to {money(g.stretch)} instead of about $1.00: few people are '
                f'trading this yet, so buying now means overpaying. Wait or skip.</p>')
    tiles = []
    for c in g.choices:
        tiles.append(_tile(c, g, min_edge))
        if g.kind != "moneyline":
            tiles.append(_tile(c, g, min_edge, side="no"))
    edge = g.best_edge
    return (f'<article class="game" data-k="{esc(g.keywords(lg.name if lg else ""))}" '
            f'data-day="{g.day.isoformat() if g.day else ""}" data-thin="{1 if g.stretched else 0}" '
            f'data-edge="{"" if edge is None else f"{edge:.4f}"}">'
            f'<header><h3>{esc(g.title or g.event_ticker)}</h3><span class="muted small">{esc(" · ".join(meta))}</span>'
            f'</header>{warn}<div class="outs n{min(len(tiles), 3)}">{"".join(tiles)}</div></article>')


# ---------------------------------------------------------------- pick cards


def pick_card(p: Pick, cash: Decimal | None) -> str:
    c, g = p.choice, p.game
    lg = LEAGUES.get(g.league)
    books = ", ".join(c.books[:4]) + (f" +{len(c.books) - 4} more" if len(c.books) > 4 else "")
    when_txt = (when(g.starts) if g.starts else day_label(g.day))
    if p.contracts > 0:
        suggest = (f"{p.contracts} contract{'s' if p.contracts != 1 else ''} · about {money(p.stake)} · "
                   f"pays {money(p.contracts)} if right")
    elif cash is not None and cash < p.cost:
        suggest = "Add cash on Kalshi to take this one."
    else:
        suggest = "Edge is small for your bankroll: 1 contract at most."
    sharp = (f'<dt>Pinnacle (sharpest book)</dt><dd>{pct(c.pinnacle)}</dd>' if c.pinnacle is not None else "")
    notes = "".join(f"<li>{esc(n)}</li>" for n in p.notes)
    notes = f'<ul class="cautions">{notes}</ul>' if notes else ""
    badge = {"Strong": "pos", "Good": "lean"}.get(p.strength, "neg")
    return f'''<article class="card pick">
<div class="pickhead"><span class="badge {badge}">{esc(p.strength)}</span>
<span class="muted small">{esc(lg.name if lg else g.league)} · {esc(g.title)} · {esc(when_txt)}</span></div>
<h2>{esc(c.statement)}</h2>
<div class="bigline"><span class="edge {badge}">{p.edge * 100:+.1f} points</span> cheaper on Kalshi than the sportsbooks think it's worth</div>
<dl class="sum">
<dt>Sportsbooks say</dt><dd>{pct(c.book)} chance <span class="muted small">({len(c.books)} books: {esc(books)}; range {pct(c.book_low)}–{pct(c.book_high)})</span></dd>
{sharp}
<dt>Kalshi price</dt><dd>{cents(c.yes_ask)} + {p.fee * 100:.1f}¢ fee = {float(p.cost) * 100:.1f}¢</dd>
<dt>Suggested</dt><dd>{esc(suggest)}</dd></dl>{notes}
<p class="actions"><a class="btn" href="{esc(bet_href(c.ticker, "yes", max(p.contracts, 1)))}">Bet this →</a>
<span class="muted small">You'll review it before anything is sent.</span></p></article>'''


# ---------------------------------------------------------------- bet slips (the Picks page)

KIND_TAGS = {"winner": "Winner", "spread": "Spread", "total": "Total", "btts": "Both score"}
LEAGUE_TAGS = {"NFL": "NFL", "CFB": "NCAAF", "NBA": "NBA", "EPL": "EPL", "UCL": "UCL", "MLS": "MLS",
               "LALIGA": "La Liga", "SERIEA": "Serie A", "BUNDESLIGA": "Bundesliga", "LIGUE1": "Ligue 1"}


def size_bet(b: Bet, cash: Decimal | None, max_order: float, kelly_fraction: float = 0.25) -> None:
    """Suggested contracts: quarter-Kelly of cash, capped at the per-bet limit (same rule as winner picks)."""
    from decimal import ROUND_DOWN

    from ..pricing.kelly import stake_fraction

    cost = b.cost
    if cost <= 0:
        return
    budget = Decimal(str(max_order))
    if cash is not None:
        frac = stake_fraction(b.fair, float(cost), kelly_fraction=kelly_fraction, cap=1.0)
        budget = min(budget, cash * Decimal(str(frac)), cash)
    b.contracts = max(int((budget / cost).to_integral_value(rounding=ROUND_DOWN)), 0)
    b.stake = (cost * b.contracts).quantize(Decimal("0.01"))


def slip_card(b: Bet, cash: Decimal | None) -> str:
    cost_pct, fair_pct = float(b.cost) * 100, b.fair * 100
    lo, hi = sorted((cost_pct, fair_pct))
    strength = {"Strong": "pos", "Good": "lean", "Model": "info", "Lean": "neg"}.get(b.strength, "neg")
    when_txt = when(b.starts) if b.starts else ""
    if b.contracts > 0:
        size = f"{b.contracts} × {cents(b.ask)} ≈ {money(b.stake)} · pays {money(b.contracts)}"
    elif cash is not None and cash < b.cost:
        size = "Add cash on Kalshi to take this"
    else:
        size = "Small edge for your bankroll: 1 contract"
    why = [f"<dt>Fair chance</dt><dd>{fair_pct:.1f}% <span class='muted small'>({esc(b.source)})</span></dd>",
           f"<dt>Kalshi cost</dt><dd>{cents(b.ask)} + {float(b.fee) * 100:.1f}¢ fee = {cost_pct:.1f}¢</dd>"]
    if b.books:
        why.append(f"<dt>Sportsbooks</dt><dd>{esc(', '.join(b.books[:5]))}"
                   f"{f' +{len(b.books) - 5}' if len(b.books) > 5 else ''}</dd>")
    if b.pinnacle is not None:
        why.append(f"<dt>Pinnacle</dt><dd>{b.pinnacle * 100:.1f}%</dd>")
    notes = "".join(f"<li>{esc(n)}</li>" for n in b.notes)
    side_txt = "YES" if b.side == "yes" else "NO"
    return f'''<article class="slip{' strong' if b.strength == 'Strong' else ''}" data-kind="{esc(b.kind)}">
<div class="slip-top"><span class="kind {esc(b.kind)}">{esc(KIND_TAGS.get(b.kind, b.kind))}</span>
<span>{esc(LEAGUE_TAGS.get(b.league, b.league))}</span><span class="badge {strength}" style="margin:0">{esc(b.strength)}</span>
<span class="when">{esc(when_txt)}</span></div>
<h3>{esc(b.headline)}</h3><div class="game-name">{esc(b.game)}</div>
<div class="quote"><div class="price">{cents(b.ask)}<small>{side_txt} · +{float(b.fee) * 100:.1f}¢ fee</small></div>
<div class="edgebig{'' if b.exact and b.strength != 'Lean' else ' model'}" title="Fair chance minus cost, in points">+{b.edge * 100:.1f} pts</div></div>
<div><div class="meter" aria-hidden="true"><div class="gap" style="left:{lo:.1f}%;width:{max(hi - lo, 0.8):.1f}%"></div>
<div class="tick" style="left:calc({cost_pct:.1f}% - 1px)"></div></div>
<div class="meter-labels"><span>Cost <b>{cost_pct:.1f}¢</b></span><span>Worth <b>{fair_pct:.1f}¢</b></span></div></div>
<details><summary>Why this pick</summary><dl class="sum" style="margin-top:10px">{"".join(why)}</dl>
{f'<ul class="cautions">{notes}</ul>' if notes else ''}</details>
<div class="slip-foot"><span class="size">{esc(size)}</span>
<a class="btn sm" href="{esc(bet_href(b.ticker, b.side, max(b.contracts, 1)))}">Bet this →</a></div></article>'''


KIND_FILTER_JS = """<script>
(function(){
  var chips=document.querySelectorAll('[data-kindchip]');
  chips.forEach(function(c){c.addEventListener('click',function(e){e.preventDefault();
    var k=c.getAttribute('data-kindchip');
    chips.forEach(function(x){x.classList.toggle('on',x===c);});
    var shown=0;
    document.querySelectorAll('.slip').forEach(function(s){
      var ok=(k==='all'||s.getAttribute('data-kind')===k); s.style.display=ok?'':'none'; if(ok)shown++;});
    var none=document.getElementById('noslips'); if(none) none.style.display=shown?'none':'';
  });});
})();
</script>"""
