from typing import Annotated

import requests
from bs4 import BeautifulSoup

from tradingagents.dataflows.date_window import (
    withhold_live_profile,
    withhold_undated_statements,
)
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE for NSE)"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get company fundamentals overview from moneycontrol.com for Indian stocks.
    
    Args:
        ticker: Stock ticker symbol (with exchange suffix if needed, e.g., RELIANCE.NS)
        as_of_date: Analysis date in YYYY-MM-DD format (defaults to current date)
        
    Returns:
        Dictionary containing fundamental data for the company
    """
    # Normalize the ticker symbol
    normalized_ticker = normalize_symbol(ticker)
    
    # Moneycontrol uses different format for NSE vs BSE
    # For simplicity, we'll assume NSE format (.NS) or try to construct the URL
    url = f"https://www.moneycontrol.com/financials/{normalized_ticker}/ratiosVI/{normalized_ticker}#/{normalized_ticker}"
    
    try:
        # Check if vendor is reachable
        if not vendor_reachable(url):
            raise VendorUnavailableError(f"Moneycontrol is not reachable at {url}")
        
        # Fetch the webpage
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract fundamental data
        fundamentals = {}
        
        # Get company name
        company_name_tag = soup.find('h1', class_='pcstname')
        if not company_name_tag:
            company_name_tag = soup.find('div', class_=' PT15 pb_15')
        fundamentals['company_name'] = company_name_tag.get_text(strip=True) if company_name_tag else ""
        
        # Get current market price
        price_tag = soup.find('div', class_='inprice1 nsecp')
        if not price_tag:
            price_tag = soup.find('div', class_='inprice1 bsecp')
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace(',', '')
            try:
                fundamentals['current_price'] = float(price_text)
            except ValueError:
                fundamentals['current_price'] = 0.0
        else:
            fundamentals['current_price'] = 0.0
        
        # Get key financial ratios from the ratios table
        ratios_table = soup.find('table', class_='tbldata14 bdrtpg')
        if ratios_table:
            rows = ratios_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    label = cols[0].get_text(strip=True).lower().replace(' ', '_').replace('.', '').replace('%', '_percent')
                    value_text = cols[1].get_text(strip=True).replace(',', '')
                    try:
                        if '%' in cols[1].get_text():
                            fundamentals[label] = float(value_text.replace('%', ''))
                        else:
                            fundamentals[label] = float(value_text)
                    except ValueError:
                        fundamentals[label] = value_text
        
        # Apply date-based filtering if as_of_date is provided
        if as_of_date:
            fundamentals = withhold_live_profile(fundamentals, as_of_date)
            fundamentals = withhold_undated_statements(fundamentals, as_of_date)
        
        return fundamentals
        
    except requests.RequestException as e:
        raise VendorUnavailableError(f"Failed to fetch data from moneycontrol: {str(e)}")
    except Exception as e:
        raise VendorUnavailableError(f"Error processing moneycontrol data: {str(e)}")


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from moneycontrol."""
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    return {
        "balance_sheet": fundamentals_data,
        "statement_type": "balance_sheet"
    }


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get cash flow statement data from moneycontrol."""
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    return {
        "cashflow": fundamentals_data,
        "statement_type": "cashflow"
    }


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get income statement data from moneycontrol."""
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    return {
        "income_statement": fundamentals_data,
        "statement_type": "income_statement"
    }
