"""Indian ETF (Exchange Traded Fund) data vendor."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from typing import Any

import yfinance as yf

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.symbols import normalize_symbol

logger = logging.getLogger(__name__)

# Common Indian ETF Benchmark mappings (used as offline fallback)
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

# In-memory cache for live NSE ETF directory (refreshed every 15 minutes)
_NSE_ETF_CACHE: list[dict[str, Any]] = []
_NSE_ETF_CACHE_TIME: float = 0.0
_NSE_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 900.0  # 15 minutes


def fetch_nse_etf_directory(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch live directory of all Indian ETFs from NSE India outer source.

    Returns real-time traded volume, turnover (trdVal), LTP, day change %, and underlying assets.
    Results are cached in memory for 15 minutes to guarantee fast sub-second responsiveness.
    """
    global _NSE_ETF_CACHE, _NSE_ETF_CACHE_TIME
    now = time.time()
    with _NSE_CACHE_LOCK:
        if not force_refresh and _NSE_ETF_CACHE and (now - _NSE_ETF_CACHE_TIME < _CACHE_TTL_SECONDS):
            return _NSE_ETF_CACHE

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    url = "https://www.nseindia.com/api/etf"

    # 1. Attempt direct request with standard headers
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", [])
            if items:
                with _NSE_CACHE_LOCK:
                    _NSE_ETF_CACHE = items
                    _NSE_ETF_CACHE_TIME = now
                return items
    except Exception as exc:
        logger.debug("Direct NSE ETF fetch notice: %s. Attempting session fallback...", exc)
        # 2. Fallback to requests Session with home page handshake
        try:
            import requests

            s = requests.Session()
            s.headers.update(headers)
            s.get("https://www.nseindia.com", timeout=3)
            r = s.get(url, timeout=4)
            if r.status_code == 200:
                items = r.json().get("data", [])
                if items:
                    with _NSE_CACHE_LOCK:
                        _NSE_ETF_CACHE = items
                        _NSE_ETF_CACHE_TIME = now
                    return items
        except Exception as s_exc:
            logger.warning("Could not fetch ETF directory from NSE India: %s", s_exc)

    with _NSE_CACHE_LOCK:
        return _NSE_ETF_CACHE or []


def get_etf_cluster(symbol: str, asset_text: str = "") -> str:
    """Classify ETF into asset cluster based on symbol and underlying asset description."""
    s = symbol.upper()
    a = (asset_text or "").lower()

    if "silver" in a or "silver" in s or "silv" in s:
        return "silver"
    if "gold" in a or "gold" in s:
        return "gold"
    if any(k in a for k in ("nasdaq", "s&p 500", "sp500", "hang seng", "us top", "nyse fang")) or any(
        k in s for k in ("mon100", "fang", "masptop50", "mom100")
    ):
        return "international"
    if any(k in a for k in ("nifty bank", "bank nifty", "psu bank", "private bank")) or any(
        k in s for k in ("bankbees", "psubnk", "bankietf", "kotakbk")
    ):
        return "banking"
    if any(k in a for k in ("nifty it", "infotech", "technology", "information technology")) or any(
        k in s for k in ("itbees", "itietf", "tech")
    ):
        return "it"
    if any(k in a for k in ("nifty auto", "automobile")) or any(
        k in s for k in ("autobees", "autoi", "evindia", "growwev")
    ):
        return "auto"
    if any(k in a for k in ("pharma", "healthcare")) or any(
        k in s for k in ("pharmabees", "healthietf", "healthy", "pharmai")
    ):
        return "pharma"
    if any(k in a for k in ("cpse", "bharat 22", "psu")) or any(
        k in s for k in ("cpseetf", "icicib22")
    ):
        return "psu_cpse"
    if any(k in a for k in ("nifty next 50", "next 50", "junior")) or any(
        k in s for k in ("juniorbees", "nn50")
    ):
        return "nifty_next_50"
    if any(k in a for k in ("nifty 50", "nifty50", "nifty")) or "niftybees" in s:
        return "nifty_50"
    if any(k in a for k in ("sensex", "bse 30", "s&p bse sensex")) or "sensex" in s:
        return "sensex"
    if "midcap" in a or "mid150" in s or "mid 150" in a:
        return "midcap"
    if "smallcap" in a or "small250" in s or "small 250" in a:
        return "smallcap"
    if any(k in a for k in ("liquid", "overnight", "gilt", "rate", "debt", "bond", "t-bill")):
        return "debt_liquid"

    # Fallback keyword extraction for thematic or new funds
    words = re.findall(r"[a-zA-Z]{3,}", a)
    stopwords = {
        "index",
        "fund",
        "etf",
        "total",
        "return",
        "tri",
        "exchange",
        "traded",
        "based",
        "price",
        "daily",
        "domestic",
    }
    meaningful = [w for w in words if w not in stopwords]
    return meaningful[0] if meaningful else "general"


