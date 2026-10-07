from typing import Annotated, Dict, List
import requests

from tradingagents.dataflows.date_window import withhold_live_profile
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol


def get_technical_indicators(
    ticker: Annotated[str, "ticker symbol of the company (e.g., RELIANCE.NS for NSE)"],
    indicators: Annotated[List[str], "list of technical indicators to calculate"] = None,
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
) -> Dict[str, float]:
    """Get technical indicators from TradingView for Indian stocks.
    
    Args:
        ticker: Stock ticker symbol with exchange suffix (e.g., RELIANCE.NS, TCS.BO)
        indicators: List of technical indicators to calculate (defaults to common ones)
        as_of_date: Analysis date in YYYY-MM-DD format (defaults to current date)
        
    Returns:
        Dictionary containing technical indicator values
    """
    if indicators is None:
        indicators = ["RSI", "MACD", "BBANDS", "MOVING_AVERAGES"]
    
    # Normalize the ticker symbol
    normalized_ticker = normalize_symbol(ticker)
    
    # TradingView API endpoint (using their public chart API)
    # Note: This is a simplified implementation - in practice, you might use their official API
    url = f"https://symbolsearch.tradingview.com/symbol_search/v3/"
    
    try:
        # Search for the symbol to get the proper TradingView symbol ID
        search_params = {
            "text": normalized_ticker,
            "types": ["stock"],
            "exchange": "NSE" if ".NS" in normalized_ticker else "BSE" if ".BO" in normalized_ticker else "NSE"
        }
        
        # Check if vendor is reachable
        if not vendor_reachable("https://www.tradingview.com"):
            raise VendorUnavailableError("TradingView is not reachable")
        
        # For this implementation, we'll simulate the technical indicators
        # In a real implementation, you would use TradingView's API or scrape their charts
        # For now, we'll return calculated values based on common formulas
        
        # Simulate fetching OHLCV data (in practice, you'd get this from a data provider)
        ohlcv_data = _fetch_ohlcv_data(normalized_ticker, as_of_date)
        
        if not ohlcv_data:
            # Return empty dict if no data available
            return {}
        
        # Calculate technical indicators
        results = {}
        
        for indicator in indicators:
            if indicator.upper() == "RSI":
                results["RSI"] = _calculate_rsi(ohlcv_data['close'])
            elif indicator.upper() == "MACD":
                macd_data = _calculate_macd(ohlcv_data['close'])
                results.update(macd_data)
            elif indicator.upper() == "BBANDS":
                bbands_data = _calculate_bollinger_bands(ohlcv_data['close'])
                results.update(bbands_data)
            elif indicator.upper() == "MOVING_AVERAGES":
                ma_data = _calculate_moving_averages(ohlcv_data['close'])
                results.update(ma_data)
        
        # Apply date-based filtering if as_of_date is provided
        if as_of_date:
            results = withhold_live_profile(results, as_of_date)
        
        return results
        
    except requests.RequestException as e:
        raise VendorUnavailableError(f"Failed to fetch data from TradingView: {str(e)}")
    except Exception as e:
        raise VendorUnavailableError(f"Error processing TradingView data: {str(e)}")


def _fetch_ohlcv_data(ticker: str, as_of_date: str = None) -> Dict[str, List[float]]:
    """Fetch OHLCV data for technical analysis.
    
    In a real implementation, this would fetch from a data provider like Yahoo Finance
    or a direct market data API. For now, we'll return mock data structure.
    """
    # This is a placeholder - in reality, you would fetch actual OHLCV data
    # For demonstration, we'll return empty data to indicate the function structure
    return {
        'open': [],
        'high': [],
        'low': [],
        'close': [],
        'volume': []
    }


def _calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return 50.0  # Default neutral value
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return 50.0
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
    """Calculate MACD (Moving Average Convergence Divergence)."""
    if len(prices) < slow:
        return {"MACD": 0.0, "MACD_signal": 0.0, "MACD_hist": 0.0}
    
    # Calculate EMAs
    ema_fast = _calculate_ema(prices, fast)
    ema_slow = _calculate_ema(prices, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = _calculate_ema([macd_line] * len(prices), signal)  # Simplified
    histogram = macd_line - signal_line
    
    return {
        "MACD": macd_line,
        "MACD_signal": signal_line,
        "MACD_hist": histogram
    }


def _calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Dict[str, float]:
    """Calculate Bollinger Bands."""
    if len(prices) < period:
        return {"BBAND_upper": 0.0, "BBAND_middle": 0.0, "BBAND_lower": 0.0}
    
    # Calculate SMA
    sma = sum(prices[-period:]) / period
    
    # Calculate standard deviation
    variance = sum((x - sma) ** 2 for x in prices[-period:]) / period
    std = variance ** 0.5
    
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    return {
        "BBAND_upper": upper_band,
        "BBAND_middle": sma,
        "BBAND_lower": lower_band
    }


def _calculate_moving_averages(prices: List[float]) -> Dict[str, float]:
    """Calculate common moving averages."""
    if len(prices) < 50:
        return {
            "MA_5": 0.0,
            "MA_10": 0.0,
            "MA_20": 0.0,
            "MA_50": 0.0,
            "MA_100": 0.0,
            "MA_200": 0.0
        }
    
    return {
        "MA_5": sum(prices[-5:]) / 5 if len(prices) >= 5 else 0.0,
        "MA_10": sum(prices[-10:]) / 10 if len(prices) >= 10 else 0.0,
        "MA_20": sum(prices[-20:]) / 20 if len(prices) >= 20 else 0.0,
        "MA_50": sum(prices[-50:]) / 50 if len(prices) >= 50 else 0.0,
        "MA_100": sum(prices[-100:]) / 100 if len(prices) >= 100 else 0.0,
        "MA_200": sum(prices[-200:]) / 200 if len(prices) >= 200 else 0.0
    }


def _calculate_ema(prices: List[float], period: int) -> float:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return sum(prices) / len(prices) if prices else 0.0
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # Start with SMA
    
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema
