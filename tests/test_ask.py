import json

import httpx
import pytest
from fastapi.testclient import TestClient

from picks_engine.web import app as webapp
from picks_engine.web.ask import route, to_html
from test_web import login, odds_feed
from test_web import env, exchange, web  # noqa: F401  (pytest fixtures)


@pytest.mark.parametrize("words,url", [
    ("best nba bets tonight", "/?league=NBA"),
    ("show me picks", "/?league=ALL"),
    ("eagles", "/find?league=ALL&q=eagles"),
    ("premier league arsenal", "/find?league=EPL&q=arsenal"),
    ("should I bet on the eagles", "/?league=ALL&q=eagles"),
    ("what's my balance", "/account"),
    ("does the longshot research show anything", "/research"),
    ("serie a", "/?league=SERIEA"),
    ("grade my bets", "/grades"),
    ("", "/"),
])
def test_route_plain_words(words, url):
    assert route(words) == url


def test_reply_html_is_safe():
    out = to_html("Here:\n- [Bet this](/bet?ticker=X&side=yes)\n- [evil](https://evil.test) <script>\n**Strong** pick")
    assert '<a href="/bet?ticker=X&amp;side=yes">Bet this</a>' in out
    assert "https://evil.test" in out and 'href="https' not in out and "<script>" not in out
    assert "<b>Strong</b>" in out and out.count("<li>") == 2


def test_ask_without_key_goes_to_the_right_page(web, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    login(web)
    r = web.get("/ask?q=nba+picks", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?league=NBA"
    assert 'action="/ask"' in web.get("/").text  # the box is on Picks


def test_ask_with_claude_uses_tools(env, exchange, fake, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ODDS_API_KEY", "odds-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sent = []

    def claude(request):
        body = json.loads(request.content)
        sent.append(body)
        assert request.headers["x-api-key"] == "sk-test" and {t["name"] for t in body["tools"]} == {
            "get_picks", "find_games", "research_results", "my_account"}
        if len(sent) == 1:
            return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "t1", "name": "get_picks", "input": {"league": "NFL"}}]})
        result = json.loads(body["messages"][-1]["content"][0]["content"])
        link = result["picks"][0]["review_link"]
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [
            {"type": "text", "text": f"One good bet: **Philadelphia** at 58¢. [Review it]({link})"}]})

    handler, _ = odds_feed()
    for m in fake.markets["KXNFLGAME"]:
        if m["event_ticker"].endswith("DALPHI"):
            phi = m["ticker"].endswith("PHI")
            m.update(yes_sub_title="Philadelphia" if phi else "Dallas", yes_ask=58 if phi else 43)
    app = webapp.create_app(trading_transport=httpx.MockTransport(exchange.handler),
                            market_transport=httpx.MockTransport(fake.handler),
                            odds_transport=httpx.MockTransport(handler), ask_transport=httpx.MockTransport(claude))
    client = TestClient(app, base_url="https://testserver")
    login(client)
    r = client.get("/ask?q=best+nfl+bet")
    assert "best nfl bet" in r.text and "<b>Philadelphia</b>" in r.text
    assert 'href="/bet?ticker=KXNFLGAME-26OCT18DALPHI-PHI&amp;side=yes&amp;contracts=' in r.text
    assert len(sent) == 2 and "Now:" in sent[0]["messages"][0]["content"]


def test_ask_reports_claude_errors(web, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-bad")
    app = webapp.create_app(ask_transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})))
    client = TestClient(app, base_url="https://testserver")
    login(client)
    r = client.get("/ask?q=eagles")
    assert "invalid x-api-key" in r.text and 'href="/find?league=ALL&amp;q=eagles"' in r.text


def test_research_tab(web, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "RESEARCH_DIR", tmp_path)
    login(web)
    assert "No research yet" in web.get("/research").text
    (tmp_path / "summary.json").write_text(json.dumps({
        "generated": "2026-10-13T11:20:00+00:00", "since": "2025-08-01",
        "leagues": [{"code": "EPL", "name": "Premier League", "markets": 900, "games": 300, "source": "football-data",
                     "tag": "none", "verdict": "No edge: when Kalshi looked cheaper than the books, it lost money.",
                     "points": ["Cheap long shots lost money."], "error": ""},
                    {"code": "NBA", "name": "NBA", "tag": "error", "error": "Not loaded: no series", "points": []}],
        "pooled": ["## All leagues together", "", "| Price | Markets |", "| --- | --- |", "| 0–10¢ | 12 |"]}))
    (tmp_path / "EPL.md").write_text("# Kalshi Premier League history test\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n")
    r = web.get("/research")
    assert "No edge" in r.text and "Cheap long shots lost money." in r.text and "Not loaded: no series" in r.text
    assert "<td>0–10¢</td>" in r.text and 'href="/research/EPL"' in r.text and 'href="/research/NBA"' not in r.text
    assert "<td>2</td>" in web.get("/research/EPL").text
    assert "No report" in web.get("/research/NBA").text
