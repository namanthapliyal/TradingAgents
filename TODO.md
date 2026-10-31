# Tradex Agent — Project TODO List

## 📌 Pending Tasks

- [ ] **Fix ETF Screener & Mutual Fund Analyzer in Web UI (`cli/web_app.py`)** *(Postponed per user request)*
  - **Mutual Fund Details Key Alignment**: The backend `get_mutual_fund_details` in `tradingagents/dataflows/vendors/amfi_mf.py` returns flat fields (`scheme_name`, `fund_house`, `category`, `latest_nav`, `nav_date`, `returns_cagr`), whereas the frontend JS in `cli/web_app.py` expects nested `data.meta.*` and `data.returns.*`. Align the response model and frontend parser.
  - **ETF Screener Fallback & Data Quality**: Ensure `get_etf_details` handles secondary market quotes reliably and falls back gracefully if Yahoo Finance rate-limits.
  - **UI Verification**: Confirm 52-week range bars, trailing returns cards, and quick buttons display seamlessly.

---

## ✅ Completed Tasks

- [x] **Context Window Expansion to 16k Tokens**: Injected `options: {"num_ctx": 16384}` into `LocalCompatibleChatOpenAI` and documented Colab 16k setup.
- [x] **Direct PM Decision Fallback**: Avoid full 15-agent restart on Phase V stream errors by synthesizing directly from accumulated debate state.
- [x] **Report Generation Time**: Added `Report generation time: <duration>` to markdown header, HTML page header, and web dashboard logs.
- [x] **Indian Financial Subreddit Routing**: Bare Indian tickers route to `r/IndianStreetBets`, `r/IndiaInvestments`, `r/IndianStockMarket` with global fallback.
- [x] **Macro Commodities Pre-fetch**: Injected macro snapshot into News Analyst prompt for metals/commodities/dollar dynamics.
- [x] **Multi-Vendor News Fallback**: Yahoo Finance -> Google News RSS -> DuckDuckGo search fallback cascade.
- [x] **Pandas4Warning Suppression**: Overrode yfinance internal deprecation warnings filter for clean logs.
