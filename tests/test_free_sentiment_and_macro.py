"""Unit tests for 100% free web search, global Reddit sentiment, X sentiment, and macro transmission."""

from unittest.mock import MagicMock, patch

import pandas as pd

from tradingagents.agents.tools import (
    get_macro_snapshot as tool_macro_snapshot,
    search_market_news as tool_search_market_news,
)
from tradingagents.dataflows import router
from tradingagents.dataflows.vendors import macro_snapshot, reddit, web_search

# ============================================================================
# 1. Web Search & Free News Grounding
# ============================================================================


def test_duckduckgo_html_parser_extracts_results():
    """Test DuckDuckGo HTML parser correctly extracts title, link, and snippet."""
    sample_html = """
    <html>
    <body>
        <div class="result__body">
            <h2 class="result__title">
                <a class="result__url" href="https://example.com/vedanta-q2">Vedanta Power Q2 Profit Surges 15%</a>
            </h2>
            <a class="result__snippet" href="https://example.com/vedanta-q2">
                Vedanta Power declared a stellar turnaround with net profit of Rs 83 Cr for Q2 FY26.
            </a>
        </div>
    </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html

    with patch("requests.post", return_value=mock_resp):
        results = web_search.search_duckduckgo("Vedanta Power Q2 results", limit=5)

    assert len(results) == 1
    assert "Vedanta Power Q2 Profit Surges 15%" in results[0]["title"]
    assert "Rs 83 Cr" in results[0]["snippet"]
    assert results[0]["link"] == "https://example.com/vedanta-q2"


def test_google_news_rss_parser():
    """Test Google News RSS feed parser extracts items within date bounds."""
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Google News</title>
            <item>
                <title>Hindustan Zinc reports record quarterly silver production - Economic Times</title>
                <link>https://news.google.com/articles/sample1</link>
                <pubDate>Wed, 28 Oct 2026 10:00:00 GMT</pubDate>
                <description>Hindustan Zinc reported strong silver volume growth...</description>
                <source url="https://economictimes.indiatimes.com">Economic Times</source>
            </item>
        </channel>
    </rss>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_rss

    with patch("requests.get", return_value=mock_resp):
        items = web_search.search_google_news_rss("Hindustan Zinc silver production", limit=5)

    assert len(items) == 1
    assert "Hindustan Zinc reports record quarterly silver production" in items[0]["title"]
    assert items[0]["source"] == "Economic Times"


def test_search_market_news_formatting():
    """Test search_market_news combines news sources into formatted Markdown."""
    fake_rss = [
        {
            "title": "Vedanta Power Turnaround Q2",
            "link": "https://example.com/1",
            "snippet": "Net profit at 83 crore",
            "source": "Moneycontrol",
        }
    ]
    with (
        patch.object(web_search, "search_google_news_rss", return_value=fake_rss),
        patch.object(web_search, "search_duckduckgo", return_value=[]),
    ):
        res = web_search.search_market_news("Vedanta Power")
        assert "Vedanta Power" in res
        assert "Vedanta Power Turnaround Q2" in res
        assert "Net profit at 83 crore" in res


def test_search_x_sentiment_generates_free_chatter():
    """Test search_x_sentiment runs zero-cost site:x.com DDG search and returns summary."""
    fake_ddg_results = [
        {
            "title": "Analyst on X: $RELIANCE breakout imminent above 2850",
            "snippet": "Heavy institutional buying spotted in Reliance Futures today. Target 3000.",
            "link": "https://x.com/analyst/status/123",
        }
    ]
    with patch.object(web_search, "search_duckduckgo", return_value=fake_ddg_results):
        sentiment_summary = web_search.search_x_sentiment("RELIANCE", ticker="RELIANCE.NS")
        assert "X / Twitter" in sentiment_summary
        assert "RELIANCE" in sentiment_summary
        assert "Target 3000" in sentiment_summary


# ============================================================================
# 2. Global Reddit Sentiment & Tier 2 Fallback
# ============================================================================


def test_reddit_global_rss_parsing():
    """Test _fetch_global_rss parses XML items properly."""
    sample_reddit_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Reddit Search</title>
        <entry>
            <title>Vedanta Power Q2 analysis: Hidden gem or debt trap?</title>
            <published>2026-10-28T12:00:00Z</published>
            <content type="html">&lt;p&gt;Operational turnaround looks solid after Q2 PAT turned positive.&lt;/p&gt;</content>
            <category term="IndianStockMarket"/>
        </entry>
    </feed>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_reddit_xml
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(reddit, "urlopen", return_value=mock_resp):
        posts = reddit._fetch_global_rss("Vedanta Power", limit=5, timeout=5.0)

    assert posts is not None
    assert len(posts) == 1
    assert "Vedanta Power Q2 analysis" in posts[0]["title"]
    assert "IndianStockMarket" in posts[0]["subreddit"]


def test_fetch_reddit_global_tier2_fallback_on_rss_failure():
    """Test that when Reddit RSS returns None (rate limit / failure), it seamlessly falls back to DuckDuckGo."""
    fake_ddg_posts = [
        {
            "title": "Anyone tracking Hindustan Zinc dividend yield? : r/IndianStreetBets",
            "snippet": "High dividend payout expected this quarter if LME zinc prices hold.",
            "link": "https://www.reddit.com/r/IndianStreetBets/comments/456/hindzinc/",
        }
    ]

    with (
        patch.object(reddit, "_fetch_global_rss", return_value=None),
        patch.object(reddit, "search_duckduckgo", return_value=fake_ddg_posts),
    ):
        res = reddit.fetch_reddit_global("Hindustan Zinc")

    assert "Global Reddit Investor Discussions" in res
    assert "Hindustan Zinc" in res
    assert "High dividend payout" in res


# ============================================================================
# 3. Sector-Aware Macro Transmission Engine
# ============================================================================


def test_get_macro_snapshot_sector_transmission():
    """Test get_macro_snapshot calculates changes and classifies headwind/tailwind correctly."""

    def fake_ticker(symbol):
        mock = MagicMock()
        mock_hist = MagicMock()
        if symbol == "^TNX":
            series = [4.0] * 20 + [4.5]
        elif symbol == "DX-Y.NYB":
            series = [100.0] * 20 + [103.0]
        elif symbol == "HG=F":
            series = [4.2] * 20 + [3.9]
        elif symbol == "SI=F":
            series = [30.0] * 20 + [30.5]
        elif symbol == "BZ=F":
            series = [75.0] * 20 + [76.0]
        else:
            series = [10.0] * 20 + [10.0]

        df = pd.DataFrame({"Close": series})
        mock_hist.return_value = df
        mock.history = mock_hist
        return mock

    with patch.object(macro_snapshot.yf, "Ticker", side_effect=fake_ticker):
        metals_report = macro_snapshot.get_macro_snapshot(
            as_of_date="2026-10-30", sector="Metals & Mining"
        )
        financials_report = macro_snapshot.get_macro_snapshot(
            as_of_date="2026-10-30", sector="Financials"
        )

    assert "Macroeconomic & Sector Transmission Snapshot" in metals_report
    assert "US 10-Year Treasury Yield" in metals_report
    assert "US Dollar Index" in metals_report

    # In Metals: Rising Yields and Stronger USD are HEADWINDS
    assert "HEADWIND" in metals_report

    # In Financials: Rising Yields expand Net Interest Margins (TAILWIND)
    assert "TAILWIND" in financials_report


# ============================================================================
# 4. Router & Agent Tools Integration
# ============================================================================


def test_router_dispatches_new_tools(monkeypatch):
    """Verify router correctly routes search_market_news and get_macro_snapshot."""
    for v in router.VENDOR_METHODS["search_market_news"]:
        monkeypatch.setitem(
            router.VENDOR_METHODS["search_market_news"],
            v,
            lambda *a, **k: "Market news ok",
        )
    news = router.route_to_vendor("search_market_news", "TCS Q3 results")
    assert news == "Market news ok"

    for v in router.VENDOR_METHODS["get_macro_snapshot"]:
        monkeypatch.setitem(
            router.VENDOR_METHODS["get_macro_snapshot"],
            v,
            lambda *a, **k: "Macro snapshot ok",
        )
    macro = router.route_to_vendor("get_macro_snapshot", "2026-10-30", sector="Energy")
    assert macro == "Macro snapshot ok"


def test_agent_tools_invocation():
    """Verify LangChain @tool wrappers dispatch cleanly."""
    with patch(
        "tradingagents.agents.tools.route_to_vendor", return_value="Tool output ok"
    ) as mock_route:
        res1 = tool_search_market_news.invoke({"query": "Vedanta Power Turnaround"})
        assert res1 == "Tool output ok"
        mock_route.assert_called_with("search_market_news", "Vedanta Power Turnaround", ticker="")

        res2 = tool_macro_snapshot.invoke({"as_of_date": "2026-10-30", "sector": "Metals & Mining"})
        assert res2 == "Tool output ok"
