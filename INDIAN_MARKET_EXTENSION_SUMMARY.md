# Indian Market Stock Analysis Agent - Extension Summary

This document summarizes the extensions made to the TradingAgents framework to create an Indian market-specific stock analysis agent.

## Overview

The original TradingAgents framework has been extended with comprehensive Indian market capabilities including:
- Indian market data vendors (Screener.in, Moneycontrol, TradingView)
- Brokerage API integrations (Kotak Neo, Interactive Brokers)
- Wallet and portfolio management
- Intraday and long-term trading strategies
- Institutional flow analysis (FII/DII, bulk/block deals, mutual fund flows)
- Mutual fund analysis (NAV tracking, expense ratios, fund manager analysis)
- Alerting and notification system

## Directory Structure

```
tradingagents/
├── dataflows/
│   └── vendors/
│       ├── screener_in/          # Screener.in fundamental data
│       ├── moneycontrol/         # Moneycontrol fundamental data
│       ├── tradingview/          # TradingView technical indicators
│       ├── kotak_neo/            # Kotak Neo brokerage API
│       └── interactive_brokers/  # Interactive Brokers API
├── wallet/
│   └── manager.py                # Wallet and portfolio management
├── strategies/
│   ├── intraday.py               # Intraday trading strategy
│   └── long_term.py              # Long-term investment strategy
├── analysis/
│   ├── institutional/
│   │   └── flow_analyzer.py      # FII/DII, bulk/block deals, mutual fund flows
│   └── mutual_funds/
│       └── analyzer.py           # Mutual fund NAV, returns, expense ratios
├── alerting/
│   └── manager.py                # Alerting and notification system
└── main.py                       # Updated main entry point with demonstration
```

## Key Features Implemented

### 1. Indian Market Data Vendors
- **Screener.in**: Fundamental data for Indian stocks (PE, PB, ROE, etc.)
- **Moneycontrol**: Alternative fundamental data source
- **TradingView**: Technical indicators (RSI, MACD, Bollinger Bands, Moving Averages)

### 2. Brokerage API Integrations
- **Kotak Neo**: Primary broker for algo trading (order placement, portfolio management, funds)
- **Interactive Brokers**: Secondary global broker option

### 3. Wallet & Portfolio Management
- Multi-currency wallet support
- Position tracking and management
- Risk-based position sizing
- Paper trading and live trading modes
- Transaction history tracking

### 4. Trading Strategies
- **Intraday Strategy**: Technical analysis-based momentum strategy with risk management
- **Long-Term Strategy**: Fundamental analysis-based value investing approach

### 5. Institutional Flow Analysis
- **FII/DII Tracking**: Foreign and Domestic Institutional Investor flows
- **Bulk/Block Deal Analysis**: Large transaction monitoring
- **Mutual Fund Flows**: Industry-wide mutual fund inflow/outflow analysis

### 6. Mutual Fund Analysis
- **NAV Tracking**: Current and historical Net Asset Values
- **Returns Analysis**: Performance across multiple time periods
- **Expense Ratio Analysis**: Cost efficiency evaluation
- **Fund Manager Analysis**: Experience and performance evaluation
- **Risk Analysis**: Volatility, beta, Sharpe ratio, etc.

### 7. Alerting System
- Price target alerts (above/below thresholds)
- Sentiment change alerts
- Volume spike alerts
- Technical breakout alerts (resistance/support)
- Institutional flow alerts
- Configurable cooldown periods to prevent alert spam

## Configuration Updates

Updated `tradingagents/default_config.py` to include:
- New data vendors for fundamental data: `screener_in`, `moneycontrol`
- New data vendors for technical indicators: `tradingview`
- New brokerage vendors: `kotak_neo`, `interactive_brokers`
- Indian market benchmark mapping (.NS -> ^NSEI, .BO -> ^BSESN)

## Usage

The extended framework can be used in two modes:

1. **Paper Trading Mode** (default): Simulated trading for strategy testing
2. **Live Trading Mode**: Actual order execution via broker APIs

To switch to live trading, set `paper_trading=False` in the WalletManager configuration and configure valid API credentials.

## Example Workflow

1. Initialize wallet with initial capital
2. Analyze stocks using fundamental, technical, and sentiment analysis
3. Generate trading signals using intraday or long-term strategies
4. Execute trades via connected broker API (Kotak Neo/Interactive Brokers)
5. Monitor positions and institutional flows
6. Receive alerts for significant events
7. Rebalance portfolio based on analysis and risk parameters

## Dependencies

The extension relies on the original TradingAgents framework dependencies plus:
- requests: For API calls to Indian market data sources
- pandas: For data manipulation and analysis
- python-dotenv: For environment variable management

Note: The original framework requires `langchain-core` and related packages for LLM functionality.

## Files Created/Modified

**New Files:**
- `tradingagents/dataflows/vendors/screener_in/`
- `tradingagents/dataflows/vendors/moneycontrol/`
- `tradingagents/dataflows/vendors/tradingview/`
- `tradingagents/dataflows/vendors/kotak_neo/`
- `tradingagents/wallet/manager.py`
- `tradingagents/strategies/intraday.py`
- `tradingagents/strategies/long_term.py`
- `tradingagents/analysis/institutional/flow_analyzer.py`
- `tradingagents/analysis/mutual_funds/analyzer.py`
- `tradingagents/alerting/manager.py`

**Modified Files:**
- `tradingagents/default_config.py` - Added Indian market vendors
- `tradingagents/main.py` - Updated with comprehensive demonstration

## Future Enhancements

1. Real-time data streaming capabilities
2. Advanced machine learning models for prediction
3. Portfolio optimization algorithms
4. Tax-loss harvesting strategies
5. Integration with additional Indian data sources
6. Enhanced backtesting framework
7. Mobile application notifications