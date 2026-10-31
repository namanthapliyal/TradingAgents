"""Screener.in vendor integration for Indian equity fundamentals."""

from __future__ import annotations

import contextlib
import logging
from typing import Annotated, Any

import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.date_window import (
    is_historical,
    withhold_live_profile,
)
from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)


def _parse_screener_soup(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract fundamental fields from a Screener.in BeautifulSoup document."""
    fund: dict[str, Any] = {}

    # 1. Company Name
    company_name_tag = soup.find("h1")
    if company_name_tag and company_name_tag.get_text(strip=True):
        fund["company_name"] = company_name_tag.get_text(strip=True)

    # 2. Key metrics from the top-ratios list (UL)
    ratios_ul = soup.find("ul", id="top-ratios")
    if ratios_ul:
        for item in ratios_ul.find_all("li"):
            label = item.find("span", class_="name")
            if not label:
                continue
            key = (
                label.get_text(strip=True)
                .lower()
                .replace(" ", "_")
                .replace(".", "")
                .replace("/", "_")
            )
            numbers = item.find_all("span", class_="number")
            if len(numbers) > 1:
                # E.g. High / Low has both High and Low spans: "52.5 / 27.5"
                parts = [
                    n.get_text(strip=True).replace(",", "")
                    for n in numbers
                    if n.get_text(strip=True)
                ]
                if parts:
                    fund[key] = " / ".join(parts)
            elif len(numbers) == 1:
                val_text = numbers[0].get_text(strip=True).replace(",", "")
                if val_text:
                    try:
                        if "%" in val_text:
                            fund[key] = float(val_text.replace("%", ""))
                        else:
                            fund[key] = float(val_text)
                    except ValueError:
                        fund[key] = val_text

    # Extract current_price explicitly
    for k in ["current_price", "market_price"]:
        if k in fund and fund[k]:
            fund["current_price"] = fund[k]
            break

    # 3. Peer & Sector Information
    peers_section = soup.find("section", id="peers")
    if peers_section:
        p_tag = peers_section.find("p")
        if p_tag:
            parts = [x.strip() for x in p_tag.get_text("|", strip=True).split("|") if x.strip()]
            if len(parts) >= 2:
                fund["sector"] = parts[0]
                fund["industry"] = parts[1]
            elif parts:
                fund["sector"] = parts[0]
                fund["industry"] = parts[0]

    # 4. Financial Statements (Profit & Loss / EBITDA / Net Profit / Sales)
    pl_section = soup.find("section", id="profit-loss")
    if pl_section:
        table = pl_section.find("table", class_="data-table")
        if table:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) >= 2:
                    row_name = cells[0].lower()
                    val_str = cells[-1].replace(",", "").replace("%", "")
                    if "operating profit" in row_name and "ebitda_cr" not in fund:
                        with contextlib.suppress(ValueError):
                            fund["ebitda_cr"] = float(val_str)
                    elif "opm" in row_name and "opm_percent" not in fund:
                        with contextlib.suppress(ValueError):
                            fund["opm_percent"] = float(val_str)
                    elif "net profit" in row_name and "net_profit_cr" not in fund:
                        with contextlib.suppress(ValueError):
                            fund["net_profit_cr"] = float(val_str)
                    elif "sales" in row_name and "sales_cr" not in fund:
                        with contextlib.suppress(ValueError):
                            fund["sales_cr"] = float(val_str)

    return fund


def _enrich_from_yfinance(clean_ticker: str, fundamentals: dict[str, Any]) -> None:
    """Enrich missing metrics (book_value, roe, high/low) via yfinance fallback."""
    needed = ["book_value", "roe", "current_price", "market_cap", "high___low", "pe_ratio"]
    missing = [k for k in needed if k not in fundamentals or fundamentals[k] in (None, "")]
    if not missing:
        return

    try:
        import yfinance as yf

        for suffix in (".NS", ".BO", ""):
            sym = f"{clean_ticker}{suffix}"
            t = yf.Ticker(sym)
            info = t.info
            if not info or not isinstance(info, dict):
                continue
            if (
                "regularMarketPrice" not in info
                and "currentPrice" not in info
                and "bookValue" not in info
            ):
                continue

            if (
                "book_value" not in fundamentals or fundamentals["book_value"] in (None, "")
            ) and info.get("bookValue"):
                fundamentals["book_value"] = round(float(info["bookValue"]), 2)
            if ("roe" not in fundamentals or fundamentals["roe"] in (None, "")) and info.get(
                "returnOnEquity"
            ):
                fundamentals["roe"] = round(float(info["returnOnEquity"]) * 100, 2)
            if "current_price" not in fundamentals or fundamentals["current_price"] in (None, ""):
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if price:
                    fundamentals["current_price"] = float(price)
            if "high___low" not in fundamentals or "/" not in str(
                fundamentals.get("high___low", "")
            ):
                hi = info.get("fiftyTwoWeekHigh")
                lo = info.get("fiftyTwoWeekLow")
                if hi and lo:
                    fundamentals["high___low"] = f"{hi} / {lo}"
            if (
                "market_cap" not in fundamentals or fundamentals["market_cap"] in (None, "")
            ) and info.get("marketCap"):
                fundamentals["market_cap"] = round(info["marketCap"] / 1e7, 2)
            if (
                "stock_p_e" not in fundamentals or fundamentals["stock_p_e"] in (None, "")
            ) and info.get("trailingPE"):
                fundamentals["stock_p_e"] = round(float(info["trailingPE"]), 2)
            if (
                "dividend_yield" not in fundamentals or fundamentals["dividend_yield"] in (None, "")
            ) and info.get("dividendYield"):
                fundamentals["dividend_yield"] = round(float(info["dividendYield"]) * 100, 2)
            break
    except Exception as exc:
        logger.debug("yfinance enrichment skipped for %s: %s", clean_ticker, exc)


def get_fundamentals_dict(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE for NSE)"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> dict[str, Any]:
    """Get company fundamentals dictionary from screener.in for Indian stocks.

    Args:
        ticker: Stock ticker symbol (with or without exchange suffix, e.g. RELIANCE, TCS.NS)
        as_of_date: Analysis date in YYYY-MM-DD format (defaults to current date)

    Returns:
        Dictionary containing fundamental data for the company.
    """
    clean_ticker = ticker.upper().replace(".NS", "").replace(".BO", "").strip()

    # Common ticker aliases for Indian demergers / special symbols
    aliases = {
        "TATAMOTORS": "TMPV",
        "TATA-MOTORS": "TMPV",
        "L&T": "LT",
        "M&M": "M&M",
    }
    if clean_ticker in aliases:
        clean_ticker = aliases[clean_ticker]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    url_cons = f"https://www.screener.in/company/{clean_ticker}/consolidated/"
    url_std = f"https://www.screener.in/company/{clean_ticker}/"

    fundamentals: dict[str, Any] = {
        "ticker": clean_ticker,
        "source": "screener.in",
    }

    # 1. Attempt Consolidated Page first
    resp_cons = None
    with contextlib.suppress(requests.RequestException):
        r = requests.get(url_cons, headers=headers, timeout=10)
        if r.status_code == 200:
            resp_cons = r

    if resp_cons is not None:
        soup_cons = BeautifulSoup(resp_cons.content, "html.parser")
        fundamentals.update(_parse_screener_soup(soup_cons))

    # 2. If consolidated page is missing or has empty key metrics (e.g. book_value, ROCE, ROE),
    # backfill from the standalone page.
    needed_metrics = {
        "book_value",
        "roce",
        "roe",
        "market_cap",
        "current_price",
        "high___low",
        "stock_p_e",
        "sales_cr",
    }
    missing_needed = [
        k for k in needed_metrics if k not in fundamentals or fundamentals[k] in (None, "")
    ]

    if missing_needed or resp_cons is None:
        resp_std = None
        with contextlib.suppress(requests.RequestException):
            r = requests.get(url_std, headers=headers, timeout=10)
            if r.status_code == 200:
                resp_std = r

        if resp_std is not None:
            soup_std = BeautifulSoup(resp_std.content, "html.parser")
            std_fund = _parse_screener_soup(soup_std)
            for k, v in std_fund.items():
                if k not in fundamentals or fundamentals[k] in (None, ""):
                    fundamentals[k] = v

    # 3. If still not found, try Screener company search API
    if "company_name" not in fundamentals:
        with contextlib.suppress(Exception):
            search_url = f"https://www.screener.in/api/company/search/?q={clean_ticker}"
            sr = requests.get(search_url, headers=headers, timeout=8)
            if sr.status_code == 200 and sr.json():
                first_match_url = sr.json()[0].get("url")
                if first_match_url:
                    full_match_url = f"https://www.screener.in{first_match_url}"
                    r = requests.get(full_match_url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        soup_search = BeautifulSoup(r.content, "html.parser")
                        fundamentals.update(_parse_screener_soup(soup_search))

    if "company_name" not in fundamentals and len(fundamentals) <= 2:
        raise VendorUnavailableError(f"Company {clean_ticker} not found on screener.in (HTTP 404)")

    # 4. Secondary fallback: Enrich any remaining missing metrics from yfinance
    _enrich_from_yfinance(clean_ticker, fundamentals)

    # 5. Normalize key metrics
    if "stock_p_e" in fundamentals and "pe_ratio" not in fundamentals:
        fundamentals["pe_ratio"] = fundamentals["stock_p_e"]

    if as_of_date and is_historical(as_of_date):
        try:
            from datetime import datetime

            from tradingagents.dataflows.date_window import get_current_date

            curr = datetime.strptime(get_current_date(), "%Y-%m-%d")
            as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
            # Only withhold if genuinely older than the current quarter (> 90 days).
            if (curr - as_of_dt).days > 90:
                withheld = withhold_live_profile(as_of_date, clean_ticker)
                if withheld:
                    fundamentals["notice"] = withheld
        except Exception:
            pass

    return fundamentals


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE for NSE)"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get formatted company fundamentals report from screener.in for LangGraph agents."""
    data = get_fundamentals_dict(ticker, as_of_date)
    if "notice" in data:
        return data["notice"]
    clean_ticker = data.get("ticker", ticker)

    fields = [
        ("Company Name", data.get("company_name")),
        ("Sector", data.get("sector")),
        ("Industry", data.get("industry")),
        ("Market Cap (Cr)", data.get("market_cap")),
        ("Current Price (INR)", data.get("current_price")),
        ("High / Low", data.get("high___low")),
        ("Stock P/E", data.get("stock_p_e") or data.get("pe_ratio")),
        ("Book Value (INR)", data.get("book_value")),
        ("Dividend Yield (%)", data.get("dividend_yield")),
        ("ROCE (%)", data.get("roce")),
        ("ROE (%)", data.get("roe")),
        ("Sales TTM (Cr)", data.get("sales_cr")),
        ("Operating Profit / EBITDA (Cr)", data.get("ebitda_cr")),
        ("Operating Margin (OPM %)", data.get("opm_percent")),
        ("Net Profit TTM (Cr)", data.get("net_profit_cr")),
    ]

    lines = [f"{label}: {v if v not in (None, '') else 'N/A'}" for label, v in fields]
    return f"Screener.in Fundamentals Overview for {clean_ticker}:\n\n" + "\n".join(lines)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    bv = data.get("book_value")
    bv_str = f"₹{bv}" if bv not in (None, "") else "N/A"
    mc = data.get("market_cap")
    mc_str = f"₹{mc} Cr" if mc not in (None, "") else "N/A"
    roce = data.get("roce")
    roce_str = f"{roce}%" if roce not in (None, "") else "N/A"
    roe = data.get("roe")
    roe_str = f"{roe}%" if roe not in (None, "") else "N/A"

    return (
        f"Screener.in Balance Sheet Summary ({freq}) for {data.get('ticker', ticker)}:\n\n"
        f"Book Value: {bv_str}\n"
        f"Market Cap: {mc_str}\n"
        f"ROCE: {roce_str}\n"
        f"ROE: {roe_str}"
    )


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cashflow statement summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    ebitda = data.get("ebitda_cr")
    ebitda_str = f"₹{ebitda} Cr" if ebitda not in (None, "") else "N/A"
    opm = data.get("opm_percent")
    opm_str = f"{opm}%" if opm not in (None, "") else "N/A"
    net_profit = data.get("net_profit_cr")
    np_str = f"₹{net_profit} Cr" if net_profit not in (None, "") else "N/A"

    return (
        f"Screener.in Cash Flow Summary ({freq}) for {data.get('ticker', ticker)}:\n\n"
        f"Operating Profit / EBITDA: {ebitda_str}\n"
        f"Operating Profit Margin: {opm_str}\n"
        f"Net Profit: {np_str}"
    )


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    sales = data.get("sales_cr")
    sales_str = f"₹{sales} Cr" if sales not in (None, "") else "N/A"
    ebitda = data.get("ebitda_cr")
    ebitda_str = f"₹{ebitda} Cr" if ebitda not in (None, "") else "N/A"
    opm = data.get("opm_percent")
    opm_str = f"{opm}%" if opm not in (None, "") else "N/A"
    net_profit = data.get("net_profit_cr")
    np_str = f"₹{net_profit} Cr" if net_profit not in (None, "") else "N/A"
    pe = data.get("stock_p_e") or data.get("pe_ratio")
    pe_str = f"{pe}" if pe not in (None, "") else "N/A"

    return (
        f"Screener.in Income Statement Summary ({freq}) for {data.get('ticker', ticker)}:\n\n"
        f"Sales (TTM): {sales_str}\n"
        f"Operating Profit / EBITDA: {ebitda_str}\n"
        f"OPM: {opm_str}\n"
        f"Net Profit: {np_str}\n"
        f"Stock P/E: {pe_str}"
    )
