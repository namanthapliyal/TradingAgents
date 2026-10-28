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
def test_dashboard_get_config(monkeypatch):
    monkeypatch.setenv("COLAB_LLM_URL", "https://facts-test.trycloudflare.com")
    monkeypatch.setenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

    handler = DummyHandler("GET", "/api/config")
    handler.do_GET()

    assert handler.response_status == HTTPStatus.OK
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["colab_url"] == "https://facts-test.trycloudflare.com"
    assert data["local_url"] == "http://localhost:11434/v1"