def find_dynamic_etf_peers(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Dynamically discover category peer ETFs from outer NSE market feed.

    Ranks peer alternatives by live turnover (traded value in ₹ Cr) descending.
    Ensures newly listed ETFs and volume shifts are reflected without hardcoded maps.
    """
    clean = ticker.upper().replace(".NS", "").replace(".BO", "").strip()
    all_etfs = fetch_nse_etf_directory()
    if not all_etfs:
        return []

    # Locate queried ETF to determine cluster
    target_item = next((x for x in all_etfs if str(x.get("symbol", "")).upper() == clean), None)
    target_asset = target_item.get("assets", "") if target_item else ""
    target_cluster = get_etf_cluster(clean, target_asset)

    candidates: list[dict[str, Any]] = []
    for item in all_etfs:
        sym = str(item.get("symbol", "")).strip().upper()
        if not sym or sym == clean:
            continue
        item_asset = str(item.get("assets", ""))
        cluster = get_etf_cluster(sym, item_asset)
        if cluster == target_cluster:
            try:
                trd_val = float(item.get("trdVal") or 0.0)
            except (ValueError, TypeError):
                trd_val = 0.0
            try:
                ltp = float(item.get("ltP") or 0.0)
            except (ValueError, TypeError):
                ltp = 0.0
            try:
                per = float(item.get("per") or 0.0)
            except (ValueError, TypeError):
                per = 0.0

            candidates.append({
                "ticker": sym,
                "canonical_symbol": f"{sym}.NS",
                "name": item_asset or sym,
                "price": ltp,
                "turnover_cr": round(trd_val / 10_000_000.0, 2),
                "day_change_pct": round(per, 2),
            })

    # Rank dynamically by liquidity / turnover descending
    candidates.sort(key=lambda x: x["turnover_cr"], reverse=True)
    return candidates[:limit]


def get_etf_details(ticker: str) -> dict[str, Any]:
    """Retrieve comprehensive technical, liquidity, and benchmark metrics for an Indian ETF."""
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

        # Dynamic underlying benchmark & asset class from live NSE directory
        all_etfs = fetch_nse_etf_directory()
        target_item = next(
            (x for x in all_etfs if str(x.get("symbol", "")).upper() == clean), None
        )
        if target_item and target_item.get("assets"):
            benchmark = str(target_item["assets"]).strip()
            cluster = get_etf_cluster(clean, benchmark)
            cluster_display = {
                "gold": "Commodity / Precious Metals",
                "silver": "Commodity / Precious Metals",
                "nifty_50": "Large Cap Equity",
                "banking": "Banking Sector Equity",
                "it": "Information Technology Equity",
                "pharma": "Healthcare Equity",
                "auto": "Automobile Equity",
                "psu_cpse": "Public Sector Undertakings",
                "nifty_next_50": "Mid/Large Cap Equity",
                "international": "International Equity",
                "sensex": "Large Cap Equity (BSE)",
                "midcap": "Mid Cap Equity",
                "smallcap": "Small Cap Equity",
                "debt_liquid": "Debt / Liquid Money Market",
            }.get(cluster, "Exchange Traded Fund")
            asset_class = cluster_display
        else:
            benchmark, asset_class = ETF_BENCHMARK_MAP.get(
                clean, ("Broad Market Index", "Exchange Traded Fund")
            )

        # Intraday price movement
        day_change = info.get("regularMarketChange")
        day_change_percent = info.get("regularMarketChangePercent")
        day_high = info.get("dayHigh") or info.get("regularMarketDayHigh")
        day_low = info.get("dayLow") or info.get("regularMarketDayLow")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

        # Turnover (₹ Cr) & liquidity assessment
        turnover_cr = None
        liquidity_rating = "Moderate Liquidity"
        if volume and current_price:
            turnover_cr = round((volume * current_price) / 10_000_000.0, 2)
            if turnover_cr >= 25.0:
                liquidity_rating = "Tier-1 Institutional (₹25+ Cr/day)"
            elif turnover_cr >= 5.0:
                liquidity_rating = "High Liquidity (₹5+ Cr/day)"
            elif turnover_cr >= 1.0:
                liquidity_rating = "Moderate Liquidity (₹1-5 Cr/day)"
            else:
                liquidity_rating = "Low Liquidity (<₹1 Cr/day)"

        # 50 & 200 Moving Averages
        dma_50 = info.get("fiftyDayAverage")
        dma_200 = info.get("twoHundredDayAverage")
        dma_50_diff = (
            round(((current_price - dma_50) / dma_50) * 100.0, 2)
            if (current_price and dma_50)
            else None
        )
        dma_200_diff = (
            round(((current_price - dma_200) / dma_200) * 100.0, 2)
            if (current_price and dma_200)
            else None
        )

        trend_signal = "Consolidating"
        if current_price and dma_50 and dma_200:
            if current_price >= dma_50 and dma_50 >= dma_200:
                trend_signal = "Bullish Uptrend (Above 50 & 200 DMA)"
            elif current_price >= dma_200:
                trend_signal = "Moderate Bullish (Above 200 DMA)"
            elif current_price < dma_200:
                trend_signal = "Bearish / Correction Phase (Below 200 DMA)"

        # 52-Week range percentage
        range_pct = 50.0
        if high52 and low52 and current_price and high52 > low52:
            range_pct = round(((current_price - low52) / (high52 - low52)) * 100.0, 1)

        # Trailing Historical Returns & 14-day RSI
        returns: dict[str, float | None] = {
            "1W": None,
            "1M": None,
            "3M": None,
            "6M": None,
            "1Y": None,
        }
        rsi_14 = None
        try:
            hist = t.history(period="1y")
            if not hist.empty and "Close" in hist:
                closes = hist["Close"].dropna()
                if len(closes) >= 5:
                    c = float(closes.iloc[-1])
                    if len(closes) >= 5 and float(closes.iloc[-5]) > 0:
                        returns["1W"] = round(
                            ((c - float(closes.iloc[-5])) / float(closes.iloc[-5])) * 100.0, 2
                        )
                    if len(closes) >= 21 and float(closes.iloc[-21]) > 0:
                        returns["1M"] = round(
                            ((c - float(closes.iloc[-21])) / float(closes.iloc[-21])) * 100.0, 2
                        )
                    if len(closes) >= 63 and float(closes.iloc[-63]) > 0:
                        returns["3M"] = round(
                            ((c - float(closes.iloc[-63])) / float(closes.iloc[-63])) * 100.0, 2
                        )
                    if len(closes) >= 126 and float(closes.iloc[-126]) > 0:
                        returns["6M"] = round(
                            ((c - float(closes.iloc[-126])) / float(closes.iloc[-126])) * 100.0, 2
                        )
                    if len(closes) >= 200 and float(closes.iloc[0]) > 0:
                        returns["1Y"] = round(
                            ((c - float(closes.iloc[0])) / float(closes.iloc[0])) * 100.0, 2
                        )

                    # RSI 14
                    if len(closes) >= 15:
                        delta = closes.diff()
                        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
                        last_gain = float(gain.iloc[-1])
                        last_loss = float(loss.iloc[-1])
                        if last_loss > 0:
                            rs = last_gain / last_loss
                            rsi_14 = round(100.0 - (100.0 / (1.0 + rs)), 1)
                        elif last_gain > 0:
                            rsi_14 = 100.0
                        else:
                            rsi_14 = 50.0
        except Exception as hist_err:
            logger.debug("Could not compute historical ETF returns for %s: %s", ticker, hist_err)

        peers = find_dynamic_etf_peers(clean, limit=5)

        return {
            "ticker": clean,
            "canonical_symbol": canonical,
            "name": name,
            "current_price": current_price,
            "day_change": day_change,
            "day_change_percent": day_change_percent,
            "day_high": day_high,
            "day_low": day_low,
            "prev_close": prev_close,
            "52_week_high": high52,
            "52_week_low": low52,
            "52_week_range_pct": range_pct,
            "volume": volume,
            "average_volume": avg_volume,
            "turnover_cr": turnover_cr,
            "liquidity_rating": liquidity_rating,
            "dma_50": dma_50,
            "dma_200": dma_200,
            "dma_50_diff": dma_50_diff,
            "dma_200_diff": dma_200_diff,
            "trend_signal": trend_signal,
            "rsi_14": rsi_14,
            "returns": returns,
            "underlying_benchmark": benchmark,
            "asset_class": asset_class,
            "peers": peers,
            "exchange": "NSE / BSE India",
        }
    except Exception as exc:
        if isinstance(exc, NoMarketDataError):
            raise
        raise VendorUnavailableError(f"Failed to fetch ETF details for {ticker}: {exc}") from exc


def get_etf_report(ticker: str) -> str:
    """Formatted report for LangGraph analyst agents."""
    details = get_etf_details(ticker)

    price_str = f"₹{details['current_price']:,.2f}" if details["current_price"] else "N/A"
    change_str = (
        f"{'+' if (details.get('day_change_percent') or 0) >= 0 else ''}"
        f"{(details.get('day_change_percent') or 0):.2f}%"
        if details.get("day_change_percent") is not None
        else "N/A"
    )
    turnover_str = (
        f"₹{details['turnover_cr']:,.2f} Cr" if details.get("turnover_cr") else "N/A"
    )

    rets = details.get("returns", {})

    lines = [
        f"# Indian ETF Analysis: {details['name']} ({details['ticker']})",
        f"- **Exchange Symbol:** `{details['canonical_symbol']}`",
        f"- **Asset Class:** {details['asset_class']}",
        f"- **Underlying Benchmark:** {details['underlying_benchmark']}",
        f"- **Current Market Price:** {price_str} ({change_str})",
        f"- **Today's Range:** ₹{details.get('day_low', 'N/A')} — ₹{details.get('day_high', 'N/A')}",
        f"- **52-Week Range:** ₹{details['52_week_low']} — ₹{details['52_week_high']} ({details.get('52_week_range_pct', 50)}% in channel)",
        f"- **Trading Volume:** {details['volume']:,}" if details["volume"] else "- **Trading Volume:** N/A",
        f"- **Daily Turnover:** {turnover_str} ({details.get('liquidity_rating', 'Moderate')})",
        f"- **30-Day Avg Volume:** {details['average_volume']:,}" if details["average_volume"] else "- **Avg Volume:** N/A",
        "",
        "### Technical Momentum & Trend Status:",
        f"- **50-Day SMA:** ₹{details.get('dma_50', 'N/A')} ({details.get('dma_50_diff', 'N/A')}% vs price)",
        f"- **200-Day SMA:** ₹{details.get('dma_200', 'N/A')} ({details.get('dma_200_diff', 'N/A')}% vs price)",
        f"- **14-Day RSI:** {details.get('rsi_14', 'N/A')}",
        f"- **Trend Stance:** {details.get('trend_signal', 'Neutral')}",
        "",
        "### Trailing Historical Returns:",
        f"- **1-Week:** {rets.get('1W', 'N/A')}%" if rets.get("1W") is not None else "- **1-Week:** N/A",
        f"- **1-Month:** {rets.get('1M', 'N/A')}%" if rets.get("1M") is not None else "- **1-Month:** N/A",
        f"- **3-Month:** {rets.get('3M', 'N/A')}%" if rets.get("3M") is not None else "- **3-Month:** N/A",
        f"- **6-Month:** {rets.get('6M', 'N/A')}%" if rets.get("6M") is not None else "- **6-Month:** N/A",
        f"- **1-Year:** {rets.get('1Y', 'N/A')}%" if rets.get("1Y") is not None else "- **1-Year:** N/A",
    ]

    peers = details.get("peers", [])
    if peers:
        peer_lines = []
        for p in peers:
            if isinstance(p, dict):
                p_sym = p.get("ticker", "")
                p_price = f"₹{p['price']:,.2f}" if p.get("price") else "N/A"
                p_turn = (
                    f"Turnover: ₹{p['turnover_cr']:,.2f} Cr" if p.get("turnover_cr") else ""
                )
                p_chg = (
                    f"({p['day_change_pct']:+.2f}%)"
                    if p.get("day_change_pct") is not None
                    else ""
                )
                peer_desc = " | ".join(filter(bool, [p_price, p_chg, p_turn]))
                peer_lines.append(f"- **{p_sym}**: {peer_desc}")
            else:
                peer_lines.append(f"- **{p}**")
        lines.extend([
            "",
            "### Category Peer Alternatives (Ranked by Live Market Liquidity):",
            *peer_lines,
        ])

    lines.extend([
        "",
        "### Key Considerations for ETF Evaluation:",
        "- **Tracking Error & Benchmark Correlation**: High liquidity minimizes tracking error against the underlying index.",
        "- **Intraday Liquidity**: Check turnover and bid-ask spread before executing large orders.",
    ])

    return "\n".join(lines)

