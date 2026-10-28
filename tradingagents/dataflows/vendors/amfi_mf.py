"""AMFI Indian Mutual Fund data vendor.

Fetches real-time and historical Net Asset Value (NAV), scheme classification,
and performance metrics directly via the AMFI API (api.mfapi.in).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError

logger = logging.getLogger(__name__)

AMFI_API_BASE = "https://api.mfapi.in/mf"


def search_mutual_fund(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for Indian mutual funds by scheme name or keyword."""
    clean_query = query.strip()
    try:
        url = f"{AMFI_API_BASE}/search?q={clean_query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        return data[:limit] if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Error searching mutual fund '%s': %s", query, exc)
        return []


def get_mutual_fund_details(scheme_identifier: str) -> dict[str, Any]:
    """Retrieve full details, latest NAV, and returns for an Indian mutual fund.

    Args:
        scheme_identifier: AMFI scheme code (e.g. '122639') or scheme name (e.g. 'Parag Parikh Flexi Cap').
    """
    clean_id = str(scheme_identifier).strip()
    scheme_code = None

    if clean_id.isdigit():
        scheme_code = clean_id
    else:
        results = search_mutual_fund(clean_id, limit=1)
        if not results:
            raise NoMarketDataError(
                scheme_identifier, f"No Indian mutual fund found matching '{scheme_identifier}'"
            )
        scheme_code = str(results[0]["schemeCode"])

    try:
        url = f"{AMFI_API_BASE}/{scheme_code}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise VendorUnavailableError(
                f"MFAPI returned status {response.status_code} for scheme {scheme_code}"
            )

        res_json = response.json()
        meta = res_json.get("meta", {})
        nav_history = res_json.get("data", [])

        if not nav_history:
            raise NoMarketDataError(
                scheme_identifier, f"No NAV data available for scheme {scheme_code}"
            )

        latest_entry = nav_history[0]
        latest_nav = float(latest_entry.get("nav", 0.0))
        nav_date = latest_entry.get("date", "")

        # Compute point-to-point trailing returns (CAGR / absolute)
        # Assuming ~250 trading days per year
        returns: dict[str, float | None] = {
            "1M": None,
            "6M": None,
            "1Y": None,
            "3Y": None,
            "5Y": None,
        }

        intervals = [
            ("1M", 21),
            ("6M", 125),
            ("1Y", 250),
            ("3Y", 750),
            ("5Y", 1250),
        ]

        total_days = len(nav_history)
        for label, offset in intervals:
            if total_days > offset:
                past_nav = float(nav_history[offset].get("nav", 0.0))
                if past_nav > 0:
                    years = offset / 250.0
                    if years <= 1.0:
                        ret = ((latest_nav - past_nav) / past_nav) * 100.0
                    else:
                        ret = (((latest_nav / past_nav) ** (1.0 / years)) - 1.0) * 100.0
                    returns[label] = round(ret, 2)

        return {
            "scheme_code": scheme_code,
            "scheme_name": meta.get("scheme_name", scheme_identifier),
            "fund_house": meta.get("fund_house", "Indian AMC"),
            "category": meta.get("scheme_category", "Mutual Fund"),
            "scheme_type": meta.get("scheme_type", "Open Ended"),
            "isin_growth": meta.get("isin_growth"),
            "latest_nav": latest_nav,
            "nav_date": nav_date,
            "returns_cagr": returns,
            "history_bars_available": total_days,
        }

    except Exception as exc:
        if isinstance(exc, (NoMarketDataError, VendorUnavailableError)):
            raise
        raise VendorUnavailableError(f"Failed to fetch mutual fund details: {exc}") from exc


