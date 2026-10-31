"""Macroeconomic Regime & Sector Transmission Snapshot module.

Provides a unified, 100% free multi-asset macro dashboard (US 10Y Yields,
US Dollar Index DXY, LME/Commodities, Volatility) via yfinance to evaluate
macro headwinds and tailwinds for cyclical, export, and commodity equities.
"""

from __future__ import annotations

import logging
import warnings
from datetime import UTC, datetime

import yfinance as yf

logger = logging.getLogger(__name__)

# Suppress pandas deprecation warnings emitted by yfinance internal code
warnings.filterwarnings("ignore", category=UserWarning)

BENCHMARK_TICKERS: dict[str, dict[str, str]] = {
    "^TNX": {
        "name": "US 10-Year Treasury Yield",
        "category": "Rates & Liquidity",
        "unit": "%",
    },
    "DX-Y.NYB": {
        "name": "US Dollar Index (DXY)",
        "category": "Currencies",
        "unit": "Index",
    },
    "SI=F": {
        "name": "Silver Futures (COMEX)",
        "category": "Precious/Industrial Metals",
        "unit": "$/oz",
    },
    "GC=F": {
        "name": "Gold Futures (COMEX)",
        "category": "Precious Metals",
        "unit": "$/oz",
    },
    "HG=F": {
        "name": "Copper Futures (COMEX)",
        "category": "Industrial Metals",
        "unit": "$/lb",
    },
    "BZ=F": {
        "name": "Brent Crude Oil",
        "category": "Energy",
        "unit": "$/bbl",
    },
    "^VIX": {
        "name": "CBOE Volatility Index (VIX)",
        "category": "Market Risk & Volatility",
        "unit": "Index",
    },
}


def _classify_impact(sym: str, change_pct: float, current_val: float, sector: str) -> str:
    """Classify the macro indicator as HEADWIND, TAILWIND, or NEUTRAL for a given sector."""
    sec = sector.lower() if sector else ""
    is_metals = any(
        k in sec for k in ("metal", "mining", "basic material", "steel", "zinc", "copper")
    )
    is_power = any(k in sec for k in ("power", "utilit", "energy", "renewab"))
    is_tech = any(k in sec for k in ("tech", "software", "it ", "information"))
    is_banking = any(k in sec for k in ("bank", "financ", "nbfc"))

    if sym == "^TNX":  # US 10Y Yield
        if current_val > 4.5 or change_pct > 3.0:
            if is_banking:
                return "🟢 TAILWIND (Higher yield spread expands net interest margins)"
            if is_tech or is_metals or is_power:
                return "🔴 HEADWIND (Elevated cost of capital & valuation discount)"
            return "🔴 HEADWIND (Higher global risk-free rate)"
        elif change_pct < -3.0:
            return "🟢 TAILWIND (Easing global financial conditions)"
        return "⚪ NEUTRAL"

    if sym == "DX-Y.NYB":  # US Dollar Index
        if change_pct > 1.5 or current_val > 103.0:
            if is_metals:
                return "🔴 HEADWIND (Strong dollar dampens LME metal prices globally)"
            if is_tech:
                return "🟢 TAILWIND (USD appreciation expands Indian IT margins)"
            return "🔴 HEADWIND (EM capital outflow pressure)"
        elif change_pct < -1.5:
            if is_metals:
                return "🟢 TAILWIND (Weaker dollar stimulates global commodity demand)"
            return "🟢 TAILWIND (EM capital inflow supportive)"
        return "⚪ NEUTRAL"

    if sym in ("SI=F", "HG=F", "GC=F"):  # Metals
        if is_metals:
            if change_pct > 2.0:
                return "🟢 TAILWIND (Higher realization prices & expanding margins)"
            elif change_pct < -2.0:
                return "🔴 HEADWIND (Softening realization prices compress operating profit)"
        return "⚪ NEUTRAL"

    if sym == "BZ=F":  # Crude Oil
        if change_pct > 5.0 or current_val > 90.0:
            if is_metals or is_power:
                return "🔴 HEADWIND (Higher energy & smelting input costs)"
            return "🔴 HEADWIND (Imported inflation pressure)"
        elif change_pct < -5.0:
            return "🟢 TAILWIND (Lower logistics and fuel input costs)"
        return "⚪ NEUTRAL"

    if sym == "^VIX":  # Volatility
        if current_val > 22.0 or change_pct > 15.0:
            return "🔴 HEADWIND (Elevated risk-off sentiment & FII equity selling)"
        elif current_val < 15.0:
            return "🟢 TAILWIND (Complacent/risk-on global liquidity environment)"
        return "⚪ NEUTRAL"

    return "⚪ NEUTRAL"


