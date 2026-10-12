"""Page layout shared by every screen: header, LIVE/DEMO bar, navigation, step tracker."""

from __future__ import annotations

import html

from fastapi.responses import HTMLResponse

from ..config import Settings

CSS = """
:root{--bg:#f5f5f2;--card:#fff;--ink:#16181d;--muted:#5f6670;--line:#e2e2dc;--soft:#f0f0eb;
--accent:#0b6e4f;--accent-ink:#fff;--accent-soft:#e3f2ec;--danger:#b42318;--danger-soft:#fdecea;
--warn-soft:#fff4e0;--live:#b42318;--demo:#1f5fbf}
@media (prefers-color-scheme:dark){:root{--bg:#0f1012;--card:#1a1b1e;--ink:#eceef1;--muted:#a3a9b2;
--line:#2b2d31;--soft:#232428;--accent:#3ccf91;--accent-ink:#06261a;--accent-soft:#16352a;
--danger:#ff7a6e;--danger-soft:#3a1b18;--warn-soft:#3a2d12}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px 16px 48px}
a{color:var(--accent)}
.bar{padding:8px 16px;color:#fff;font-weight:700;text-align:center;font-size:15px}
.bar.live{background:var(--live)}.bar.demo{background:var(--demo)}
header{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0 16px}
header .brand{font-weight:800;font-size:19px;margin-right:auto}
header a.tab{text-decoration:none;color:var(--ink);padding:8px 14px;border-radius:999px;font-weight:600}
header a.tab.on{background:var(--ink);color:var(--bg)}
header a.logout{color:var(--muted);font-size:15px;text-decoration:none;padding:8px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px}
h2{font-size:19px;margin:0 0 10px}
p{margin:0 0 10px}
.lead{color:var(--muted);margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
.muted{color:var(--muted)}.small{font-size:14px}
.big{font-size:34px;font-weight:800;line-height:1.1}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.note{background:var(--soft);border-radius:10px;padding:12px 14px}
.warn{background:var(--warn-soft);border-radius:10px;padding:12px 14px}
.bad{background:var(--danger-soft);color:var(--ink);border-radius:10px;padding:12px 14px}
.good{background:var(--accent-soft);border-radius:10px;padding:12px 14px}
.err{color:var(--danger);font-weight:700}
.steps{display:flex;gap:6px;margin:0 0 14px;font-size:14px;flex-wrap:wrap}
.steps span{padding:6px 12px;border-radius:999px;background:var(--soft);color:var(--muted);font-weight:600}
.steps span.on{background:var(--ink);color:var(--bg)}
.row{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}
.row .what{flex:1;min-width:0}
.row .what b{display:block}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--soft);font-size:13px;font-weight:700}
.btn,button{display:inline-block;font:inherit;font-weight:700;padding:11px 18px;border-radius:10px;border:0;
background:var(--accent);color:var(--accent-ink);text-decoration:none;cursor:pointer;text-align:center}
.btn.ghost,button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
.btn.sm,button.sm{padding:8px 14px;font-size:15px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 4px}
.chips a{padding:8px 14px;border-radius:999px;border:1px solid var(--line);text-decoration:none;color:var(--ink);font-weight:600;font-size:15px}
.chips a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
dl.sum{display:grid;grid-template-columns:auto 1fr;gap:10px 16px;margin:0}
dl.sum dt{color:var(--muted)}dl.sum dd{margin:0;font-weight:700}
form.stack{display:grid;gap:14px;max-width:440px}
label{display:grid;gap:6px;font-weight:700}
input,select{font:inherit;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
label.check{display:flex;gap:12px;align-items:flex-start;font-weight:700}
label.check input{width:24px;height:24px;margin-top:2px;flex:none;accent-color:var(--accent)}
details summary{cursor:pointer;color:var(--muted);font-weight:600}
code{font-size:13px;word-break:break-all;color:var(--muted)}
header.top{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;margin:0 0 12px;
border-bottom:1px solid var(--line)}
section{margin:22px 0}section>h2{display:flex;align-items:baseline;gap:8px}
.chips.scroll{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px;scrollbar-width:none}
.chips.scroll::-webkit-scrollbar{display:none}.chips a{white-space:nowrap}
.searchbox{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.searchbox input[type=search]{width:100%;font-size:18px;padding:14px 16px;border-radius:12px}
.filters{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin-top:10px}
.filters .chips{margin:0}.toggle{display:flex;gap:8px;align-items:center;font-weight:600;font-size:15px}
.toggle input{width:20px;height:20px}
.game{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0}
.game header{display:block;margin:0 0 10px}.game h3{font-size:18px;margin:0 0 2px}
.outs{display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr))}
.outs.n3{grid-template-columns:repeat(3,minmax(0,1fr))}
@media (max-width:520px){.outs.n3{grid-template-columns:1fr}}
.out{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:12px;border:1px solid var(--line);
background:var(--soft);color:var(--ink);text-decoration:none;min-width:0}
a.out:hover{border-color:var(--accent)}.out.off{opacity:.55}
.oname{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oprice{font-size:22px;font-weight:800}.osub{font-size:13px;color:var(--muted);min-height:18px}
.edge{display:inline-block;padding:1px 8px;border-radius:999px;font-weight:800;font-size:13px}
.edge.pos{background:var(--accent);color:var(--accent-ink)}.edge.lean{background:var(--accent-soft);color:var(--ink)}
.edge.neg{background:var(--soft);color:var(--muted)}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:800;font-size:13px;margin-right:8px}
.badge.pos{background:var(--accent);color:var(--accent-ink)}.badge.lean{background:var(--accent-soft);color:var(--ink)}
.badge.neg{background:var(--soft);color:var(--muted)}
.thin{background:var(--warn-soft);border-radius:10px;padding:8px 12px;font-size:14px;margin:0 0 10px}
.pick h2{font-size:22px;margin:8px 0 6px}.bigline{margin:0 0 12px}.bigline .edge{font-size:15px;padding:3px 10px}
.cautions{margin:12px 0 0;padding:10px 14px 10px 30px;background:var(--warn-soft);border-radius:10px;font-size:14px}
.actions{margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.status{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:14px;color:var(--muted);margin:6px 0 0}
.empty{text-align:center;padding:26px 16px}
.ask{display:flex;gap:8px;margin:12px 0}.ask input{flex:1;min-width:0;font-size:17px;padding:13px 14px;border-radius:12px}
.ask button{flex:none;border-radius:12px}
.reply p,.reply ul{margin:0 0 10px}.reply ul{padding-left:20px}.reply li{margin:4px 0}
.question{font-weight:700;font-size:19px;margin:0 0 6px}
.tablewrap{overflow-x:auto;margin:6px 0 12px}
table{border-collapse:collapse;width:100%;font-size:15px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:13px}
.report h2{font-size:21px;margin:18px 0 8px}.report h3{font-size:17px;margin:16px 0 6px}
.verdict{font-weight:700;margin:6px 0 8px}.points{margin:0;padding-left:20px}.points li{margin:4px 0}
.badge.warn{background:var(--warn-soft);color:var(--ink)}
.big-letter{font-size:20px;padding:6px 12px;min-width:44px;text-align:center}
.row.grade{align-items:flex-start}.row.grade .what div{margin-top:3px}.badge.bad{background:var(--danger-soft);color:var(--ink)}
@media (max-width:520px){header.top{gap:2px;flex-wrap:nowrap}header .brand{font-size:16px}
header a.tab{padding:7px 8px;font-size:14px}header a.logout{font-size:13px;padding:6px 4px}
h1{font-size:24px}}
@media (max-width:420px){header .brand{display:none}header a.tab{padding:7px 7px}}
"""

TABS = (("picks", "/", "Picks"), ("find", "/find", "All bets"), ("research", "/research", "Research"),
        ("home", "/account", "Account"))
STEPS = ("Choose", "Review", "Done")


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
        header = f'<header class="top"><span class="brand">Kalshi bot</span>{tabs}<a class="logout" href="/logout">Log out</a></header>'
    else:
        header = '<header class="top"><span class="brand">Kalshi bot</span></header>'
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta name="robots" content="noindex"><title>{esc(title)} · Kalshi bot</title>'
           f'<style>{CSS}</style></head><body>{bar}<main>{header}{body}</main></body></html>')
    resp = HTMLResponse(doc)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
