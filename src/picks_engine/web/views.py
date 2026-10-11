"""HTML pieces: the search bar, game cards and pick cards shared by Picks and All bets."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from ..kalshi.leagues import LEAGUES
from ..live.board import Choice, Game
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
