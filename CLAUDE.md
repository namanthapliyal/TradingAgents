# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🔧 Common Development Commands

### Installation & Setup
```bash
# Install in development mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

### Running the Application
```bash
# Run the main demonstration
python -m tradingagents.main

# Or using the installed command
tradingagents
```

### Testing
```bash
# Run all tests
pytest

# Run unit tests only (excluding integration)
pytest -m "not integration"

# Run a specific test file
pytest tests/test_specific_module.py

# Run a specific test function
pytest tests/test_specific_module.py::test_function_name
```

### Linting & Code Quality
```bash
# Check code style with ruff
ruff check .

# Automatically fix fixable issues
ruff check --fix .

# Format code
ruff format .
```

### Dependency Management
```bash
# Update dependencies (check pyproject.toml for version ranges)
pip list --outdated

# Update to latest compatible versions
pip install --upgrade .
```

## 🏗️ Code Architecture & Structure

### High-Level Organization
The codebase follows a modular architecture centered around the `tradingagents` package:

```
tradingagents/
├── dataflows/          # Data ingestion layer
│   └── vendors/        # Market data providers
│       ├── screener_in/      # Fundamental data (Screener.in)
│       ├── moneycontrol/     # Fundamental data (Moneycontrol)
│       ├── tradingview/      # Technical indicators (TradingView)
│       ├── kotak_neo/        # Brokerage API (Kotak Neo)
│       └── interactive_brokers/ # Brokerage API (Interactive Brokers)
├── wallet/             # Portfolio & risk management
│   └── manager.py      # Wallet manager with position sizing & controls
├── strategies/         # Trading strategies
│   ├── intraday.py     # Technical momentum strategy
│   └── long_term.py    # Fundamental value strategy
├── analysis/           # Analytical modules
│   ├── institutional/  # FII/DII, bulk/block deals, mutual fund flows
│   │   └── flow_analyzer.py
│   └── mutual_funds/   # Mutual fund analysis
│       └── analyzer.py
├── alerting/           # Notification system
│   └── manager.py      # Alert creation, monitoring & delivery
├── main.py             # Entry point with demonstration workflow
└── default_config.py   # Configuration including Indian market vendors
```

### Key Architectural Patterns

1. **Dataflow/Vendors Pattern**: 
   - Each vendor (Screener.in, Moneycontrol, etc.) implements a consistent interface for data retrieval
   - Separation of concerns: fundamental data vs technical indicators vs brokerage APIs
   - Easy to extend with new data sources

2. **Wallet-Centric Design**:
   - Portfolio management is centralized in `wallet/manager.py`
   - Supports both paper trading (simulation) and live trading modes
   - Includes risk controls for position sizing and diversification

3. **Strategy Analysis Separation**:
   - Strategies (`strategies/`) generate trading signals
   - Analysis modules (`analysis/`) provide deeper market insights
   - Alerting system (`alerting/`) monitors conditions and triggers notifications

4. **Extension Points**:
   - New data vendors can be added under `dataflows/vendors/`
   - New strategies can be added to `strategies/`
   - New analysis modules can be added under `analysis/`
   - Alert types can be extended in `alerting/manager.py`

### Data Flow
```
[Market Data] → [Data Collectors/Vendors] → [Processing Engine]
                              ↓
                      [Strategy Engine] ← [Backtesting Framework] (planned)
                              ↓
                      [Execution Engine] → [Broker APIs]
                              ↓
                      [Wallet Manager] ↔ [Performance Tracker] (planned)
                              ↓
                      [Alert Manager] → [Delivery Channels] (email/SMS/webhook)
                              ↓
                      [Dashboard] ←→ [Visualization Engine] (planned)
```

## 📚 Important Files to Review

- **README.md**: Project overview and basic usage
- **NEXT_STEPS_PLAN.md**: Enhancement roadmap for future development
- **INDIAN_MARKET_EXTENSION_SUMMARY.md**: Summary of current Indian market extensions
- **pyproject.toml**: Project configuration, dependencies, and scripts
- **tradingagents/main.py**: Entry point demonstrating the full workflow
- **tradingagents/default_config.py**: Configuration showing enabled vendors

## ⚠️ Important Notes

- The project requires Python 3.11+
- API credentials for brokers (Kotak Neo, Interactive Brokers) must be configured via environment variables or config files for live trading
- Paper trading mode is enabled by default for safe strategy testing
- All data vendors include error handling for API unavailability