"""Unit tests for the Tradex Agent Web Dashboard."""

import io
import json
from http import HTTPStatus

import pytest

from cli.web_app import GLOBAL_STATE, WebDashboardHandler


class DummyRequest:
    def __init__(self, method: str, path: str, body: bytes = b"") -> None:
        self.method = method
        self.path = path
        self.body = body

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.body)


class DummyHandler(WebDashboardHandler):
    """Subclass of WebDashboardHandler for testing without live TCP sockets."""

    def __init__(self, method: str, path: str, body: bytes = b"") -> None:
        self.requestline = f"{method} {path} HTTP/1.1"
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.1"
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.response_status = None
        self.response_headers = {}

    def send_response(self, code, message=None):
        self.response_status = code

    def send_header(self, keyword, value):
        self.response_headers[keyword] = value

    def end_headers(self):
        pass


@pytest.mark.unit
def test_web_state_snapshot():
    GLOBAL_STATE.reset()
    assert GLOBAL_STATE.status == "idle"

    GLOBAL_STATE.add_message("System", "Testing message", "system")
    snapshot = GLOBAL_STATE.get_snapshot()

    assert snapshot["status"] == "idle"
    assert snapshot["total_messages"] == 1
    assert snapshot["new_messages"][0]["sender"] == "System"
    assert snapshot["new_messages"][0]["content"] == "Testing message"


@pytest.mark.unit
def test_dashboard_get_index():
    handler = DummyHandler("GET", "/")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    body = handler.wfile.getvalue().decode("utf-8")
    assert "Tradex Agent" in body
    assert "Analysis Parameters" in body
    assert "Google Colab" in body
    assert "Local Ollama" in body


@pytest.mark.unit
def test_dashboard_get_status():
    GLOBAL_STATE.reset()
    handler = DummyHandler("GET", "/api/status?offset=0")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["status"] == "idle"
    assert "agent_statuses" in data


@pytest.mark.unit
def test_dashboard_live_file_logging(tmp_path):
    log_file = tmp_path / "test_run.log"
    GLOBAL_STATE.reset()
    GLOBAL_STATE.log_file_path = log_file

    GLOBAL_STATE.add_message("MARKET", "Analyzing technical indicators...", "tool")
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "[MARKET]" in content
    assert "Analyzing technical indicators..." in content

    handler = DummyHandler("GET", "/api/log")
    handler.do_GET()
    assert handler.response_status == HTTPStatus.OK
    assert b"Analyzing technical indicators..." in handler.wfile.getvalue()


@pytest.mark.unit
def test_dashboard_get_config(monkeypatch):
    monkeypatch.setenv("COLAB_LLM_URL", "https://facts-test.trycloudflare.com")
    monkeypatch.setenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

    handler = DummyHandler("GET", "/api/config")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["colab_url"] == "https://facts-test.trycloudflare.com"
    assert data["local_url"] == "http://localhost:11434/v1"


@pytest.mark.unit
def test_dashboard_download_html_report():
    GLOBAL_STATE.reset()
    GLOBAL_STATE.ticker = "VEDPOWER"
    GLOBAL_STATE.trade_date = "2026-10-31"
    GLOBAL_STATE.report_html = "<html><body><h1>Report</h1></body></html>"

    handler = DummyHandler("GET", "/api/report/download?format=html")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    assert (
        'attachment; filename="TradingAgents_Report_VEDPOWER_2026-10-31.html"'
        in handler.response_headers.get("Content-Disposition", "")
    )
    assert handler.response_headers.get("Content-Type") == "text/html; charset=utf-8"
    assert b"<h1>Report</h1>" in handler.wfile.getvalue()


@pytest.mark.unit
def test_dashboard_download_md_report():
    GLOBAL_STATE.reset()
    GLOBAL_STATE.ticker = "VEDPOWER"
    GLOBAL_STATE.trade_date = "2026-10-31"
    GLOBAL_STATE.report_md = "# VEDPOWER Report"

    handler = DummyHandler("GET", "/api/report/download?format=md")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    assert (
        'attachment; filename="TradingAgents_Report_VEDPOWER_2026-10-31.md"'
        in handler.response_headers.get("Content-Disposition", "")
    )
    assert handler.response_headers.get("Content-Type") == "text/markdown; charset=utf-8"
    assert b"# VEDPOWER Report" in handler.wfile.getvalue()


@pytest.mark.unit
def test_dashboard_reports_list():
    handler = DummyHandler("GET", "/api/reports/list")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert isinstance(data, list)


@pytest.mark.unit
def test_dashboard_etf_details(monkeypatch):
    import tradingagents.dataflows.vendors.etf_vendor as etf_mod

    mock_details = {
        "ticker": "NIFTYBEES",
        "canonical_symbol": "NIFTYBEES.NS",
        "name": "Nippon India ETF Nifty 50 BeES",
        "current_price": 262.89,
        "52_week_high": 302.25,
        "52_week_low": 251.7,
        "volume": 5671007,
        "average_volume": 6590948,
        "underlying_benchmark": "Nifty 50 Index",
        "asset_class": "Large Cap Equity",
        "exchange": "NSE / BSE India",
    }
    monkeypatch.setattr(etf_mod, "get_etf_details", lambda ticker: mock_details)

    handler = DummyHandler("GET", "/api/etf/details?ticker=NIFTYBEES")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["ticker"] == "NIFTYBEES"
    assert "current_price" in data
    assert "underlying_benchmark" in data


@pytest.mark.unit
def test_dashboard_mf_details(monkeypatch):
    import tradingagents.dataflows.vendors.amfi_mf as mf_mod

    mock_details = {
        "meta": {"scheme_name": "Parag Parikh Flexi Cap Fund", "fund_house": "PPFAS Mutual Fund"},
        "current_nav": "82.50",
        "returns": {"1M": 1.5, "1Y": 24.2, "3Y": 19.8, "5Y": 22.1},
    }
    monkeypatch.setattr(mf_mod, "get_mutual_fund_details", lambda code: mock_details)

    handler = DummyHandler("GET", "/api/mf/details?code=122639")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["meta"]["scheme_name"] == "Parag Parikh Flexi Cap Fund"
    assert data["current_nav"] == "82.50"
    assert data["returns"]["1Y"] == 24.2


@pytest.mark.unit
def test_dashboard_portfolio_analyze_and_download():
    payload = json.dumps(
        {
            "holdings": [{"ticker": "RELIANCE.NS", "quantity": 10, "buy_price": 2800.0}],
            "cash": 15000.0,
        }
    ).encode("utf-8")

    handler = DummyHandler("POST", "/api/portfolio/analyze", body=payload)
    handler.do_POST()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "summary" in data
    assert "holdings" in data
    assert "html_report" in data
    assert data["summary"]["holdings_count"] == 1

    # Verify download of portfolio HTML
    dl_handler = DummyHandler("GET", "/api/portfolio/download")
    dl_handler.do_GET()

    assert dl_handler.response_status == HTTPStatus.OK
    assert "TradingAgents_Portfolio_Report_" in dl_handler.response_headers.get(
        "Content-Disposition", ""
    )
    assert b"Portfolio Health" in dl_handler.wfile.getvalue()
