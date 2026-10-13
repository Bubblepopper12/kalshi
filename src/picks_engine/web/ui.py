"""Page layout shared by every screen: header, LIVE/DEMO bar, navigation, step tracker."""

from __future__ import annotations

import html

from fastapi.responses import HTMLResponse

from ..config import Settings

CSS = """
:root{--bg:#0a0c0f;--bg2:#0e1116;--card:#12161c;--card2:#171c23;--ink:#e9edf2;--muted:#8a94a3;--faint:#5c6573;
--line:#222833;--line2:#2c3440;--soft:#1a2029;--accent:#2ef2a0;--accent-ink:#04130c;--accent-soft:rgba(46,242,160,.12);
--accent-line:rgba(46,242,160,.35);--danger:#ff6b6b;--danger-soft:rgba(255,107,107,.12);--warn:#ffb547;
--warn-soft:rgba(255,181,71,.12);--info:#7aa7ff;--info-soft:rgba(122,167,255,.12);--live:#ff4d4d;--demo:#4c7dff;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
--sans:"Inter Tight","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
--glow:0 0 0 1px var(--accent-line),0 8px 30px -12px rgba(46,242,160,.35);color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg:#f3f4f1;--bg2:#eceee9;--card:#ffffff;--card2:#f8f9f6;--ink:#0d1117;
--muted:#5a6472;--faint:#8b94a1;--line:#e1e4de;--line2:#d3d7cf;--soft:#eef0eb;--accent:#079663;--accent-ink:#ffffff;
--accent-soft:rgba(7,150,99,.10);--accent-line:rgba(7,150,99,.35);--danger:#c62d2d;--danger-soft:rgba(198,45,45,.08);
--warn:#a8650a;--warn-soft:rgba(220,140,20,.12);--info:#2f5fd0;--info-soft:rgba(47,95,208,.08);
--glow:0 0 0 1px var(--accent-line),0 8px 24px -14px rgba(7,150,99,.35);color-scheme:light}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:radial-gradient(1200px 500px at 50% -200px,var(--bg2),var(--bg));background-attachment:fixed;
color:var(--ink);font:16px/1.5 var(--sans);letter-spacing:-.005em;-webkit-font-smoothing:antialiased}
main{max-width:1080px;margin:0 auto;padding:0 20px 64px}
a{color:var(--accent);text-underline-offset:3px}
.num,.mono,code{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.bar{padding:6px 16px;color:#fff;font:600 12px/1.4 var(--mono);text-align:center;letter-spacing:.08em;text-transform:uppercase}
.bar.live{background:linear-gradient(90deg,#7a1010,var(--live),#7a1010)}.bar.demo{background:var(--demo)}
header.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:6px;margin:0 -20px 22px;padding:12px 20px;
background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
border-bottom:1px solid var(--line)}
header .brand{display:flex;align-items:center;gap:8px;margin-right:auto;font:700 14px/1 var(--mono);letter-spacing:.14em;
text-transform:uppercase;color:var(--ink);text-decoration:none}
header .brand i{width:10px;height:10px;border-radius:2px;background:var(--accent);box-shadow:0 0 12px var(--accent);
transform:rotate(45deg);display:inline-block}
header nav{display:flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
header a.tab{text-decoration:none;color:var(--muted);padding:7px 13px;border-radius:9px;font-weight:600;font-size:14px}
header a.tab:hover{color:var(--ink)}
header a.tab.on{background:var(--soft);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line2)}
header a.logout{color:var(--faint);font-size:13px;text-decoration:none;padding:8px 4px 8px 10px}
h1{font-size:30px;line-height:1.1;margin:0 0 8px;letter-spacing:-.03em;font-weight:750}
h2{font-size:18px;margin:0 0 10px;letter-spacing:-.015em}
h3{font-size:16px;margin:0 0 6px}
p{margin:0 0 10px}
.eyebrow{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:0 0 10px}
.lead{color:var(--muted);margin:0 0 18px;max-width:640px}
.card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:16px;
padding:18px 20px;margin:14px 0}
.muted{color:var(--muted)}.small{font-size:13.5px}
.big{font:700 30px/1.1 var(--mono);letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px}
.note{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.warn{background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 35%,transparent);border-radius:12px;padding:12px 14px}
.bad{background:var(--danger-soft);border:1px solid color-mix(in srgb,var(--danger) 35%,transparent);color:var(--ink);border-radius:12px;padding:12px 14px}
.good{background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:12px;padding:12px 14px}
.err{color:var(--danger);font-weight:700}
.steps{display:flex;gap:6px;margin:0 0 16px;flex-wrap:wrap}
.steps span{padding:6px 12px;border-radius:999px;border:1px solid var(--line);color:var(--muted);font:600 12px/1.2 var(--mono);
letter-spacing:.06em;text-transform:uppercase}
.steps span.on{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.row{display:flex;align-items:center;gap:14px;padding:14px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}
.row .what{flex:1;min-width:0}.row .what b{display:block}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--soft);font-size:12px;font-weight:700}
.btn,button{white-space:nowrap;display:inline-flex;align-items:center;justify-content:center;gap:6px;font:inherit;font-weight:700;font-size:15px;
padding:11px 18px;border-radius:11px;border:0;background:var(--accent);color:var(--accent-ink);text-decoration:none;cursor:pointer;
transition:transform .08s ease,box-shadow .15s ease}
.btn:hover,button:hover{box-shadow:var(--glow)}.btn:active,button:active{transform:translateY(1px)}
.btn.ghost,button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line2)}
.btn.ghost:hover,button.ghost:hover{box-shadow:none;border-color:var(--muted)}
.btn.sm,button.sm{padding:7px 13px;font-size:14px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chips a,.chips button{padding:7px 13px;border-radius:999px;border:1px solid var(--line);background:var(--card);text-decoration:none;
color:var(--muted);font:600 13.5px/1.2 var(--sans);white-space:nowrap}
.chips a:hover,.chips button:hover{color:var(--ink);border-color:var(--line2);box-shadow:none}
.chips a.on,.chips button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.chips.scroll{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px;scrollbar-width:none;-webkit-mask-image:linear-gradient(90deg,#000 92%,transparent)}
.chips.scroll::-webkit-scrollbar{display:none}
dl.sum{display:grid;grid-template-columns:auto 1fr;gap:9px 18px;margin:0}
dl.sum dt{color:var(--muted)}dl.sum dd{margin:0;font-weight:650}
form.stack{display:grid;gap:14px;max-width:460px}
label{display:grid;gap:6px;font-weight:650}
input,select{font:inherit;padding:12px 14px;border-radius:11px;border:1px solid var(--line2);background:var(--bg2);color:var(--ink);outline:none}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
label.check{display:flex;gap:12px;align-items:flex-start}
label.check input{width:22px;height:22px;margin-top:2px;flex:none;accent-color:var(--accent)}
details summary{cursor:pointer;color:var(--muted);font-weight:650;list-style:none}
details summary::before{content:"+ ";font-family:var(--mono);color:var(--accent)}
details[open] summary::before{content:"– "}
code{font-size:12.5px;word-break:break-all;color:var(--muted)}
section{margin:30px 0}
section>h2{display:flex;align-items:baseline;gap:10px;font-size:20px}
.searchbox{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px;margin:12px 0}
.searchbox input[type=search]{width:100%;font-size:17px;padding:13px 15px;border-radius:12px}
.filters{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin-top:10px}
.filters .chips{margin:0}.toggle{display:flex;gap:8px;align-items:center;font-weight:600;font-size:14px;color:var(--muted)}
.toggle input{width:18px;height:18px}
.game{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin:10px 0}
.game header{display:block;margin:0 0 10px;position:static;background:none;border:0;padding:0;backdrop-filter:none}
.game h3{font-size:16px;margin:0 0 2px}
.outs{display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr))}
.outs.n3{grid-template-columns:repeat(3,minmax(0,1fr))}
@media (max-width:560px){.outs.n3{grid-template-columns:1fr}}
.out{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:12px;border:1px solid var(--line);
background:var(--bg2);color:var(--ink);text-decoration:none;min-width:0;transition:border-color .12s}
a.out:hover{border-color:var(--accent-line)}.out.off{opacity:.5}
.oname{font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oprice{font:700 21px/1.2 var(--mono);letter-spacing:-.03em}.osub{font-size:12.5px;color:var(--muted);min-height:18px}
.edge{display:inline-block;padding:1px 8px;border-radius:7px;font:700 12px/1.6 var(--mono)}
.edge.pos{background:var(--accent);color:var(--accent-ink)}.edge.lean{background:var(--accent-soft);color:var(--accent)}
.edge.neg{background:var(--soft);color:var(--muted)}
.badge{display:inline-block;padding:3px 9px;border-radius:7px;font:700 11px/1.5 var(--mono);letter-spacing:.08em;
text-transform:uppercase;margin-right:8px}
.badge.pos{background:var(--accent);color:var(--accent-ink)}.badge.lean{background:var(--accent-soft);color:var(--accent)}
.badge.neg{background:var(--soft);color:var(--muted)}.badge.info{background:var(--info-soft);color:var(--info)}
.badge.warn{background:var(--warn-soft);color:var(--warn)}.badge.bad{background:var(--danger-soft);color:var(--danger)}
.thin{background:var(--warn-soft);border-radius:10px;padding:8px 12px;font-size:13.5px;margin:0 0 10px}
.cautions{margin:12px 0 0;padding:10px 14px 10px 28px;background:var(--warn-soft);border-radius:10px;font-size:13.5px}
.cautions li{margin:2px 0}
.actions{margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.status{display:flex;gap:6px 16px;flex-wrap:wrap;font:500 12.5px/1.5 var(--mono);color:var(--muted);margin:6px 0 0}
.status span::before{content:"▪ ";color:var(--faint)}
.empty{text-align:center;padding:30px 18px}
.ask{display:flex;gap:8px;margin:14px 0;padding:6px;background:var(--card);border:1px solid var(--line2);border-radius:14px}
.ask:focus-within{border-color:var(--accent-line);box-shadow:var(--glow)}
.ask input{flex:1;min-width:0;font-size:16px;padding:11px 12px;border:0;background:transparent;box-shadow:none}
.ask input:focus{box-shadow:none}
.ask button{flex:none;border-radius:10px}
.reply p,.reply ul{margin:0 0 10px}.reply ul{padding-left:20px}.reply li{margin:4px 0}
.question{font-weight:700;font-size:19px;margin:0 0 8px}
.tablewrap{overflow-x:auto;margin:6px 0 14px;border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
td{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:13px}td:first-child{font-family:var(--sans);font-size:14px}
tr:last-child td{border-bottom:0}
th{color:var(--faint);font:600 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;background:var(--bg2)}
.report h2{font-size:20px;margin:22px 0 8px}.report h3{font-size:16px;margin:16px 0 6px}
.verdict{font-weight:700;margin:8px 0 10px}.points{margin:0;padding-left:20px;color:var(--muted)}.points li{margin:5px 0}
.big-letter{font:800 18px/1 var(--mono);padding:9px 0;width:42px;text-align:center;border-radius:10px;letter-spacing:0}
.row.grade{align-items:flex-start}.row.grade .what div{margin-top:3px}
/* ---- bet slips (Picks) ---- */
.hero{display:grid;gap:4px;margin:6px 0 4px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between;margin:14px 0 6px}
.slips{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));margin:14px 0}
.slip{position:relative;display:flex;flex-direction:column;gap:12px;background:linear-gradient(180deg,var(--card2),var(--card));
border:1px solid var(--line);border-radius:18px;padding:16px 16px 14px;overflow:hidden}
.slip::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:linear-gradient(90deg,var(--accent),transparent 70%);opacity:.0}
.slip.strong{border-color:var(--accent-line)}.slip.strong::before{opacity:1}
.slip-top{display:flex;align-items:center;gap:8px;font:600 11px/1.3 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.slip-top .when{margin-left:auto;text-transform:none;letter-spacing:0;font-size:12px}
.kind{padding:3px 8px;border-radius:6px;background:var(--soft);color:var(--muted)}
.kind.spread{color:var(--info);background:var(--info-soft)}.kind.total{color:var(--warn);background:var(--warn-soft)}
.kind.btts{color:#c792ff;background:rgba(199,146,255,.12)}.kind.winner{color:var(--accent);background:var(--accent-soft)}
.slip h3{font-size:19px;line-height:1.25;margin:0;letter-spacing:-.02em}
.slip .game-name{color:var(--muted);font-size:13.5px;margin-top:-6px}
.quote{display:flex;align-items:flex-end;justify-content:space-between;gap:10px}
.quote .price{font:700 30px/1 var(--mono);letter-spacing:-.04em}
.quote .price small{font:600 12px var(--mono);color:var(--muted);letter-spacing:0;margin-left:4px}
.quote .edgebig{font:800 15px/1 var(--mono);padding:8px 10px;border-radius:10px;background:var(--accent);color:var(--accent-ink)}
.quote .edgebig.model{background:var(--accent-soft);color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent-line)}
.meter{position:relative;height:8px;border-radius:99px;background:var(--soft);margin:4px 0 2px}
.meter .gap{position:absolute;top:0;bottom:0;border-radius:99px;background:linear-gradient(90deg,var(--accent-soft),var(--accent))}
.meter .tick{position:absolute;top:-4px;width:2px;height:16px;border-radius:2px;background:var(--ink)}
.meter-labels{display:flex;justify-content:space-between;font:500 11.5px/1.3 var(--mono);color:var(--muted)}
.meter-labels b{color:var(--ink);font-weight:700}
.slip-foot{display:flex;align-items:center;gap:10px;justify-content:space-between;border-top:1px dashed var(--line2);padding-top:12px;margin-top:auto}
.slip-foot .size{font:500 12.5px/1.35 var(--mono);color:var(--muted)}
.slip details{font-size:13.5px}.slip details summary{font-size:12.5px}
.slip .cautions{margin-top:8px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);
border-radius:14px;overflow:hidden;margin:14px 0}
.stats div{background:var(--card);padding:12px 14px}.stats b{display:block;font:700 22px/1.1 var(--mono);letter-spacing:-.03em}
.stats span{font:600 10.5px/1.3 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
@media (max-width:640px){main{padding:0 14px 56px}header.top{margin:0 -14px 18px;padding:10px 14px;gap:4px}
header .brand span{display:none}header a.tab{padding:7px 9px;font-size:13.5px}header a.logout{display:none}
h1{font-size:25px}.slips{grid-template-columns:1fr}.big{font-size:26px}}
@media (max-width:380px){header a.tab{padding:6px 7px;font-size:13px}}
"""

