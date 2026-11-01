# Tradex Agent — Project TODO List

## 📌 Pending Tasks

*(No blocking pending tasks)*

---

## ✅ Completed Tasks

- [x] **Dynamic ETF Peer Discovery & Outer Feed Integration**:
  - Removed all hardcoded ETF peer lists (`ETF_PEERS_MAP`).
  - Added real-time outer source integration with NSE India (`/api/etf`), providing live orderflow turnover (`trdVal`), day change %, and underlying benchmark assets.
  - Dynamically clusters ETFs (Gold, Silver, Banking, IT, Auto, Pharma, CPSE/PSU, Nifty 50, etc.) and ranks peer alternatives by live turnover descending.
  - Enriched ETF Screener card with Day Range, Turnover (₹ Cr), Liquidity Rating, 50/200 DMA, 14-day RSI, and clickable peer alternative chips.
- [x] **Mutual Fund Analyzer Dual-Schema Compatibility**:
  - Aligned `/api/mf/details` and frontend `fetchMFDetails` to seamlessly support both flat AMFI keys (`latest_nav`, `nav_date`, `returns_cagr`, `scheme_name`, `fund_house`, `category`) and nested frontend keys (`current_nav`, `last_updated`, `returns`, `meta`).
  - Fixes missing NAV (₹0.00) and N/A CAGR returns for scheme searches (e.g. "Parag Parikh Flexi Cap").
- [x] **12-Agent Multi-Agent Workflow Adaptation for MFs and ETFs**:
  - Added Asset Class Mode selector (`Auto-Detect`, `Equity Stock`, `Indian Mutual Fund`, `Exchange Traded Fund`, `Crypto`) to Analysis Parameters.
  - Forwarded `asset_type` to `_run_pipeline_worker` and `graph.create_run_state`, stopping hardcoded `"stock"` state initialization.
  - Added **"Run 12-Agent Analysis"** one-click buttons on both the Mutual Fund card and ETF card to immediately run the 12-agent research, bull/bear debate, risk committee, and portfolio manager on mutual fund schemes and ETFs.

- [x] **Context Window Expansion to 16k Tokens**: Injected `options: {"num_ctx": 16384}` into `LocalCompatibleChatOpenAI` and documented Colab 16k setup.
- [x] **Direct PM Decision Fallback**: Avoid full 15-agent restart on Phase V stream errors by synthesizing directly from accumulated debate state.
- [x] **Report Generation Time**: Added `Report generation time: <duration>` to markdown header, HTML page header, and web dashboard logs.
- [x] **Indian Financial Subreddit Routing**: Bare Indian tickers route to `r/IndianStreetBets`, `r/IndiaInvestments`, `r/IndianStockMarket` with global fallback.
- [x] **Macro Commodities Pre-fetch**: Injected macro snapshot into News Analyst prompt for metals/commodities/dollar dynamics.
- [x] **Multi-Vendor News Fallback**: Yahoo Finance -> Google News RSS -> DuckDuckGo search fallback cascade.
- [x] **Pandas4Warning Suppression**: Overrode yfinance internal deprecation warnings filter for clean logs.

