"""Indian financial news fetcher and sentiment parser.

Fetches real-time financial headlines for Indian equities from Google News India RSS
(aggregating Livemint, Moneycontrol, Economic Times, Business Standard, NDTV Profit)
and evaluates sentiment signals.
"""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import requests

from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)

# Key financial sentiment keywords for Indian equity context
BULLISH_KEYWORDS = {
    "surge",
    "rally",
    "gain",
    "profit",
    "growth",
    "jump",
    "high",
    "outperform",
    "buy",
    "bullish",
    "record",
    "order",
    "contract",
    "expansion",
    "beat",
    "dividend",
    "upgrade",
    "positive",
    "strong",
    "deal",
    "approval",
    "listing",
    "recovery",
    "soar",
    "momentum",
    "robust",
    "bonus",
}

BEARISH_KEYWORDS = {
    "fall",
    "drop",
    "plunge",
    "loss",
    "decline",
    "low",
    "underperform",
    "sell",
    "bearish",
    "miss",
    "probe",
    "penalty",
    "fraud",
    "downgrade",
    "negative",
    "weak",
    "slump",
    "drag",
    "tumble",
    "debt",
    "default",
    "investigation",
    "layoff",
    "curb",
    "warning",
    "caution",
    "slip",
}


def fetch_indian_news(
    query_or_ticker: str, limit: int = 10, timeout: float = 8.0
) -> list[dict[str, Any]]:
    """Fetch latest financial news for an Indian stock via Google News India RSS.

    Args:
        query_or_ticker: Ticker (e.g. RELIANCE, TCS.NS) or company name.
        limit: Maximum number of articles to return.
        timeout: Request timeout in seconds.

    Returns:
        List of news article dicts with title, source, pub_date, link, and sentiment.
    """
    clean_ticker = query_or_ticker.replace(".NS", "").replace(".BO", "").strip()
    search_query = f"{clean_ticker} share stock news"
    encoded_query = urllib.parse.quote(search_query)

    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    articles: list[dict[str, Any]] = []
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            logger.warning(
                "Google News RSS returned status %d for %s", response.status_code, clean_ticker
            )
            return articles

        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        for item in items[:limit]:
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            source_elem = item.find("source")

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
            pub_date = (
                pub_date_elem.text.strip()
                if pub_date_elem is not None and pub_date_elem.text
                else ""
            )
            source = (
                source_elem.text.strip()
                if source_elem is not None and source_elem.text
                else "Indian Media"
            )

            # Clean publisher from title if duplicated at the end (e.g. "Headline - Source")
            title_text = title.rsplit(" - ", 1)[0].strip() if " - " in title else title

            # Basic sentiment scoring on the headline
            title_lower = title_text.lower()
            bull_hits = [w for w in BULLISH_KEYWORDS if w in title_lower]
            bear_hits = [w for w in BEARISH_KEYWORDS if w in title_lower]

            if len(bull_hits) > len(bear_hits):
                sentiment = "Positive"
            elif len(bear_hits) > len(bull_hits):
                sentiment = "Negative"
            else:
                sentiment = "Neutral"

            articles.append(
                {
                    "title": title_text,
                    "source": source,
                    "pub_date": pub_date,
                    "link": link,
                    "sentiment": sentiment,
                    "bull_hits": bull_hits,
                    "bear_hits": bear_hits,
                }
            )

    except Exception as exc:
        logger.error("Failed to fetch Indian news for %s: %s", clean_ticker, exc)
        raise VendorUnavailableError(f"Indian news fetch failed: {exc}") from exc

    return articles


def evaluate_stock_sentiment(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate aggregate sentiment score and dominant narrative from news articles.

    Score ranges from 1.0 (extremely bearish) to 10.0 (extremely bullish). 5.0 is neutral.
    """
    if not articles:
        return {
            "score": 5.0,
            "sentiment_label": "Neutral",
            "confidence": "Low (No recent articles)",
            "article_count": 0,
            "catalysts": [],
            "risks": [],
        }

    positive_count = sum(1 for a in articles if a["sentiment"] == "Positive")
    negative_count = sum(1 for a in articles if a["sentiment"] == "Negative")
    neutral_count = sum(1 for a in articles if a["sentiment"] == "Neutral")
    total = len(articles)

    # Base score is 5.0. Net positive shifts upwards up to +4.5, net negative downwards to -4.0
    net_ratio = (positive_count - negative_count) / total
    score = round(5.0 + (net_ratio * 4.0), 1)
    score = max(1.0, min(10.0, score))

    if score >= 6.5:
        label = "Bullish"
    elif score <= 3.5:
        label = "Bearish"
    else:
        label = "Neutral"

    catalysts = [a["title"] for a in articles if a["sentiment"] == "Positive"][:3]
    risks = [a["title"] for a in articles if a["sentiment"] == "Negative"][:3]

    confidence = "High" if total >= 5 else "Moderate"

    return {
        "score": score,
        "sentiment_label": label,
        "confidence": f"{confidence} ({total} articles analyzed)",
        "article_count": total,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "catalysts": catalysts,
        "risks": risks,
    }


def get_news_indian(
    ticker: str,
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Formatted news about an Indian equity for LangGraph News Analyst agents."""
    articles = fetch_indian_news(ticker, limit=12)
    if not articles:
        return f"No recent Indian news headlines found for {ticker}."

    clean_ticker = ticker.upper().replace(".NS", "").replace(".BO", "").strip()
    lines = [f"## Indian Financial News for {clean_ticker}:\n"]
    for a in articles:
        lines.append(f"### {a['title']}")
        lines.append(f"Source: {a['source']} | Published: {a['pub_date']}")
        lines.append(f"Sentiment: {a['sentiment']}")
        if a.get("link"):
            lines.append(f"Link: {a['link']}")
        lines.append("")

    return "\n".join(lines)
