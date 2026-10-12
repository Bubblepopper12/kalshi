"""The "Ask" box: type what you want in plain words.

Without an Anthropic key, route() reads the words and sends you to the right page
("best NBA bets" -> Picks for the NBA, "eagles" -> the Eagles' games, "balance" -> My account).
With ANTHROPIC_API_KEY set, answer() lets Claude look things up with read-only tools
(picks, games, research results, your account) and reply in plain English with links.
Neither can place a bet: a bet always goes through the review page and your approval.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_ROUNDS = 5
TIME_BUDGET = 45  # seconds; the website's server stops a request at 60

LEAGUE_WORDS = [
    (r"\bcollege football\b|\bcfb\b|\bncaaf?\b|\bcollege\b|\bcfp\b", "CFB"),
    (r"\bnfl\b|\bpro football\b", "NFL"),
    (r"\bnba\b|\bbasketball\b", "NBA"),
    (r"\bpremier league\b|\bepl\b|\bprem\b|\benglish\b", "EPL"),
    (r"\bchampions league\b|\bucl\b", "UCL"),
    (r"\bmls\b|\bmajor league soccer\b", "MLS"),
    (r"\bla ?liga\b|\bspain\b|\bspanish\b", "LALIGA"),
    (r"\bserie a\b|\bitaly\b|\bitalian\b", "SERIEA"),
    (r"\bbundesliga\b|\bgermany\b|\bgerman\b", "BUNDESLIGA"),
    (r"\bligue ?1\b|\bfrance\b|\bfrench\b", "LIGUE1"),
]
RESEARCH = r"\b(research|history|historical|backtest|tested|test|report|bias|long ?shots?|results so far)\b"
ACCOUNT = r"\b(balance|account|cash|positions?|my bets|orders?|portfolio|spent|holdings?|funds)\b"
PICKS = r"\b(picks?|best|recommend\w*|should i|good|value|cheap\w*|edges?|worth|top|tonight|today|bet on)\b"
FILLER = set("""a an the me my i show find get give what whats what's which who is are was were on for of in at to
and or any all some games game bets bet odds price prices line lines market markets kalshi please can you could
would will this that these those there about with against vs v versus league leagues soccer football matches match
tell know see look up next upcoming should do does did it take place put think like want need help how much
win wins winner will going go week weekend""".split())


def leagues_in(text: str) -> list[str]:
    t = text.lower()
    return [code for pattern, code in LEAGUE_WORDS if re.search(pattern, t)]


def route(question: str) -> str:
    """The page that best answers a plain-words request, without any AI."""
    q = (question or "").strip().lower()
    if not q:
        return "/"
    found = leagues_in(q)
    league = found[0] if len(found) == 1 else "ALL"
    if re.search(RESEARCH, q):
        return "/research"
    if re.search(ACCOUNT, q):
        return "/account"
    stripped = q
    for pattern, _ in LEAGUE_WORDS:
        stripped = re.sub(pattern, " ", stripped)
    words = [w for w in re.findall(r"[a-z0-9']+", stripped) if w not in FILLER and not re.fullmatch(PICKS, w)]
    if words and not re.search(PICKS, q):
        return "/find?" + urlencode({"league": league, "q": " ".join(words)})
    if words:
        return "/?" + urlencode({"league": league, "q": " ".join(words)})
    return "/?" + urlencode({"league": league})


# ---------------------------------------------------------------- Claude


SYSTEM = """You are the assistant inside a private Kalshi sports-betting research website that belongs to one person.
You help them find good bets on Kalshi and understand the numbers.

How the site works:
- Picks compare Kalshi's price (plus Kalshi's fee) with the sportsbooks' fair chance (vig removed). The
  difference is the "edge" in points. "Strong" picks need 5+ points, 3+ sportsbooks and Pinnacle agreeing.
