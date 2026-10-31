"""Institutional flow, FII/DII shareholding trends, and NSE bulk/block deal detector."""

from __future__ import annotations

import contextlib
import io
import logging

import pandas as pd
import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.symbols import normalize_symbol

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_screener_shareholding(clean_ticker: str) -> str | None:
    """Fetch multi-quarter FII, DII, Promoter shareholding trend from Screener.in."""
    try:
        r = requests.get(
            f"https://www.screener.in/company/{clean_ticker}/", headers=HEADERS, timeout=10
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.content, "html.parser")
        sh = soup.find("section", id="shareholding")
        if not sh:
            return None

        tbl = sh.find("table", class_="data-table")
        if not tbl:
            return None

        rows = [
            [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            for tr in tbl.find_all("tr")
        ]
        if len(rows) < 2:
            return None

        quarters = rows[0]
        # Keep up to the last 6 quarters for concise display
        col_slice = slice(-6, None) if len(quarters) > 6 else slice(1, None)
        disp_quarters = quarters[col_slice]

        md_lines = [
            "#### Quarterly Institutional & Ownership Trend (Screener.in):",
            "",
            "| Shareholder Class | " + " | ".join(disp_quarters) + " |",
            "| --- | " + " | ".join(["---"] * len(disp_quarters)) + " |",
        ]

        fii_row = None
        dii_row = None

        for row in rows[1:]:
            cat = row[0].replace("+", "").strip()
            vals = row[col_slice]
            md_lines.append(f"| **{cat}** | " + " | ".join(vals) + " |")
            if cat.lower() == "fiis":
                fii_row = vals
            elif cat.lower() == "diis":
                dii_row = vals

        summary_notes = []
        if fii_row and len(fii_row) >= 2:
            with contextlib.suppress(Exception):
                start_fii = float(fii_row[0].replace("%", ""))
                end_fii = float(fii_row[-1].replace("%", ""))
                fii_diff = end_fii - start_fii
                fii_trend = "Accumulating (+)" if fii_diff > 0 else "Trimming / Selling (-)"
                summary_notes.append(
                    f"- **FII (Foreign) Flow**: {fii_trend} ({fii_diff:+.2f}% over reported window)"
                )

        if dii_row and len(dii_row) >= 2:
            with contextlib.suppress(Exception):
                start_dii = float(dii_row[0].replace("%", ""))
                end_dii = float(dii_row[-1].replace("%", ""))
                dii_diff = end_dii - start_dii
                dii_trend = "Accumulating (+)" if dii_diff > 0 else "Trimming / Selling (-)"
                summary_notes.append(
                    f"- **DII (Domestic MFs/LIC) Flow**: {dii_trend} ({dii_diff:+.2f}% over reported window)"
                )

        if summary_notes:
            md_lines.append("")
            md_lines.extend(summary_notes)

        return "\n".join(md_lines)

    except Exception as exc:
        logger.debug("Failed fetching shareholding for %s: %s", clean_ticker, exc)
        return None


def _fetch_nse_deals(clean_ticker: str) -> str:
    """Fetch recent single-day Bulk and Block deals from official NSE archives."""
    deals_found = []

    # 1. Bulk Deals (>= 0.5% of total equity)
    with contextlib.suppress(Exception):
        bulk_r = requests.get(
            "https://archives.nseindia.com/content/equities/bulk.csv", headers=HEADERS, timeout=8
        )
        if bulk_r.status_code == 200:
            df = pd.read_csv(io.StringIO(bulk_r.text))
            df.columns = [c.strip() for c in df.columns]
            if "Symbol" in df.columns:
                matches = df[df["Symbol"].astype(str).str.upper() == clean_ticker]
                for _, row in matches.iterrows():
                    deals_found.append(
                        {
                            "Type": "Bulk Deal (>=0.5% equity)",
                            "Date": row.get("Date", "N/A"),
                            "Client": row.get("Client Name", "N/A"),
                            "Action": row.get("Buy/Sell", "N/A"),
                            "Qty": row.get("Quantity Traded", "N/A"),
                            "Price": row.get("Trade Price / Wght. Avg. Price", "N/A"),
                        }
                    )

    # 2. Block Deals (>= ₹10 Crore value)
    with contextlib.suppress(Exception):
        block_r = requests.get(
            "https://archives.nseindia.com/content/equities/block.csv", headers=HEADERS, timeout=8
        )
        if block_r.status_code == 200:
            df = pd.read_csv(io.StringIO(block_r.text))
            df.columns = [c.strip() for c in df.columns]
            if "Symbol" in df.columns:
                matches = df[df["Symbol"].astype(str).str.upper() == clean_ticker]
                for _, row in matches.iterrows():
                    deals_found.append(
                        {
                            "Type": "Block Deal (>=₹10 Cr)",
                            "Date": row.get("Date", "N/A"),
                            "Client": row.get("Client Name", "N/A"),
                            "Action": row.get("Buy/Sell", "N/A"),
                            "Qty": row.get("Quantity Traded", "N/A"),
                            "Price": row.get("Trade Price / Wght. Avg. Price", "N/A"),
                        }
                    )

    if not deals_found:
        return "- **NSE Bulk & Block Deals**: No heavy institutional deals (>= 0.5% equity or >= ₹10 Cr) disclosed in the latest exchange session."

    lines = [
        "#### NSE Heavy Institutional Deals (Bulk & Block):",
        "",
        "| Deal Type | Date | Institution / Client Name | Action | Quantity | Avg Price |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in deals_found:
        qty_str = f"{d['Qty']:,}" if isinstance(d["Qty"], (int, float)) else str(d["Qty"])
        price_str = (
            f"₹{d['Price']:,.2f}" if isinstance(d["Price"], (int, float)) else str(d["Price"])
        )
        lines.append(
            f"| {d['Type']} | {d['Date']} | {d['Client']} | **{d['Action']}** | {qty_str} | {price_str} |"
        )

    return "\n".join(lines)


def get_institutional_flow(ticker: str) -> str:
    """Retrieve institutional flow, FII/DII shareholding trends, and large block/bulk deals."""
    clean = ticker.upper().replace(".NS", "").replace(".BO", "").strip()

    # 1. Indian Stock Flow Analysis
    sh_text = _fetch_screener_shareholding(clean)
    if sh_text is not None:
        deals_text = _fetch_nse_deals(clean)
        return (
            f"### Institutional Flow & Shareholding Analysis for {clean}:\n\n"
            f"{sh_text}\n\n"
            f"{deals_text}"
        )

    # 2. Global / US Stock Institutional Holdings (via Yahoo Finance)
    import yfinance as yf

    canonical = normalize_symbol(ticker)
    try:
        t = yf.Ticker(canonical)
        major = t.major_holders
        inst = t.institutional_holders

        lines = [f"### Institutional Holdings & Flow for {canonical} (Yahoo Finance):"]

        if major is not None and not major.empty:
            lines.append("\n**Ownership Breakdown**:")
            for idx, row in major.iterrows():
                val = row.get("Value", row.iloc[0] if len(row) > 0 else "")
                lbl = row.get("Breakdown", idx)
                if isinstance(val, (int, float)) and val <= 1.0:
                    val = f"{val * 100:.2f}%"
                lines.append(f"- **{lbl}**: {val}")

        if inst is not None and not inst.empty:
            lines.append("\n**Top Institutional Holders & Recent Position Shifts**:")
            lines.append(
                "| Institution / Fund | Shares | Value | % Position Change | Date Reported |"
            )
            lines.append("| --- | --- | --- | --- | --- |")
            for _, row in inst.head(6).iterrows():
                holder = row.get("Holder", "N/A")
                shares = row.get("Shares", 0)
                shares_str = f"{shares:,}" if isinstance(shares, (int, float)) else str(shares)
                val = row.get("Value", 0)
                val_str = (
                    f"${val / 1e9:.2f}B"
                    if isinstance(val, (int, float)) and val > 1e7
                    else f"${val:,.0f}"
                )
                pct = row.get("pctChange", 0)
                pct_str = f"{pct * 100:+.2f}%" if isinstance(pct, (int, float)) else str(pct)
                date_rep = row.get("Date Reported", "N/A")
                if isinstance(date_rep, pd.Timestamp):
                    date_rep = date_rep.strftime("%Y-%m-%d")
                lines.append(
                    f"| {holder} | {shares_str} | {val_str} | **{pct_str}** | {date_rep} |"
                )

        return (
            "\n".join(lines)
            if len(lines) > 1
            else f"No institutional holdings data found for {ticker}."
        )

    except Exception as exc:
        return f"Could not retrieve institutional flow data for {ticker}: {exc}"
