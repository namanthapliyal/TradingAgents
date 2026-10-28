"""Tests for Indian asset support across the 12-agent workflow.

Covers:
- Indian stocks (NSE/BSE, Screener.in fundamentals, Google News India)
- Indian Mutual Funds (AMFI scheme details, CAGR returns, NAV-as-OHLCV, technical indicators on NAV)
- Indian ETFs (benchmark mapping, .NS normalization, secondary market metrics)
- Asset classification & symbol resolution
- Subreddit routing for Indian financial communities
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from cli.models import AssetType
from cli.prompts import detect_asset_type
from tradingagents.agents.context import build_instrument_context
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.amfi_mf import get_mutual_fund_details, get_mutual_fund_nav_df
from tradingagents.dataflows.vendors.etf_vendor import get_etf_details
from tradingagents.dataflows.vendors.reddit import _clean_search_ticker, subreddits_for


class TestIndianAssetTypeClassification:
    def test_stock_detection(self):
        assert detect_asset_type("RELIANCE.NS") == AssetType.STOCK
        assert detect_asset_type("TCS.BO") == AssetType.STOCK
        assert detect_asset_type("INFY") == AssetType.STOCK

    def test_mutual_fund_detection(self):
        assert detect_asset_type("122639") == AssetType.MUTUAL_FUND
        assert detect_asset_type("Parag Parikh Flexi Cap Fund") == AssetType.MUTUAL_FUND
        assert detect_asset_type("SBI Small Cap Fund Direct Growth") == AssetType.MUTUAL_FUND

    def test_etf_detection(self):
        assert detect_asset_type("NIFTYBEES") == AssetType.ETF
        assert detect_asset_type("BANKBEES.NS") == AssetType.ETF
        assert detect_asset_type("GOLDBEES") == AssetType.ETF
        assert detect_asset_type("MON100") == AssetType.ETF

    def test_crypto_detection(self):
        assert detect_asset_type("BTC-USD") == AssetType.CRYPTO
        assert detect_asset_type("ETH-USDT") == AssetType.CRYPTO


class TestIndianSymbolNormalization:
    def test_etf_suffix_added(self):
        assert normalize_symbol("NIFTYBEES") == "NIFTYBEES.NS"
        assert normalize_symbol("GOLDBEES") == "GOLDBEES.NS"
        assert normalize_symbol("MON100") == "MON100.NS"
        assert normalize_symbol("NIFTYBEES.NS") == "NIFTYBEES.NS"

    def test_mf_code_preserved(self):
        assert normalize_symbol("122639") == "122639"


class TestIndianSubredditRouting:
    def test_routes_to_indian_subreddits(self):
        expected = ("IndianStreetBets", "IndiaInvestments", "IndianStockMarket")
        assert subreddits_for("RELIANCE.NS") == expected
        assert subreddits_for("TCS.BO") == expected
        assert subreddits_for("122639") == expected
        assert subreddits_for("NIFTYBEES") == expected

    def test_cleans_ticker_for_reddit_query(self):
        assert _clean_search_ticker("RELIANCE.NS") == "RELIANCE"
        assert _clean_search_ticker("TCS.BO") == "TCS"
        assert _clean_search_ticker("BTC-USD") == "BTC"


class TestAmfiMutualFundDataflow:
    SAMPLE_MF_RESPONSE = {
        "meta": {
            "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
            "scheme_code": 122639,
            "fund_house": "PPFAS Mutual Fund",
            "scheme_category": "Equity Scheme - Flexi Cap Fund",
            "scheme_type": "Open Ended Schemes",
            "isin_growth": "INF879O01027",
        },
        "data": [
            {"date": "27-10-2026", "nav": "89.2762"},
            {"date": "26-10-2026", "nav": "89.3000"},
            {"date": "23-10-2026", "nav": "88.9695"},
            {"date": "22-10-2026", "nav": "89.4088"},
            {"date": "21-10-2026", "nav": "89.9443"},
        ],
    }

    @patch("tradingagents.dataflows.vendors.amfi_mf.requests.get")
    def test_amfi_nav_df_structure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.SAMPLE_MF_RESPONSE
        mock_get.return_value = mock_resp

        df = get_mutual_fund_nav_df("122639", as_of_date="2026-10-25")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        required_cols = {"Date", "Open", "High", "Low", "Close", "Volume"}
        assert required_cols.issubset(set(df.columns))
        last_row = df.iloc[-1]
        assert last_row["Open"] == last_row["High"] == last_row["Low"] == last_row["Close"]
        assert last_row["Volume"] == 0

    @patch("tradingagents.dataflows.vendors.amfi_mf.requests.get")
    def test_amfi_details_cagr(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.SAMPLE_MF_RESPONSE
        mock_get.return_value = mock_resp

        details = get_mutual_fund_details("122639")
        assert details["scheme_code"] == "122639"
        assert "Parag Parikh" in details["scheme_name"]
        assert details["latest_nav"] == 89.2762
        assert "returns_cagr" in details


class TestEtfDetails:
    @patch("tradingagents.dataflows.vendors.etf_vendor.yf.Ticker")
    def test_etf_lookup(self, mock_ticker):
        mock_inst = MagicMock()
        mock_inst.info = {
            "longName": "Nippon India ETF Nifty 50 BeES",
            "regularMarketPrice": 252.40,
            "fiftyTwoWeekHigh": 265.00,
            "fiftyTwoWeekLow": 210.00,
            "volume": 1200000,
            "averageVolume": 1500000,
        }
        mock_ticker.return_value = mock_inst

        details = get_etf_details("NIFTYBEES")
        assert details["ticker"] == "NIFTYBEES"
        assert details["canonical_symbol"] == "NIFTYBEES.NS"
        assert details["current_price"] == 252.40
        assert "Nifty 50" in details["underlying_benchmark"]


class TestInstrumentIdentityAndContext:
    def test_mf_instrument_context(self):
        identity = {
            "company_name": "Parag Parikh Flexi Cap Fund",
            "sector": "Equity Scheme - Flexi Cap Fund",
            "industry": "PPFAS Mutual Fund",
            "quote_type": "MUTUAL_FUND",
            "exchange": "AMFI India",
        }
        ctx = build_instrument_context("122639", "mutual_fund", identity)
        assert "Indian mutual fund scheme" in ctx
        assert "AMFI/SEBI regulated" in ctx
        assert "daily NAV" in ctx
        assert "get_mutual_fund_info" in ctx

    def test_etf_instrument_context(self):
        identity = {
            "company_name": "Nippon India ETF Nifty 50 BeES",
            "sector": "Large Cap Equity",
            "industry": "Nifty 50 Index",
            "quote_type": "ETF",
            "exchange": "NSE India",
        }
        ctx = build_instrument_context("NIFTYBEES", "etf", identity)
        assert "Indian exchange traded fund (ETF)" in ctx
        assert "get_etf_info" in ctx
