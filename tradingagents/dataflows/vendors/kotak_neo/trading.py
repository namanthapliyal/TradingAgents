from typing import Annotated, Dict, List, Optional
import requests
import json

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable


def place_order(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE.NS)"],
    action: Annotated[str, "BUY or SELL"],
    quantity: Annotated[int, "number of shares to trade"],
    order_type: Annotated[str, "MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET"] = "MARKET",
    price: Annotated[Optional[float], "price for LIMIT or STOP_LOSS orders"] = None,
    product_type: Annotated[str, "MIS for intraday, CNC for delivery, CO for bracket order"] = "CNC",
    validity: Annotated[str, "DAY for day order, IOC for immediate or cancel"] = "DAY",
    disclosed_quantity: Annotated[int, "disclosed quantity for iceberg orders"] = 0
) -> Dict[str, any]:
    """Place a trading order via Kotak Neo API.

    Args:
        ticker: Stock ticker symbol with exchange suffix
        action: BUY or SELL
        quantity: Number of shares
        order_type: MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET
        price: Price for LIMIT/STOP_LOSS orders (required for LIMIT and STOP_LOSS)
        product_type: MIS (intraday), CNC (delivery), CO (bracket order)
        validity: DAY or IOC
        disclosed_quantity: Disclosed quantity for iceberg orders

    Returns:
        Dictionary containing order details and status
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://api.kotaksecurities.com"):
        raise VendorUnavailableError("Kotak Neo API is not reachable")

    # In a real implementation, you would:
    # 1. Load API credentials from secure storage/environment
    # 2. Generate access token (if needed)
    # 3. Make actual API call to place order

    # For now, we'll return a simulated response
    # In production, this would be replaced with actual API calls

    try:
        # Simulate order placement
        order_id = f"KTNK_{hash(ticker + action + str(quantity)) % 1000000:06d}"

        result = {
            "order_id": order_id,
            "status": "OPEN",
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
            "product_type": product_type,
            "validity": validity,
            "disclosed_quantity": disclosed_quantity,
            "timestamp": "2026-10-08T10:30:00Z",
            "exchange": "NSE" if ".NS" in ticker else "BSE" if ".BO" in ticker else "UNKNOWN"
        }

        # If market order, simulate immediate execution
        if order_type == "MARKET":
            result["status"] = "COMPLETE"
            result["filled_quantity"] = quantity
            result["average_price"] = price or 0.0  # Would be actual market price

        return result

    except Exception as e:
        raise VendorUnavailableError(f"Failed to place order via Kotak Neo: {str(e)}")


def get_holdings() -> List[Dict[str, any]]:
    """Get current holdings from Kotak Neo portfolio.

    Returns:
        List of dictionaries containing holding details
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://api.kotaksecurities.com"):
        raise VendorUnavailableError("Kotak Neo API is not reachable")

    # In a real implementation, this would fetch actual holdings
    # For now, return simulated data
    try:
        holdings = [
            {
                "ticker": "RELIANCE.NS",
                "company_name": "Reliance Industries Limited",
                "quantity": 50,
                "average_price": 2450.00,
                "last_price": 2480.50,
                "pnl": 1525.00,
                "pnl_percentage": 6.22,
                "product": "CNC",
                "exchange": "NSE"
            },
            {
                "ticker": "TCS.NS",
                "company_name": "Tata Consultancy Services Limited",
                "quantity": 25,
                "average_price": 3200.00,
                "last_price": 3250.75,
                "pnl": 1268.75,
                "pnl_percentage": 3.96,
                "product": "CNC",
                "exchange": "NSE"
            }
        ]

        return holdings

    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch holdings from Kotak Neo: {str(e)}")


def get_funds() -> Dict[str, float]:
    """Get available funds and margin from Kotak Neo account.

    Returns:
        Dictionary containing fund details
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://api.kotaksecurities.com"):
        raise VendorUnavailableError("Kotak Neo API is not reachable")

    # In a real implementation, this would fetch actual fund details
    # For now, return simulated data
    try:
        funds = {
            "cash": 50000.00,
            "equity_margin": 100000.00,
            "commodity_margin": 50000.00,
            "total": 150000.00,
            "used_margin": 25000.00,
            "available_margin": 125000.00
        }

        return funds

    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch funds from Kotak Neo: {str(e)}")


def get_order_history(limit: int = 50) -> List[Dict[str, any]]:
    """Get order history from Kotak Neo account.

    Args:
        limit: Maximum number of orders to return

    Returns:
        List of dictionaries containing order details
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://api.kotaksecurities.com"):
        raise VendorUnavailableError("Kotak Neo API is not reachable")

    # In a real implementation, this would fetch actual order history
    # For now, return simulated data
    try:
        orders = [
            {
                "order_id": "KTNK_123456",
                "ticker": "RELIANCE.NS",
                "action": "BUY",
                "quantity": 50,
                "price": 2450.00,
                "order_type": "LIMIT",
                "status": "COMPLETE",
                "timestamp": "2026-10-07T14:30:00Z"
            },
            {
                "order_id": "KTNK_123457",
                "ticker": "TCS.NS",
                "action": "BUY",
                "quantity": 25,
                "price": 3200.00,
                "order_type": "LIMIT",
                "status": "COMPLETE",
                "timestamp": "2026-10-06T10:15:00Z"
            }
        ]

        return orders[:limit]

    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch order history from Kotak Neo: {str(e)}")


def get_live_price(ticker: str) -> float:
    """Get live price for a ticker from Kotak Neo.

    Args:
        ticker: Stock ticker symbol with exchange suffix

    Returns:
        Current live price as float
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://api.kotaksecurities.com"):
        raise VendorUnavailableError("Kotak Neo API is not reachable")

    # In a real implementation, this would fetch actual live price
    # For now, return simulated data
    try:
        # Simulate live prices for common stocks
        live_prices = {
            "RELIANCE.NS": 2480.50,
            "TCS.NS": 3250.75,
            "INFY.NS": 1650.25,
            "HDFCBANK.NS": 1420.80,
            "ICICIBANK.NS": 890.45,
            "HINDUNILVR.NS": 2450.30,
            "ITC.NS": 420.15,
            "SBIN.NS": 580.90,
            "BHARTIARTL.NS": 850.60,
            "KOTAKBANK.NS": 1750.25
        }

        return live_prices.get(ticker, 0.0)

    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch live price from Kotak Neo: {str(e)}")