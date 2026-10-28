"""Screener.in vendor integration for Indian equity fundamentals."""

from typing import Annotated, Any, Dict
import logging
import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.date_window import (
    is_historical,
    withhold_live_profile,
    withhold_undated_statements,
)
from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)


def get_fundamentals_dict(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE for NSE)"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> Dict[str, Any]:
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

    urls_to_try = [
        f"https://www.screener.in/company/{clean_ticker}/consolidated/",
        f"https://www.screener.in/company/{clean_ticker}/",
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = None
    last_error = None
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                response = r
                break
        except requests.RequestException as e:
            last_error = e

    # If still not found, try Screener company search API
    if response is None:
        try:
            search_url = f"https://www.screener.in/api/company/search/?q={clean_ticker}"
            sr = requests.get(search_url, headers=headers, timeout=8)
            if sr.status_code == 200 and sr.json():
                first_match_url = sr.json()[0].get("url")
                if first_match_url:
                    full_match_url = f"https://www.screener.in{first_match_url}"
                    r = requests.get(full_match_url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        response = r
        except Exception:
            pass

    if response is None:
        if last_error:
            raise VendorUnavailableError(f"Failed to fetch data from screener.in for {clean_ticker}: {last_error}")
        raise VendorUnavailableError(f"Company {clean_ticker} not found on screener.in (HTTP 404)")

    try:
        soup = BeautifulSoup(response.content, "html.parser")
        fundamentals: Dict[str, Any] = {
            "ticker": clean_ticker,
            "source": "screener.in",
        }

        # 1. Company Name
        company_name_tag = soup.find("h1")
        fundamentals["company_name"] = company_name_tag.get_text(strip=True) if company_name_tag else clean_ticker

        # 2. Key metrics from the top-ratios list (UL)
        ratios_ul = soup.find("ul", id="top-ratios")
        if ratios_ul:
            ratio_items = ratios_ul.find_all("li")
            for item in ratio_items:
                label = item.find("span", class_="name")
                value = item.find("span", class_="number")
                if label and value:
                    key = label.get_text(strip=True).lower().replace(" ", "_").replace(".", "").replace("/", "_")
                    val_text = value.get_text(strip=True).replace(",", "")
                    try:
                        if "%" in val_text:
                            fundamentals[key] = float(val_text.replace("%", ""))
                        else:
                            fundamentals[key] = float(val_text)
                    except ValueError:
                        fundamentals[key] = val_text

        # Extract current_price explicitly
        if "current_price" not in fundamentals:
            for k in ["current_price", "market_price"]:
                if k in fundamentals:
                    fundamentals["current_price"] = fundamentals[k]
                    break

        # 3. Peer & Sector Information
        peers_section = soup.find("section", id="peers")
        if peers_section:
            p_tag = peers_section.find("p")
            if p_tag:
                parts = [x.strip() for x in p_tag.get_text("|", strip=True).split("|") if x.strip()]
                if len(parts) >= 2:
                    fundamentals["sector"] = parts[0]
                    fundamentals["industry"] = parts[1]
                elif parts:
                    fundamentals["sector"] = parts[0]
                    fundamentals["industry"] = parts[0]

        # 4. Financial Statements (Profit & Loss / EBITDA / Net Profit)
        pl_section = soup.find("section", id="profit-loss")
        if pl_section:
            table = pl_section.find("table", class_="data-table")
            if table:
                for row in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    if len(cells) >= 2:
                        row_name = cells[0].lower()
                        val_str = cells[-1].replace(",", "").replace("%", "")
                        if "operating profit" in row_name and "ebitda_cr" not in fundamentals:
                            try:
                                fundamentals["ebitda_cr"] = float(val_str)
                            except ValueError:
                                pass
                        elif "opm" in row_name and "opm_percent" not in fundamentals:
                            try:
                                fundamentals["opm_percent"] = float(val_str)
                            except ValueError:
                                pass
                        elif "net profit" in row_name and "net_profit_cr" not in fundamentals:
                            try:
                                fundamentals["net_profit_cr"] = float(val_str)
                            except ValueError:
                                pass
                        elif "sales" in row_name and "sales_cr" not in fundamentals:
                            try:
                                fundamentals["sales_cr"] = float(val_str)
                            except ValueError:
                                pass

        if "stock_p_e" in fundamentals and "pe_ratio" not in fundamentals:
            fundamentals["pe_ratio"] = fundamentals["stock_p_e"]

        if as_of_date and is_historical(as_of_date):
            withheld = withhold_live_profile(as_of_date, clean_ticker)
            if withheld:
                fundamentals["notice"] = withheld

        return fundamentals

    except Exception as e:
        raise VendorUnavailableError(f"Error processing screener.in data for {clean_ticker}: {str(e)}")


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
        ("Stock P/E", data.get("stock_p_e")),
        ("Book Value (INR)", data.get("book_value")),
        ("Dividend Yield (%)", data.get("dividend_yield")),
        ("ROCE (%)", data.get("roce")),
        ("ROE (%)", data.get("roe")),
        ("Sales TTM (Cr)", data.get("sales_cr")),
        ("Operating Profit / EBITDA (Cr)", data.get("ebitda_cr")),
        ("Operating Margin (OPM %)", data.get("opm_percent")),
        ("Net Profit TTM (Cr)", data.get("net_profit_cr")),
    ]

    lines = [f"{label}: {v}" for label, v in fields if v is not None]
    return f"Screener.in Fundamentals Overview for {clean_ticker}:\n\n" + "\n".join(lines)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    return (
        f"Screener.in Balance Sheet Summary for {data.get('ticker', ticker)}:\n\n"
        f"Book Value: ₹{data.get('book_value', 'N/A')}\n"
        f"Market Cap: ₹{data.get('market_cap', 'N/A')} Cr\n"
        f"ROCE: {data.get('roce', 'N/A')}%\n"
        f"ROE: {data.get('roe', 'N/A')}%"
    )


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cashflow statement summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    return (
        f"Screener.in Cash Flow Summary for {data.get('ticker', ticker)}:\n\n"
        f"Operating Profit / EBITDA: ₹{data.get('ebitda_cr', 'N/A')} Cr\n"
        f"Operating Profit Margin: {data.get('opm_percent', 'N/A')}%\n"
        f"Net Profit: ₹{data.get('net_profit_cr', 'N/A')} Cr"
    )


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement summary from screener.in."""
    data = get_fundamentals_dict(ticker, as_of_date)
    return (
        f"Screener.in Income Statement Summary for {data.get('ticker', ticker)}:\n\n"
        f"Sales (TTM): ₹{data.get('sales_cr', 'N/A')} Cr\n"
        f"Operating Profit / EBITDA: ₹{data.get('ebitda_cr', 'N/A')} Cr\n"
        f"OPM: {data.get('opm_percent', 'N/A')}%\n"
        f"Net Profit: ₹{data.get('net_profit_cr', 'N/A')} Cr\n"
        f"Stock P/E: {data.get('stock_p_e', 'N/A')}"
    )
