"""Technical analysis consensus scoring module."""

from __future__ import annotations

import contextlib
import logging

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

logger = logging.getLogger(__name__)


def compute_technical_consensus(symbol: str, curr_date: str = "") -> str:
    """Compute an institutional multi-indicator technical consensus verdict."""
    canonical = normalize_symbol(symbol)
    try:
        df = load_ohlcv(canonical, curr_date, fill_gaps=False)
    except Exception as exc:
        return f"Could not load market data for technical consensus on {symbol}: {exc}"

    if df is None or df.empty or len(df) < 20:
        return f"Insufficient price history ({len(df) if df is not None else 0} bars) to calculate technical consensus for {symbol}."

    s = wrap(df)
    # Ensure key indicators are pre-calculated
    calc_cols = [
        "close_10_ema",
        "close_20_ema",
        "close_50_sma",
        "close_100_sma",
        "close_200_sma",
        "rsi",
        "macd",
        "macds",
        "macdh",
        "boll",
        "boll_ub",
        "boll_lb",
        "atr",
    ]
    for col in calc_cols:
        with contextlib.suppress(Exception):
            s[col]

    latest = s.iloc[-1]
    c = float(latest["close"])

    # 1. Moving Average Signals (Trend)
    ma_signals: list[tuple[str, str, str]] = []
    for period, col in [
        (10, "close_10_ema"),
        (20, "close_20_ema"),
        (50, "close_50_sma"),
        (100, "close_100_sma"),
        (200, "close_200_sma"),
    ]:
        if col in latest and not pd.isna(latest[col]):
            val = float(latest[col])
            action = "BUY" if c > val else "SELL"
            ma_signals.append(
                (f"{period} {'EMA' if 'ema' in col else 'SMA'}", f"{val:,.2f}", action)
            )

    # Golden Cross (50 SMA vs 200 SMA)
    if "close_50_sma" in latest and "close_200_sma" in latest:
        sma50 = float(latest["close_50_sma"])
        sma200 = float(latest["close_200_sma"])
        if not pd.isna(sma50) and not pd.isna(sma200):
            action = "BUY (Golden Cross)" if sma50 > sma200 else "SELL (Death Cross)"
            ma_signals.append(("50/200 Cross", f"Diff: {sma50 - sma200:+.2f}", action))

    # 2. Oscillator & Momentum Signals
    osc_signals: list[tuple[str, str, str]] = []
    if "rsi" in latest and not pd.isna(latest["rsi"]):
        rsi = float(latest["rsi"])
        action = "BUY (Oversold)" if rsi < 30 else ("SELL (Overbought)" if rsi > 70 else "NEUTRAL")
        osc_signals.append(("RSI (14)", f"{rsi:.1f}", action))

    if "macd" in latest and "macds" in latest:
        macd_val = float(latest["macd"])
        macds_val = float(latest["macds"])
        if not pd.isna(macd_val) and not pd.isna(macds_val):
            action = "BUY (Bullish)" if macd_val > macds_val else "SELL (Bearish)"
            osc_signals.append(("MACD (12, 26, 9)", f"{macd_val:.2f} vs {macds_val:.2f}", action))

    if "macdh" in latest and not pd.isna(latest["macdh"]):
        macdh = float(latest["macdh"])
        action = "BUY (Expanding)" if macdh > 0 else "SELL (Contracting)"
        osc_signals.append(("MACD Histogram", f"{macdh:+.2f}", action))

    if "boll_lb" in latest and "boll_ub" in latest:
        lb = float(latest["boll_lb"])
        ub = float(latest["boll_ub"])
        if not pd.isna(lb) and not pd.isna(ub):
            action = (
                "BUY (Oversold Bounce)"
                if c < lb
                else ("SELL (Upper Band Break)" if c > ub else "NEUTRAL")
            )
            osc_signals.append(("Bollinger Bands (20,2)", f"[{lb:,.1f} - {ub:,.1f}]", action))

    all_signals = ma_signals + osc_signals
    buys = sum(1 for _, _, act in all_signals if "BUY" in act)
    sells = sum(1 for _, _, act in all_signals if "SELL" in act)
    neutrals = sum(1 for _, _, act in all_signals if "NEUTRAL" in act)
    total = len(all_signals)

    if total == 0:
        return f"Unable to compute technical signals for {canonical}."

    buy_ratio = buys / total
    sell_ratio = sells / total

    if buy_ratio >= 0.70:
        verdict = "STRONG BUY"
    elif buy_ratio >= 0.55:
        verdict = "BUY"
    elif sell_ratio >= 0.70:
        verdict = "STRONG SELL"
    elif sell_ratio >= 0.55:
        verdict = "SELL"
    else:
        verdict = "NEUTRAL"

    ma_buys = sum(1 for _, _, act in ma_signals if "BUY" in act)
    ma_sells = sum(1 for _, _, act in ma_signals if "SELL" in act)
    osc_buys = sum(1 for _, _, act in osc_signals if "BUY" in act)
    osc_sells = sum(1 for _, _, act in osc_signals if "SELL" in act)
    osc_neutrals = sum(1 for _, _, act in osc_signals if "NEUTRAL" in act)

    lines = [
        f"### Technical Consensus Matrix for {canonical} (Latest Close: {c:,.2f}):",
        f"- **Overall Consensus Verdict**: **{verdict}** ({buys} Buy, {neutrals} Neutral, {sells} Sell out of {total} indicators)",
        f"- **Moving Averages Summary**: {ma_buys} Buy vs {ma_sells} Sell",
        f"- **Oscillators Summary**: {osc_buys} Buy, {osc_neutrals} Neutral, {osc_sells} Sell",
        "",
        "| Indicator | Reading / Level | Signal |",
        "| --- | --- | --- |",
    ]

    for ind, val, act in all_signals:
        lines.append(f"| {ind} | {val} | **{act}** |")

    return "\n".join(lines)