def get_macro_snapshot(as_of_date: str = "", sector: str = "") -> str:
    """Compile an institutional macro regime dashboard table.

    Tracks US 10-Year Treasury Yields, US Dollar Index (DXY), Key Benchmark
    Commodities (Copper, Silver, Gold, Brent), and Market Volatility (VIX).
    Provides sector-specific Headwind/Tailwind impact classifications.

    Args:
        as_of_date: Reference date (yyyy-mm-dd), defaults to latest available.
        sector: Target company's industry or sector (e.g., 'Metals & Mining', 'Utilities').

    Returns:
        Formatted Markdown table with macro readings and sector transmission insights.
    """
    rows = []
    as_of_str = as_of_date or datetime.now(UTC).strftime("%Y-%m-%d")

    for sym, meta in BENCHMARK_TICKERS.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="1mo")
            if hist.empty:
                continue

            clean = hist.dropna(subset=["Close"])
            if clean.empty:
                continue

            curr_val = float(clean["Close"].iloc[-1])
            first_val = float(clean["Close"].iloc[0])
            chg_pct = ((curr_val - first_val) / first_val) * 100 if first_val else 0.0

            if chg_pct > 1.0:
                trend = f"▲ +{chg_pct:.1f}% (Rising)"
            elif chg_pct < -1.0:
                trend = f"▼ {chg_pct:.1f}% (Falling)"
            else:
                trend = f"▶ {chg_pct:+.1f}% (Stable)"

            impact = _classify_impact(sym, chg_pct, curr_val, sector)

            unit = meta["unit"]
            val_display = f"{curr_val:.2f} {unit}" if unit != "%" else f"{curr_val:.2f}%"

            rows.append(
                {
                    "Indicator": f"**{meta['name']}** (`{sym}`)",
                    "Category": meta["category"],
                    "Current Level": val_display,
                    "1-Month Trend": trend,
                    "Impact for Sector": impact,
                }
            )
        except Exception as exc:
            logger.debug("Failed fetching macro benchmark %s: %s", sym, exc)
            continue

    if not rows:
        return f"<Macroeconomic benchmark snapshot temporarily unavailable as of {as_of_str}>"

    # Determine overall macro regime
    yield_val = next((r["Current Level"] for r in rows if "^TNX" in r["Indicator"]), "")
    dxy_val = next((r["Current Level"] for r in rows if "DX-Y.NYB" in r["Indicator"]), "")

    lines = [
        f"### Global Macroeconomic & Sector Transmission Snapshot (as of {as_of_str}):",
        f"- **Yield & Currency Environment**: US 10Y Yield at {yield_val} | US Dollar Index (DXY) at {dxy_val}",
        f"- **Target Sector Context**: {sector or 'Broad Market'}\n",
        "| Macro Benchmark | Category | Current Reading | 1-Month Trend | Sector Transmission Impact |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in rows:
        lines.append(
            f"| {r['Indicator']} | {r['Category']} | {r['Current Level']} | {r['1-Month Trend']} | {r['Impact for Sector']} |"
        )

    # Synthesis summary guidance for the analyst
    lines.extend(
        [
            "",
            "#### Analyst Macro-Transmission Takeaway:",
            "- **US Bond Yields & Dollar Strength**: High US yields and an elevated DXY exert direct downward pressure on emerging market equity flows (FII trimming) and make dollar-denominated commodities expensive globally.",
            "- **Commodity Price-Takers**: If analyzing Metals, Mining, or Energy companies, correlate domestic operational margins against LME and Brent trends above before assuming a low P/E represents an unassailable discount.",
        ]
    )

    return "\n".join(lines)
