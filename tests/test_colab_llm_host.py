"""Tests for Google Colab hosted LLM and self-hosted local Ollama switching."""

import pytest

from cli.selections import resolve_llm_host, unattended_gaps
from tradingagents.default_config import build_default_config
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import LocalCompatibleChatOpenAI


@pytest.mark.unit
def test_resolve_llm_host_flags():
    assert resolve_llm_host({"colab": True}) == "colab"
    assert resolve_llm_host({"local": True}) == "local"
    assert resolve_llm_host({"host": "colab"}) == "colab"
    assert resolve_llm_host({"host": "google-colab"}) == "colab"
    assert resolve_llm_host({"host": "local"}) == "local"
    assert resolve_llm_host({"host": "self-hosted"}) == "local"
    assert resolve_llm_host({}) is None


@pytest.mark.unit
def test_resolve_llm_host_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_HOST", "colab")
    assert resolve_llm_host({}) == "colab"

    # Explicit flag overrides env
    assert resolve_llm_host({"local": True}) == "local"

    monkeypatch.setenv("TRADINGAGENTS_LLM_HOST", "self-hosted")
    assert resolve_llm_host({}) == "local"


@pytest.mark.unit
def test_default_config_colab_preset(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_HOST", "colab")
    monkeypatch.setenv("COLAB_LLM_URL", "https://facts-test.trycloudflare.com")
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)
    monkeypatch.delenv("COLAB_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("COLAB_DEEP_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LLM_BACKEND_URL", raising=False)

    cfg = build_default_config()
    assert cfg["llm_provider"] == "colab"
    assert cfg["quick_think_llm"] == "qwen3:8b"
    assert cfg["deep_think_llm"] == "deepseek-r1:14b"
    assert cfg["backend_url"] == "https://facts-test.trycloudflare.com"


@pytest.mark.unit
def test_default_config_local_preset(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_HOST", "local")
    monkeypatch.setenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)
    monkeypatch.delenv("COLAB_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("COLAB_DEEP_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LLM_BACKEND_URL", raising=False)

    cfg = build_default_config()
    assert cfg["llm_provider"] == "ollama"
    assert cfg["quick_think_llm"] == "qwen2.5-coder:1.5b"
    assert cfg["deep_think_llm"] == "qwen2.5-coder:7b"
    assert cfg["backend_url"] == "http://localhost:11434/v1"


@pytest.mark.unit
def test_unattended_gaps_with_host(monkeypatch):
    flags = {
        "ticker": "VEDPOWER",
        "date": "2026-10-28",
        "analysts": "market,news",
        "save": True,
        "show": False,
        "colab": True,
    }
    monkeypatch.setenv("TRADINGAGENTS_OUTPUT_LANGUAGE", "English")
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "1")
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)

    # When colab flag is set, provider and models are not missing gaps!
    gaps = unattended_gaps(flags)
    assert "TRADINGAGENTS_LLM_PROVIDER" not in gaps
    assert "TRADINGAGENTS_QUICK_THINK_LLM or TRADINGAGENTS_DEEP_THINK_LLM" not in gaps


@pytest.mark.unit
def test_colab_llm_client_headers_and_url(monkeypatch):
    monkeypatch.setenv("COLAB_LLM_URL", "https://facts-almost-depending-boulder.trycloudflare.com")
    monkeypatch.setenv("COLAB_LLM_API_KEY", "sk-colab-secret-key-12345")

    client = create_llm_client(provider="colab", model="qwen3:8b")
    llm = client.get_llm()
    assert isinstance(llm, LocalCompatibleChatOpenAI)
    # Check that /v1 is automatically appended
    assert str(llm.openai_api_base) == "https://facts-almost-depending-boulder.trycloudflare.com/v1"
    # Check that bearer auth key is passed
    key = (
        llm.openai_api_key.get_secret_value()
        if hasattr(llm.openai_api_key, "get_secret_value")
        else llm.openai_api_key
    )
    assert key == "sk-colab-secret-key-12345"
