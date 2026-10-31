"""Analyst consensus and target price vendor module."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from tradingagents.dataflows.symbols import normalize_symbol

logger = logging.getLogger(__name__)


def _fetch_finnhub_consensus(clean_ticker: str, api_key: str) -> dict[str, Any] | None:
    """Fetch analyst recommendations and price targets from Finnhub API."""
    import requests

    headers = {"X-Finnhub-Token": api_key}
    res: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        # 1. Price Target
        target_r = requests.get(
            f"https://finnhub.io/api/v1/stock/price-target?symbol={clean_ticker}",
            headers=headers,
            timeout=8,
        )
        if target_r.status_code == 200:
            res["target"] = target_r.json()

        # 2. Recommendations
        rec_r = requests.get(
            f"https://finnhub.io/api/v1/stock/recommendation?symbol={clean_ticker}",
            headers=headers,
            timeout=8,
        )
        if rec_r.status_code == 200:
            res["recommendations"] = rec_r.json()

    return res if res else None


def get_analyst_consensus(ticker: str) -> str:
    """Retrieve Wall Street and institutional broker consensus, price targets, and ratings."""
    import yfinance as yf

    raw_clean = ticker.upper().replace(".NS", "").replace(".BO", "").strip()

    # 1. Check if Finnhub API Key is present for US/Global assets
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if finnhub_key:
        fh_data = _fetch_finnhub_consensus(raw_clean, finnhub_key)
        if fh_data and "target" in fh_data:
            target = fh_data["target"]
            t_mean = target.get("targetMean")
            t_high = target.get("targetHigh")
            t_low = target.get("targetLow")
            recs = fh_data.get("recommendations", [])

            lines = [
                f"### Institutional Analyst Consensus & Target Prices for {raw_clean} (Finnhub):",
                f"- **Target Price Mean**: ${t_mean} (High: ${t_high} | Low: ${t_low})",
            ]
            if recs:
                latest = recs[0]
                lines.append(
                    f"- **Latest Ratings Distribution ({latest.get('period')})**: "
                    f"Strong Buy: {latest.get('strongBuy')}, Buy: {latest.get('buy')}, "
                    f"Hold: {latest.get('hold')}, Sell: {latest.get('sell')}, Strong Sell: {latest.get('strongSell')}"
                )
            return "\n".join(lines)

    # 2. Fall back to Yahoo Finance (supports US and Indian tickers with .NS / .BO)
    canonical = normalize_symbol(ticker)
    candidates = [canonical]
    if "." not in canonical and not canonical.startswith("^"):
        candidates.extend([f"{canonical}.NS", f"{canonical}.BO"])

    info = None
    target_ticker = canonical
    t = None

    for sym in candidates:
        try:
            cand_t = yf.Ticker(sym)
            cand_info = cand_t.info or {}
            if "targetMeanPrice" in cand_info or "recommendationKey" in cand_info:
                info = cand_info
                target_ticker = sym
                t = cand_t
                break
        except Exception:
            continue

    if not info or not t:
        return f"No institutional analyst consensus or target price coverage found for {ticker}."

    curr_price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or getattr(t.fast_info, "last_price", None)
    )
    target_low = info.get("targetLowPrice")
    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    target_median = info.get("targetMedianPrice")
    rec_key = (info.get("recommendationKey") or "N/A").replace("_", " ").upper()
    num_opinions = info.get("numberOfAnalystOpinions") or "N/A"

    currency = "₹" if (".NS" in target_ticker or ".BO" in target_ticker) else "$"

    upside_str = "N/A"
    if curr_price and target_mean and isinstance(curr_price, (int, float)):
        upside = ((target_mean - curr_price) / curr_price) * 100
        upside_str = f"{upside:+.1f}%"

    price_str = (
        f"{currency}{curr_price:,.2f}" if isinstance(curr_price, (int, float)) else str(curr_price)
    )
    t_mean_str = (
        f"{currency}{target_mean:,.2f}"
        if isinstance(target_mean, (int, float))
        else str(target_mean)
    )
    t_low_str = (
        f"{currency}{target_low:,.2f}" if isinstance(target_low, (int, float)) else str(target_low)
    )
    t_high_str = (
        f"{currency}{target_high:,.2f}"
        if isinstance(target_high, (int, float))
        else str(target_high)
    )
    t_med_str = (
        f"{currency}{target_median:,.2f}"
        if isinstance(target_median, (int, float))
        else str(target_median)
    )

    lines = [
        f"### Institutional Analyst Consensus & Price Targets for {target_ticker}:",
        f"- **Consensus Verdict**: **{rec_key}**",
        f"- **Analyst Coverage**: {num_opinions} institutional broker research desks",
        f"- **Current Market Price**: {price_str}",
        f"- **Consensus Target Mean**: {t_mean_str} (**{upside_str}** implied potential)",
        f"- **Target Price Range**: Low: {t_low_str} | Median: {t_med_str} | High: {t_high_str}",
    ]

    recs = getattr(t, "recommendations", None)
    if recs is not None and hasattr(recs, "iterrows") and not recs.empty:
        lines.append("")
        lines.append("**Institutional Ratings Distribution Trends (Recent Months)**:")
        lines.append("| Period | Strong Buy | Buy | Hold | Underperform / Sell | Strong Sell |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for idx, row in recs.head(4).iterrows():
            period = row.get("period", str(idx))
            sb = row.get("strongBuy", 0)
            b = row.get("buy", 0)
            h = row.get("hold", 0)
            s = row.get("sell", 0)
            ss = row.get("strongSell", 0)
            lines.append(f"| {period} | {sb} | {b} | {h} | {s} | {ss} |")

    return "\n".join(lines)
