from typing import Annotated, Dict, List, Optional
import requests
import json

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable


def place_order(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE.NS for NSE)"],
    action: Annotated[str, "BUY or SELL"],
    quantity: Annotated[int, "number of shares to trade"],
    order_type: Annotated[str, "MKT, LMT, STP, STP LMT, REL, TRAIL, VOL, PEG"] = "MKT",
    price: Annotated[Optional[float], "price for LMT or STP LMT orders"] = None,
    aux_price: Annotated[Optional[float], "auxiliary price for STP or STP LMT orders"] = None,
    tif: Annotated[str, "Time in force: DAY, GTC, IOC, OPG, GTD, GTX"] = "DAY"
) -> Dict[str, any]:
    """Place a trading order via Interactive Brokers API.
    
    Args:
        ticker: Stock ticker symbol with exchange suffix
        action: BUY or SELL
        quantity: Number of shares
        order_type: MKT (Market), LMT (Limit), STP (Stop), STP LMT (Stop Limit), etc.
        price: Price for LMT/STP LMT orders
        aux_price: Auxiliary price for STP/STP LMT orders (stop price for STP)
        tif: Time in force
        
    Returns:
        Dictionary containing order details and status
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://www.interactivebrokers.com"):
        raise VendorUnavailableError("Interactive Brokers API is not reachable")
    
    # In a real implementation, you would:
    # 1. Load API credentials from secure storage/environment
    # 2. Connect to IB Gateway or TWS
    # 3. Make actual API call to place order
    
    # For now, we'll return a simulated response
    # In production, this would be replaced with actual API calls
    
    try:
        # Simulate order placement
        order_id = f"IB_{hash(ticker + action + str(quantity)) % 1000000:06d}"
        
        result = {
            "order_id": order_id,
            "status": "Submitted",
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
            "aux_price": aux_price,
            "tif": tif,
            "timestamp": "2026-10-08T10:30:00Z",
            "exchange": "NSE" if ".NS" in ticker else "BSE" if ".BO" in ticker else "UNKNOWN"
        }
        
        # If market order, simulate immediate execution
        if order_type == "MKT":
            result["status"] = "Filled"
            result["filled_quantity"] = quantity
            result["average_price"] = price or 0.0  # Would be actual market price
        
        return result
        
    except Exception as e:
        raise VendorUnavailableError(f"Failed to place order via Interactive Brokers: {str(e)}")


def get_portfolio() -> List[Dict[str, any]]:
    """Get current portfolio from Interactive Brokers account.
    
    Returns:
        List of dictionaries containing portfolio details
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://www.interactivebrokers.com"):
        raise VendorUnavailableError("Interactive Brokers API is not reachable")
    
    # In a real implementation, this would fetch actual portfolio
    # For now, return simulated data
    try:
        portfolio = [
            {
                "ticker": "RELIANCE.NS",
                "company_name": "Reliance Industries Limited",
                "position": 50,
                "market_price": 2480.50,
                "market_value": 124025.00,
                "average_cost": 2450.00,
                "unrealized_pnl": 1525.00,
                "unrealized_pnl_percent": 6.22,
                "currency": "INR"
            },
            {
                "ticker": "TCS.NS",
                "company_name": "Tata Consultancy Services Limited",
                "position": 25,
                "market_price": 3250.75,
                "market_value": 81268.75,
                "average_cost": 3200.00,
                "unrealized_pnl": 1268.75,
                "unrealized_pnl_percent": 3.96,
                "currency": "INR"
            }
        ]
        
        return portfolio
        
    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch portfolio from Interactive Brokers: {str(e)}")


def get_account_summary() -> Dict[str, float]:
    """Get account summary from Interactive Brokers.
    
    Returns:
        Dictionary containing account details
    """
    # Check if vendor is reachable
    if not vendor_reachable("https://www.interactivebrokers.com"):
        raise VendorUnavailableError("Interactive Brokers API is not reachable")
    
    # In a real implementation, this would fetch actual account summary
    # For now, return simulated data
    try:
        account_summary = {
            "netliquidation": 200000.00,
            "totalcashvalue": 50000.00,
            "buyingpower": 150000.00,
            "grosspositionvalue": 205293.75,
            "maintmarginreq": 50000.00,
            "availablefunds": 150000.00
        }
        
        return account_summary
        
    except Exception as e:
        raise VendorUnavailableError(f"Failed to fetch account summary from Interactive Brokers: {str(e)}")