def get_mutual_fund_report(scheme_identifier: str) -> str:
    """Formatted textual report for LangGraph analyst agents."""
    details = get_mutual_fund_details(scheme_identifier)
    rets = details.get("returns_cagr", {})

    lines = [
        f"# Indian Mutual Fund Analysis: {details['scheme_name']}",
        f"- **Scheme Code (AMFI):** `{details['scheme_code']}`",
        f"- **Fund House (AMC):** {details['fund_house']}",
        f"- **Category:** {details['category']}",
        f"- **Scheme Type:** {details['scheme_type']}",
        f"- **Latest NAV:** ₹{details['latest_nav']:,.4f} (as of {details['nav_date']})",
        "",
        "### Trailing Historical Returns (CAGR / Absolute):",
        f"- **1-Month:** {rets.get('1M', 'N/A')}%"
        if rets.get("1M") is not None
        else "- **1-Month:** N/A",
        f"- **6-Month:** {rets.get('6M', 'N/A')}%"
        if rets.get("6M") is not None
        else "- **6-Month:** N/A",
        f"- **1-Year:** {rets.get('1Y', 'N/A')}%"
        if rets.get("1Y") is not None
        else "- **1-Year:** N/A",
        f"- **3-Year CAGR:** {rets.get('3Y', 'N/A')}%"
        if rets.get("3Y") is not None
        else "- **3-Year CAGR:** N/A",
        f"- **5-Year CAGR:** {rets.get('5Y', 'N/A')}%"
        if rets.get("5Y") is not None
        else "- **5-Year CAGR:** N/A",
    ]

    return "\n".join(lines)


def get_mutual_fund_nav_df(scheme_identifier: str, as_of_date: str = "") -> pd.DataFrame:
    """Retrieve full NAV history as an OHLCV-compatible DataFrame for stockstats / indicators.

    Columns: Date (datetime), Open, High, Low, Close (all equal to NAV), Volume (0).
    """
    clean_id = str(scheme_identifier).strip()
    scheme_code = clean_id if clean_id.isdigit() else None
    if not scheme_code:
        results = search_mutual_fund(clean_id, limit=1)
        if not results:
            raise NoMarketDataError(
                scheme_identifier,
                scheme_identifier,
                f"No Indian mutual fund found matching '{scheme_identifier}'",
            )
        scheme_code = str(results[0]["schemeCode"])

    url = f"{AMFI_API_BASE}/{scheme_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        raise VendorUnavailableError(
            f"MFAPI returned status {response.status_code} for scheme {scheme_code}"
        )

    res_json = response.json()
    data = res_json.get("data", [])
    if not data:
        raise NoMarketDataError(
            scheme_identifier, scheme_code, f"No NAV data available for scheme {scheme_code}"
        )

    rows = []
    for d in data:
        try:
            dt = pd.to_datetime(d["date"], format="%d-%m-%Y")
            nav_val = float(d["nav"])
            rows.append(
                {
                    "Date": dt,
                    "Open": nav_val,
                    "High": nav_val,
                    "Low": nav_val,
                    "Close": nav_val,
                    "Volume": 0,
                }
            )
        except Exception:
            continue

    if not rows:
        raise NoMarketDataError(
            scheme_identifier, scheme_code, f"Could not parse NAV history for {scheme_code}"
        )

    df = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    if as_of_date:
        as_of_dt = pd.to_datetime(as_of_date).normalize()
        df = df[df["Date"] <= as_of_dt]

    return df


def get_mutual_fund_stock_data_csv(scheme_identifier: str, start_date: str, end_date: str) -> str:
    """Retrieve CSV representation of mutual fund NAV history over a date window."""
    df = get_mutual_fund_nav_df(scheme_identifier, end_date)
    start_dt = pd.to_datetime(start_date).normalize()
    filtered = df[df["Date"] >= start_dt].copy()
    if filtered.empty:
        raise NoMarketDataError(
            scheme_identifier,
            scheme_identifier,
            f"No NAV records between {start_date} and {end_date}",
        )

    for col in ["Open", "High", "Low", "Close"]:
        filtered[col] = filtered[col].round(4)

    csv_data = filtered.to_csv(index=False)
    header = (
        f"# Indian Mutual Fund NAV data for {scheme_identifier} from {start_date} to {end_date}\n"
    )
    header += f"# Total records: {len(filtered)}\n\n"
    return header + csv_data