TABS = (("picks", "/", "Picks"), ("find", "/find", "All bets"), ("research", "/research", "Research"),
        ("home", "/account", "Account"))
STEPS = ("Choose", "Review", "Done")
BRAND = '<a class="brand" href="/"><i></i><span>Kalshi bot</span></a>'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
         'href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Inter+Tight:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap">')


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def steps(current: int) -> str:
    return '<div class="steps">' + "".join(
        f'<span class="{"on" if i == current else ""}">{i + 1}. {name}</span>' for i, name in enumerate(STEPS)
    ) + "</div>"


def page(settings: Settings, title: str, body: str, tab: str | None = None, nav: bool = True) -> HTMLResponse:
    bar = ('<div class="bar live">LIVE: bets here use real money</div>' if settings.kalshi_env == "live"
           else '<div class="bar demo">DEMO: practice money only</div>')
    header = ""
    if nav:
        tabs = "".join(f'<a class="tab{" on" if key == tab else ""}" href="{href}">{label}</a>'
                       for key, href, label in TABS)
        header = (f'<header class="top">{BRAND}<nav>{tabs}</nav>'
                  '<a class="logout" href="/logout">Log out</a></header>')
    else:
        header = f'<header class="top">{BRAND}</header>'
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta name="robots" content="noindex"><title>{esc(title)} · Kalshi bot</title>'
           f'{FONTS}<style>{CSS}</style></head><body>{bar}<main>{header}{body}</main></body></html>')
    resp = HTMLResponse(doc)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
