"""Zero-cost Web & Social News Search module.

Provides 100% free, credential-less search engine capabilities using DuckDuckGo HTML
and Google News RSS feeds to eliminate vendor blindspots on regional, small-cap,
and newly demerged equities (e.g. VEDPOWER, HINDZINC).
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def search_duckduckgo(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Query DuckDuckGo's free HTML endpoint for live web results."""
    clean_query = query.strip()
    if not clean_query:
        return []

    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://html.duckduckgo.com/",
    }
    data = {"q": clean_query}

    try:
        resp = requests.post(url, data=data, headers=headers, timeout=_DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(
                "DuckDuckGo HTML search returned status %s for query %r",
                resp.status_code,
                clean_query,
            )
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for body in soup.find_all("div", class_="result__body"):
            title_tag = body.find("a", class_="result__url")
            snippet_tag = body.find("a", class_="result__snippet")
            head_tag = body.find("h2", class_="result__title")

            if head_tag and snippet_tag:
                title = head_tag.text.strip()
                snippet = snippet_tag.text.strip()
                link = title_tag["href"] if title_tag and "href" in title_tag.attrs else ""
                results.append({"title": title, "snippet": snippet, "link": link})
                if len(results) >= limit:
                    break

        return results
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for query %r: %s", clean_query, exc)
        return []


def search_google_news_rss(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Query Google News RSS for real-time indexed financial and corporate stories."""
    clean_query = query.strip()
    if not clean_query:
        return []

    encoded = urllib.parse.quote_plus(clean_query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {"User-Agent": _USER_AGENT}

    try:
        resp = requests.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(
                "Google News RSS returned status %s for %r", resp.status_code, clean_query
            )
            return []

        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        results = []

        for item in items[:limit]:
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text.strip() if title_el is not None and title_el.text else "No title"
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
            source = (
                source_el.text.strip()
                if source_el is not None and source_el.text
                else "Google News"
            )

            results.append(
                {
                    "title": title,
                    "snippet": f"Published: {pub_date} | Source: {source}",
                    "link": link,
                    "source": source,
                    "pub_date": pub_date,
                }
            )

        return results
    except Exception as exc:
        logger.warning("Google News RSS failed for %r: %s", clean_query, exc)
        return []


def search_market_news(query: str, ticker: str = "", limit: int = 8) -> str:
    """Retrieve synthesized real-time market and corporate news across search engines.

    100% Free, credential-less search fallback combining Google News RSS and DuckDuckGo.
    """
    search_q = query.strip()
    if ticker and ticker.upper() not in search_q.upper():
        clean_tick = ticker.replace(".NS", "").replace(".BO", "")
        search_q = f"{clean_tick} {search_q}".strip()

    if not search_q:
        return "No search query provided for market news."

    # Tier 1: Google News RSS
    g_articles = search_google_news_rss(search_q, limit=limit)
    # Tier 2: DuckDuckGo HTML
    ddg_articles = search_duckduckgo(search_q, limit=limit)

    combined = []
    seen_titles = set()

    for item in g_articles + ddg_articles:
        norm_title = re.sub(r"[^\w\s]", "", item["title"]).lower()[:40]
        if norm_title and norm_title not in seen_titles:
            seen_titles.add(norm_title)
            combined.append(item)
            if len(combined) >= limit:
                break

    if not combined:
        return f"<No news found via public search engines for query: {search_q}>"

    as_of = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"### Real-Time Web & News Search Results for '{search_q}' (as of {as_of}):\n"]

    for i, art in enumerate(combined, start=1):
        lines.append(f"{i}. **{art['title']}**")
        if art.get("snippet"):
            lines.append(f"   - {art['snippet']}")
        if art.get("link"):
            lines.append(f"   - URL: {art['link']}")
        lines.append("")

    return "\n".join(lines).strip()


def search_x_sentiment(query: str, ticker: str = "", limit: int = 8) -> str:
    """Retrieve 100% free X / Twitter financial chatter and sentiment via web site-search."""
    clean_tick = ticker.replace(".NS", "").replace(".BO", "").strip() if ticker else ""
    target = query.strip() or clean_tick
    if not target:
        return "No ticker or company query provided for X / Twitter sentiment."

    # Build free site-search query for X/Twitter
    if clean_tick:
        search_query = (
            f'site:x.com OR site:twitter.com ("${clean_tick}" OR "{target}") stock market'
        )
    else:
        search_query = f'site:x.com OR site:twitter.com "{target}" stock market'

    results = search_duckduckgo(search_query, limit=limit)
    if not results:
        return f"<No recent X / Twitter chatter found for {target}>"

    lines = [f"### X / Twitter Financial Chatter & Retail Sentiment for '{target}':\n"]
    for i, res in enumerate(results, start=1):
        clean_title = res["title"].replace("on X:", ":").replace("on Twitter:", ":")
        lines.append(f"{i}. **{clean_title}**")
        if res.get("snippet"):
            lines.append(f'   "{res["snippet"]}"')
        lines.append("")

    return "\n".join(lines).strip()
