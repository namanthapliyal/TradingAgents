"""Indian ETF (Exchange Traded Fund) data vendor."""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.symbols import normalize_symbol

logger = logging.getLogger(__name__)

# Common Indian ETF Benchmark mappings
ETF_BENCHMARK_MAP = {
    "NIFTYBEES": ("Nifty 50 Index", "Large Cap Equity"),
    "BANKBEES": ("Nifty Bank Index", "Banking Sector Equity"),
    "GOLDBEES": ("Domestic Gold Price", "Commodity / Precious Metals"),
    "SILVERBEES": ("Domestic Silver Price", "Commodity / Precious Metals"),
    "ITBEES": ("Nifty IT Index", "Information Technology Equity"),
    "JUNIORBEES": ("Nifty Next 50 Index", "Mid/Large Cap Equity"),
    "CPSEETF": ("Nifty CPSE Index", "Public Sector Undertakings"),
    "MON100": ("Nasdaq 100 Index", "International / US Technology"),
    "PHARMABEES": ("Nifty Pharma Index", "Healthcare Equity"),
    "AUTOBEES": ("Nifty Auto Index", "Automobile Equity"),
}


def get_etf_details(ticker: str) -> dict[str, Any]:
    """Retrieve key metrics for an Indian exchange-traded fund."""
    clean = ticker.upper().replace(".NS", "").replace(".BO", "").strip()
    canonical = normalize_symbol(ticker)
    if not canonical.endswith(".NS") and not canonical.endswith(".BO"):
        canonical = f"{clean}.NS"

    try:
        t = yf.Ticker(canonical)
        info = t.info or {}
        if not info:
            raise NoMarketDataError(ticker, f"No market data found for ETF {ticker}")

        name = info.get("longName") or info.get("shortName") or clean
        current_price = (
            info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
        )
        high52 = info.get("fiftyTwoWeekHigh")
        low52 = info.get("fiftyTwoWeekLow")
        volume = info.get("volume") or info.get("regularMarketVolume")
        avg_volume = info.get("averageVolume")

        benchmark, asset_class = ETF_BENCHMARK_MAP.get(
            clean, ("Broad Market Index", "Exchange Traded Fund")
        )

        return {
            "ticker": clean,
            "canonical_symbol": canonical,
            "name": name,
            "current_price": current_price,
            "52_week_high": high52,
            "52_week_low": low52,
            "volume": volume,
            "average_volume": avg_volume,
            "underlying_benchmark": benchmark,
            "asset_class": asset_class,
            "exchange": "NSE / BSE India",
        }
    except Exception as exc:
        if isinstance(exc, NoMarketDataError):
            raise
        raise VendorUnavailableError(f"Failed to fetch ETF details for {ticker}: {exc}") from exc


def get_etf_report(ticker: str) -> str:
    """Formatted report for LangGraph analyst agents."""
    details = get_etf_details(ticker)

    lines = [
        f"# Indian ETF Analysis: {details['name']} ({details['ticker']})",
        f"- **Exchange Symbol:** `{details['canonical_symbol']}`",
        f"- **Asset Class:** {details['asset_class']}",
        f"- **Underlying Benchmark:** {details['underlying_benchmark']}",
        f"- **Current Market Price:** ₹{details['current_price']:,.2f}"
        if details["current_price"]
        else "- **Current Price:** N/A",
        f"- **52-Week Range:** ₹{details['52_week_low']} — ₹{details['52_week_high']}",
        f"- **Trading Volume:** {details['volume']:,}"
        if details["volume"]
        else "- **Trading Volume:** N/A",
        f"- **30-Day Avg Volume:** {details['average_volume']:,}"
        if details["average_volume"]
        else "- **Avg Volume:** N/A",
        "",
        "### Key Considerations for ETF Evaluation:",
        "- **Tracking Error & Benchmark Correlation**: High liquidity minimizes tracking error against the underlying index.",
        "- **Intraday Liquidity**: Check current volume vs average volume before executing large order tranches.",
    ]

    return "\n".join(lines)