- A Kalshi contract pays $1 if right and $0 if wrong; the price in cents is roughly the market's chance.
- Research results come from testing Kalshi's past prices against what actually happened.
- You cannot place, change or cancel bets. To bet, give the person the review link from your tools
  (it starts with /bet). They review it and must approve it themselves before anything is sent.

Rules:
- Use the tools for every number. Never invent prices, chances, games or results.
- Answer in short, plain English for someone who is new to betting: a few sentences or a short list.
- Link to pages with markdown links to the site's own paths, e.g. [Bet this](/bet?ticker=...).
- Be honest: if nothing looks good, say so. Edges are estimates, not guarantees; suggest small bets.
- Today's date and time come with each question."""


@dataclass
class Tool:
    description: str
    schema: dict
    run: Callable[[dict], object]


@dataclass
class Answer:
    text: str
    used: list[str] = field(default_factory=list)  # tool names, in order
    error: str = ""


def answer(question: str, tools: dict[str, Tool], api_key: str, model: str = DEFAULT_MODEL, now: str = "",
           transport: httpx.BaseTransport | None = None) -> Answer:
    """Let Claude answer with the given read-only tools. Errors come back in Answer.error, never raised."""
    messages: list[dict] = [{"role": "user", "content": f"{question.strip()}\n\n(Now: {now})"}]
    spec = [{"name": n, "description": t.description, "input_schema": t.schema} for n, t in tools.items()]
    used: list[str] = []
    started = time.monotonic()
    with httpx.Client(timeout=httpx.Timeout(30.0), transport=transport) as http:
        for _ in range(MAX_ROUNDS):
            try:
                resp = http.post(ANTHROPIC_URL, json={"model": model, "max_tokens": 1500, "system": SYSTEM,
                                                      "tools": spec, "messages": messages},
                                 headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
            except httpx.HTTPError as exc:
                return Answer("", used, f"Couldn't reach Claude ({exc.__class__.__name__}).")
            if resp.status_code != 200:
                try:
                    detail = resp.json().get("error", {}).get("message", "")
                except ValueError:
                    detail = ""
                return Answer("", used, f"Claude returned an error ({resp.status_code}). {detail}".strip())
            data = resp.json()
            content = data.get("content") or []
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            calls = [b for b in content if b.get("type") == "tool_use"]
            if data.get("stop_reason") != "tool_use" or not calls:
                return Answer(text, used)
            if time.monotonic() - started > TIME_BUDGET:
                return Answer(text or "That took too long to look up. Try a narrower question.", used)
            messages.append({"role": "assistant", "content": content})
            results = []
            for call in calls:
                used.append(call["name"])
                tool = tools.get(call["name"])
                try:
                    out = tool.run(call.get("input") or {}) if tool else {"error": "unknown tool"}
                except Exception as exc:  # a tool failing shouldn't sink the whole answer
                    out = {"error": f"{exc.__class__.__name__}: {exc}"}
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": json.dumps(out, default=str)[:20000]})
            messages.append({"role": "user", "content": results})
    return Answer("I couldn't finish looking that up. Try asking something narrower.", used)


# ---------------------------------------------------------------- showing the reply


def _inline(text: str) -> str:
    out, last = [], 0
    for m in re.finditer(r"\[([^\]]+)\]\((/[^)\s]*)\)|\*\*([^*]+)\*\*", text):
        out.append(html.escape(text[last:m.start()]))
        if m.group(1):
            out.append(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>')
        else:
            out.append(f"<b>{html.escape(m.group(3))}</b>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def to_html(text: str) -> str:
    """Claude's reply as safe HTML: paragraphs, lists, bold, and links to this site only."""
    blocks, items = [], []

    def flush():
        if items:
            blocks.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)", line)
        if m:
            items.append(m.group(1))
            continue
        flush()
        if line:
            line = re.sub(r"^#+\s*", "", line)
            blocks.append(f"<p>{_inline(line)}</p>")
    flush()
    return "".join(blocks)
