"""Peer comparison vendor module for Indian and Global equities."""

from __future__ import annotations

import contextlib
import logging

import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.symbols import normalize_symbol

logger = logging.getLogger(__name__)


def get_peer_comparison_indian(clean_ticker: str) -> str | None:
    """Fetch peer comparison table from screener.in for an Indian company."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(
            f"https://www.screener.in/company/{clean_ticker}/", headers=headers, timeout=10
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.content, "html.parser")
        info_el = soup.find(id="company-info")
        if not info_el or not info_el.get("data-warehouse-id"):
            return None

        wh_id = info_el.get("data-warehouse-id")
        pr = requests.get(
            f"https://www.screener.in/api/company/{wh_id}/peers/", headers=headers, timeout=10
        )
        if pr.status_code != 200:
            return None

        psoup = BeautifulSoup(pr.content, "html.parser")
        table = psoup.find("table", class_="data-table")
        if not table:
            return None

        rows = table.find_all("tr")
        if len(rows) < 2:
            return None

        raw_headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        # Map or clean header labels
        col_names = []
        for h in raw_headers[1:]:
            cleaned = (
                h.replace("Rs.Cr.", "(₹ Cr)").replace("Rs.", "(₹)").replace("%", "(%)").strip()
            )
            col_names.append(cleaned)

        md_lines = [
            f"### Sector Peer Comparison for {clean_ticker} (via Screener.in):",
            "",
            "| " + " | ".join(col_names) + " |",
            "| " + " | ".join(["---"] * len(col_names)) + " |",
        ]

        for row in rows[1:9]:  # Top 8 direct industry peers
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) >= len(raw_headers):
                md_lines.append("| " + " | ".join(cells[1:]) + " |")

        return "\n".join(md_lines)

    except Exception as exc:
        logger.debug("Failed fetching Screener peer table for %s: %s", clean_ticker, exc)
        return None


def get_peer_comparison_global(ticker: str) -> str:
    """Fetch industry peer comparison using Yahoo Finance for Global/US stocks."""
    import yfinance as yf

    canonical = normalize_symbol(ticker)
    try:
        t = yf.Ticker(canonical)
        info = t.info or {}
        industry_key = info.get("industryKey")
        sector_name = info.get("sector") or "Industry"

        symbols = [canonical]
        if industry_key and hasattr(yf, "Industry"):
            with contextlib.suppress(Exception):
                ind = yf.Industry(industry_key)
                top = getattr(ind, "top_companies", None)
                if top is not None and not top.empty:
                    top_syms = [
                        s.strip().upper() for s in top.index if s.strip().upper() != canonical
                    ]
                    symbols.extend(top_syms[:4])

        md_lines = [
            f"### Industry Peer Comparison for {canonical} ({sector_name}):",
            "",
            "| Symbol | Company Name | Price | Market Cap | Trailing P/E | Forward P/E | Div Yield |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]

        for sym in symbols:
            try:
                pt = yf.Ticker(sym)
                pinfo = pt.info or {}
                name = pinfo.get("shortName") or sym
                price = (
                    pinfo.get("currentPrice")
                    or pinfo.get("regularMarketPrice")
                    or getattr(pt.fast_info, "last_price", None)
                    or "N/A"
                )
                price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else str(price)

                mcap = getattr(pt.fast_info, "market_cap", None) or pinfo.get("marketCap")
                mcap_str = f"${mcap / 1e9:.2f}B" if mcap else "N/A"

                pe = pinfo.get("trailingPE")
                pe_str = f"{pe:.2f}" if pe else "N/A"

                fpe = pinfo.get("forwardPE")
                fpe_str = f"{fpe:.2f}" if fpe else "N/A"

                dy = pinfo.get("dividendYield")
                dy_str = f"{dy * 100:.2f}%" if dy else "0.0%"

                bold = "**" if sym == canonical else ""
                md_lines.append(
                    f"| {bold}{sym}{bold} | {name} | {price_str} | {mcap_str} | {pe_str} | {fpe_str} | {dy_str} |"
                )
            except Exception:
                continue

        return "\n".join(md_lines)

    except Exception as exc:
        return f"Could not retrieve peer comparison for {ticker}: {exc}"


def get_peer_comparison(ticker: str) -> str:
    """Retrieve sector and industry peer comparisons with key financial metrics."""
    clean = ticker.upper().replace(".NS", "").replace(".BO", "").strip()

    # Try Indian Screener peer table first
    indian_res = get_peer_comparison_indian(clean)
    if indian_res:
        return indian_res

    # Fall back to Global / Yahoo Finance industry peers
    return get_peer_comparison_global(ticker)
