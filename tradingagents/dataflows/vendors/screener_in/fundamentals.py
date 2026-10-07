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
    """Get company fundamentals overview from screener.in for Indian stocks.
    
    Args:
        ticker: Stock ticker symbol (without exchange suffix, e.g., RELIANCE)
        as_of_date: Analysis date in YYYY-MM-DD format (defaults to current date)
        
    Returns:
        Dictionary containing fundamental data for the company
    """
    # Normalize the ticker symbol
    normalized_ticker = normalize_symbol(ticker)
    
    # Construct the screener.in URL
    url = f"https://www.screener.in/company/{normalized_ticker}/consolidated/"
    
    try:
        # Check if vendor is reachable
        if not vendor_reachable(url):
            raise VendorUnavailableError(f"Screener.in is not reachable at {url}")
        
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
        company_name_tag = soup.find('h1', class_='h2')
        fundamentals['company_name'] = company_name_tag.get_text(strip=True) if company_name_tag else ""
        
        # Get current market price
        price_tag = soup.find('div', class_='number')
        fundamentals['current_price'] = float(price_tag.get_text(strip().replace(',', ''))) if price_tag else 0.0
        
        # Get key metrics from the quick ratios section
        ratios_section = soup.find('section', id='top-ratios')
        if ratios_section:
            ratio_items = ratios_section.find_all('li')
            for item in ratio_items:
                label = item.find('span', class_='name')
                value = item.find('span', class_='number')
                if label and value:
                    key = label.get_text(strip=True).lower().replace(' ', '_').replace('.', '')
                    val_text = value.get_text(strip=True).replace(',', '')
                    try:
                        # Try to convert to float, handle percentages and other formats
                        if '%' in val_text:
                            fundamentals[key] = float(val_text.replace('%', ''))
                        else:
                            fundamentals[key] = float(val_text)
                    except ValueError:
                        fundamentals[key] = val_text
        
        # Get financial ratios from the detailed sections
        sections = soup.find_all('section')
        for section in sections:
            heading = section.find('h2')
            if heading:
                section_title = heading.get_text(strip=True).lower()
                if 'profit and loss' in section_title or 'balance sheet' in section_title or 'cash flow' in section_title:
                    # Extract table data for financial statements
                    table = section.find('table')
                    if table:
                        # Process table data here if needed
                        pass
        
        # Apply date-based filtering if as_of_date is provided
        if as_of_date:
            fundamentals = withhold_live_profile(fundamentals, as_of_date)
            fundamentals = withhold_undated_statements(fundamentals, as_of_date)
        
        return fundamentals
        
    except requests.RequestException as e:
        raise VendorUnavailableError(f"Failed to fetch data from screener.in: {str(e)}")
    except Exception as e:
        raise VendorUnavailableError(f"Error processing screener.in data: {str(e)}")


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from screener.in."""
    # For now, we'll reuse the fundamentals function and extract balance sheet data
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    # In a full implementation, we would parse the balance sheet table specifically
    return {
        "balance_sheet": fundamentals_data,
        "statement_type": "balance_sheet"
    }


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get cash flow statement data from screener.in."""
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    return {
        "cashflow": fundamentals_data,
        "statement_type": "cashflow"
    }


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get income statement data from screener.in."""
    fundamentals_data = get_fundamentals(ticker, as_of_date)
    return {
        "income_statement": fundamentals_data,
        "statement_type": "income_statement"
    }
