"""Web UI Dashboard for TradingAgents.

Runs a local web server (pure standard library http.server) providing an
interactive web browser UI to configure runs, monitor agent progress in real time
without terminal truncation, and view/download full markdown and HTML reports.
Supports 4 specialized financial modules:
1. Equities Ticker Analysis (Multi-agent institutional workflow)
2. Indian Mutual Funds Analysis (AMFI NAV, returns, risk profiling)
3. Indian ETF Screener (Tracking error, liquidity, 52-week range)
4. Indian Stock Portfolio Analyzer (Valuation, HHI concentration, rebalancing)
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import threading
import webbrowser
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from langchain_core.callbacks import BaseCallbackHandler

from cli.display import classify_message_type
from tradingagents.default_config import build_default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.report_html import (
    _COMPANY,
    _CSS,
    _LOGO,
    _ORG,
    _PROJECT,
    _markdown,
    render_report,
)
from tradingagents.reporting import _report_parts, write_report_tree


def build_html_report(final_state: dict, ticker: str, settings: dict | None = None) -> str:
    """Render the full standalone HTML report for equities analysis."""
    parts = _report_parts(final_state)
    return render_report(ticker, final_state, settings, parts)


def render_portfolio_html_report(results: dict[str, Any], analyzer: Any = None) -> str:
    """Render a standalone Tauric Research styled HTML report for portfolio evaluation."""
    if analyzer is None:
        from tradingagents.analysis.portfolio_analyzer import PortfolioAnalyzer

        analyzer = PortfolioAnalyzer()
    md_content = analyzer.format_markdown_report(results)
    md = _markdown()
    body_html = md.render(md_content)
    s = results.get("summary", {})
    evaluated_at = s.get("evaluated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    total_wealth = s.get("total_portfolio_wealth", 0.0)
    pnl = s.get("total_unrealized_pnl", 0.0)
    pnl_pct = s.get("total_pnl_percent", 0.0)
    tone = "up" if pnl >= 0 else "down"
    rating_label = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}% P&L"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Indian Stock Portfolio Health Report: TradingAgents</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page" id="top">
<header class="masthead">
<a class="logo" href="{_COMPANY}" rel="noopener" aria-label="Tauric Research">{_LOGO}</a>
<h1><span class="ticker">Portfolio Health</span> <span class="rating {tone}">{escape(rating_label)}</span></h1>
<p class="date">Evaluation of {escape(evaluated_at)}</p>
<dl class="run">
  <div class="detail"><dt>Total Wealth</dt><dd><span class="field">₹{total_wealth:,.2f}</span></dd></div>
  <div class="detail"><dt>Unrealized P&L</dt><dd><span class="field">₹{pnl:,.2f}</span></dd></div>
  <div class="detail"><dt>Concentration (HHI)</dt><dd><span class="field">{s.get("hhi_index", 0)} ({escape(str(s.get("skew_status", "N/A")))})</span></dd></div>
</dl>
</header>
<main>
{body_html}
</main>
<footer class="credit"><a href="{_PROJECT}" rel="noopener">TradingAgents</a> powered by <a class="brand" href="{_ORG}" rel="noopener">Tauric Research</a></footer>
</div>
</body>
</html>"""


class WebLogCallbackHandler(BaseCallbackHandler):
    """Callback handler routing LangChain model and tool activity to terminal and Web UI."""

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        name = serialized.get("name") or "LLM"
        GLOBAL_STATE.add_message("LLM", f"Generating inference ({name})...", "system")

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[Any]], **kwargs: Any
    ) -> None:
        name = serialized.get("name") or "LLM"
        GLOBAL_STATE.add_message("LLM", f"Generating response ({name})...", "system")

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = serialized.get("name") or "tool"
        clean = input_str.strip().replace("\n", " ")
        if len(clean) > 130:
            clean = clean[:127] + "..."
        GLOBAL_STATE.add_message("TOOL", f"{name}({clean})", "tool")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        clean = str(output).strip().replace("\n", " ")
        if len(clean) > 130:
            clean = clean[:127] + "..."
        GLOBAL_STATE.add_message("TOOL_OUT", f"{clean}", "tool")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        GLOBAL_STATE.add_message("TOOL_ERR", f"{error}", "error")


class AnalysisState:
    """Thread-safe state store for active and completed runs."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.log_file_path: Path | None = None
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.status: str = "idle"  # idle, running, completed, error
            self.error_message: str | None = None
            self.ticker: str = ""
            self.trade_date: str = ""
            self.host_mode: str = "colab"
            self.messages: list[dict[str, Any]] = []
            self.agent_statuses: dict[str, str] = {
                "market": "pending",
                "news": "pending",
                "fundamentals": "pending",
                "social": "pending",
                "researcher": "pending",
                "trader": "pending",
                "risk_mgmt": "pending",
                "portfolio_manager": "pending",
            }
            self.report_html: str | None = None
            self.report_md: str | None = None
            self.final_decision: str | None = None
            self.final_state: dict[str, Any] | None = None
            self.portfolio_html: str | None = None
            self.portfolio_results: dict[str, Any] | None = None

    def add_message(self, sender: str, content: str, msg_type: str = "message") -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {
            "id": len(self.messages),
            "timestamp": timestamp,
            "sender": sender,
            "content": content,
            "type": msg_type,
        }
        with self.lock:
            self.messages.append(entry)

        # 1. Real-time colored terminal logging with immediate flush
        tag_color = {
            "system": "\033[96m",  # cyan
            "tool": "\033[93m",  # yellow
            "error": "\033[91m",  # red
            "success": "\033[92m",  # green
        }.get(msg_type, "\033[94m")  # blue
        reset = "\033[0m"

        try:
            print(f"[{timestamp}] {tag_color}[{sender}]{reset} {content}", flush=True)
        except Exception:
            with contextlib.suppress(Exception):
                print(f"[{timestamp}] [{sender}] {content}", flush=True)

        # 2. Append directly to active run log file
        if self.log_file_path:
            with (
                contextlib.suppress(Exception),
                open(self.log_file_path, "a", encoding="utf-8") as f,
            ):
                f.write(f"[{timestamp}] [{sender}] [{msg_type.upper()}] {content}\n")

    def update_agent(self, agent_key: str, status: str) -> None:
        with self.lock:
            self.agent_statuses[agent_key] = status

    def get_snapshot(self, offset: int = 0) -> dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
                "error_message": self.error_message,
                "ticker": self.ticker,
                "trade_date": self.trade_date,
                "host_mode": self.host_mode,
                "log_file": str(self.log_file_path) if self.log_file_path else "",
                "agent_statuses": dict(self.agent_statuses),
                "new_messages": self.messages[offset:],
                "total_messages": len(self.messages),
                "has_report": bool(self.report_html),
                "final_decision": self.final_decision,
            }


GLOBAL_STATE = AnalysisState()


def _run_pipeline_worker(params: dict[str, Any]) -> None:
    """Execute the TradingAgents graph in a background thread with live terminal & file logging."""
    ticker = params.get("ticker", "VEDPOWER").strip().upper()
    trade_date = params.get("date") or datetime.date.today().isoformat()
    host_mode = params.get("host", "colab").strip().lower()
    analysts = params.get("analysts", ["market", "news", "fundamentals"])
    if isinstance(analysts, str):
        analysts = [a.strip() for a in analysts.split(",") if a.strip()]

    depth = int(params.get("depth", 1))

    # Dedicated log file
    log_dir = Path.home() / ".tradingagents" / "logs" / "web_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{ticker}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file.touch(exist_ok=True)

    with GLOBAL_STATE.lock:
        GLOBAL_STATE.status = "running"
        GLOBAL_STATE.ticker = ticker
        GLOBAL_STATE.trade_date = trade_date
        GLOBAL_STATE.host_mode = host_mode
        GLOBAL_STATE.log_file_path = log_file
        GLOBAL_STATE.messages.clear()
        GLOBAL_STATE.error_message = None
        GLOBAL_STATE.report_html = None
        GLOBAL_STATE.report_md = None
        GLOBAL_STATE.final_decision = None
        for k in GLOBAL_STATE.agent_statuses:
            GLOBAL_STATE.agent_statuses[k] = "in_progress" if k in analysts else "pending"

    print("\n" + "=" * 70, flush=True)
    print(
        f"🚀 [TRADEX RUN STARTED] Ticker: {ticker} | Date: {trade_date} | Host: {host_mode.upper()}",
        flush=True,
    )
    print(f"📝 Live Run Log File: {log_file}", flush=True)
    print("=" * 70 + "\n", flush=True)

    GLOBAL_STATE.add_message(
        "System", f"Starting multi-agent trading analysis for {ticker} ({trade_date})...", "system"
    )
    GLOBAL_STATE.add_message("Log", f"Live run log active at: {log_file}", "system")

    try:
        # Build configuration with host flags
        config = build_default_config()
        config["max_debate_rounds"] = depth
        config["max_risk_discuss_rounds"] = depth

        if host_mode == "colab":
            config["llm_host"] = "colab"
            config["llm_provider"] = "colab"
            config["quick_think_llm"] = os.getenv("COLAB_QUICK_THINK_LLM") or "qwen3:8b"
            config["deep_think_llm"] = os.getenv("COLAB_DEEP_THINK_LLM") or "deepseek-r1:14b"
            if os.getenv("COLAB_LLM_URL"):
                config["backend_url"] = os.getenv("COLAB_LLM_URL")
        elif host_mode == "local":
            config["llm_host"] = "local"
            config["llm_provider"] = "ollama"
            config["quick_think_llm"] = (
                os.getenv("LOCAL_QUICK_THINK_LLM")
                or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM")
                or "qwen2.5-coder:1.5b"
            )
            config["deep_think_llm"] = (
                os.getenv("LOCAL_DEEP_THINK_LLM")
                or os.getenv("TRADINGAGENTS_DEEP_THINK_LLM")
                or "qwen2.5-coder:7b"
            )
            config["backend_url"] = (
                os.getenv("LOCAL_LLM_URL")
                or os.getenv("OLLAMA_BASE_URL")
                or "http://localhost:11434/v1"
            )

        GLOBAL_STATE.add_message(
            "Config",
            f"Configured {host_mode.upper()} host: Deep={config.get('deep_think_llm')} via {config.get('deep_think_provider') or config.get('llm_provider')}, Quick={config.get('quick_think_llm')} via {config.get('quick_think_provider') or config.get('llm_provider')}",
            "system",
        )

        callback_handler = WebLogCallbackHandler()
        graph = TradingAgentsGraph(
            selected_analysts=analysts,
            config=config,
            callbacks=[callback_handler],
            debug=True,
        )

        GLOBAL_STATE.add_message(
            "Pipeline",
            f"Phase I: Analyst Team ({', '.join(analysts)}) starting investigations...",
            "system",
        )

        init_agent_state = graph.create_run_state(ticker, trade_date, "stock", None)
        args = graph.propagator.get_graph_args(callbacks=[callback_handler])

        final_state = None
        processed_msg_ids = set()

        try:
            for messages, chunk in graph.stream_run(
                graph.checkpoint_input(init_agent_state), **args
            ):
                for message in messages:
                    msg_id = getattr(message, "id", None)
                    if msg_id and msg_id in processed_msg_ids:
                        continue
                    if msg_id:
                        processed_msg_ids.add(msg_id)

                    msg_type, content = classify_message_type(message)
                    if content and content.strip():
                        sender = getattr(message, "name", None) or msg_type
                        GLOBAL_STATE.add_message(
                            str(sender).upper(), content.strip()[:300], "message"
                        )

                if chunk and isinstance(chunk, dict):
                    final_state = chunk
                    if (
                        chunk.get("market_report")
                        and GLOBAL_STATE.agent_statuses.get("market") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("market", "completed")
                        GLOBAL_STATE.add_message(
                            "MARKET", "Market Analyst filed report.", "success"
                        )
                    if (
                        chunk.get("news_report")
                        and GLOBAL_STATE.agent_statuses.get("news") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("news", "completed")
                        GLOBAL_STATE.add_message("NEWS", "News Analyst filed report.", "success")
                    if (
                        chunk.get("fundamentals_report")
                        and GLOBAL_STATE.agent_statuses.get("fundamentals") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("fundamentals", "completed")
                        GLOBAL_STATE.add_message(
                            "FUNDAMENTALS", "Fundamentals Analyst filed report.", "success"
                        )
                    if (
                        chunk.get("sentiment_report")
                        and GLOBAL_STATE.agent_statuses.get("social") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("social", "completed")
                        GLOBAL_STATE.add_message(
                            "SENTIMENT", "Sentiment Analyst filed report.", "success"
                        )

                    if chunk.get("investment_debate_state"):
                        debate_state = chunk["investment_debate_state"]
                        bull = debate_state.get("bull_history", "").strip()
                        bear = debate_state.get("bear_history", "").strip()
                        if bull or bear:
                            GLOBAL_STATE.update_agent("researcher", "in_progress")
                            if bull:
                                GLOBAL_STATE.add_message(
                                    "BULL", "Bull Researcher argument submitted.", "message"
                                )
                            if bear:
                                GLOBAL_STATE.add_message(
                                    "BEAR", "Bear Researcher counter-argument submitted.", "message"
                                )

                    if (
                        chunk.get("investment_plan")
                        and GLOBAL_STATE.agent_statuses.get("researcher") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("researcher", "completed")
                        GLOBAL_STATE.add_message(
                            "RESEARCH MGR",
                            "Phase II Complete: Research Manager finalized plan.",
                            "success",
                        )
                        GLOBAL_STATE.update_agent("trader", "in_progress")
                        GLOBAL_STATE.add_message(
                            "Pipeline", "Phase III: Trader formulating proposal...", "system"
                        )

                    if (
                        chunk.get("trader_investment_plan")
                        and GLOBAL_STATE.agent_statuses.get("trader") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("trader", "completed")
                        GLOBAL_STATE.add_message(
                            "TRADER",
                            "Phase III Complete: Trader submitted execution plan.",
                            "success",
                        )
                        GLOBAL_STATE.update_agent("risk_mgmt", "in_progress")
                        GLOBAL_STATE.add_message(
                            "Pipeline",
                            "Phase IV: Risk Management committee deliberating...",
                            "system",
                        )

                    if (
                        chunk.get("risk_debate_state")
                        and GLOBAL_STATE.agent_statuses.get("risk_mgmt") != "completed"
                    ):
                        GLOBAL_STATE.update_agent("risk_mgmt", "completed")
                        GLOBAL_STATE.add_message(
                            "RISK",
                            "Phase IV Complete: Risk Management committee concluded.",
                            "success",
                        )
                        GLOBAL_STATE.update_agent("portfolio_manager", "in_progress")
                        GLOBAL_STATE.add_message(
                            "Pipeline",
                            "Phase V: Portfolio Manager rendering final trade decision...",
                            "system",
                        )

                    if chunk.get("final_trade_decision"):
                        GLOBAL_STATE.update_agent("portfolio_manager", "completed")
                        GLOBAL_STATE.add_message(
                            "PORTFOLIO MGR",
                            "Phase V Complete: Portfolio Manager rendered final decision.",
                            "success",
                        )

        except Exception as stream_err:
            GLOBAL_STATE.add_message(
                "System",
                f"Stream notice: {stream_err}. Ensuring complete state via graph propagation...",
                "system",
            )

        if not final_state or not final_state.get("final_trade_decision"):
            GLOBAL_STATE.add_message(
                "System", "Running graph propagation to complete final decisions...", "system"
            )
            final_state, signal = graph.propagate(ticker, trade_date)

        # Mark all agents completed
        for k in GLOBAL_STATE.agent_statuses:
            GLOBAL_STATE.update_agent(k, "completed")

        # Extract final trade decision
        decision = final_state.get("final_trade_decision") or "No decision reached"
        rating = "Hold"
        for line in decision.split("\n"):
            if "Rating" in line or "Decision" in line:
                rating = line.strip()
                break

        # Generate HTML report
        settings = graph.run_settings()
        html_report = build_html_report(final_state, ticker, settings)

        # Save to disk report directory
        reports_dir = Path.home() / ".tradingagents" / "logs" / "reports"
        save_folder = reports_dir / f"{ticker}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        md_file = write_report_tree(final_state, ticker, save_folder, settings=settings, html=True)

        md_content = md_file.read_text(encoding="utf-8") if md_file.exists() else ""

        with GLOBAL_STATE.lock:
            GLOBAL_STATE.status = "completed"
            GLOBAL_STATE.final_decision = rating
            GLOBAL_STATE.report_html = html_report
            GLOBAL_STATE.report_md = md_content
            GLOBAL_STATE.final_state = final_state

        GLOBAL_STATE.add_message(
            "System",
            f"Analysis completed successfully! Final Decision: {rating}. Report saved to {save_folder.name}",
            "success",
        )

    except Exception as exc:
        with GLOBAL_STATE.lock:
            GLOBAL_STATE.status = "error"
            GLOBAL_STATE.error_message = str(exc)
        GLOBAL_STATE.add_message("System", f"Analysis failed: {exc}", "error")


class WebDashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the interactive dashboard and REST API."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr HTTP request logging for cleaner CLI experience."""
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html: str, status: int = 200) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._send_html(DASHBOARD_HTML)
        elif path == "/api/status":
            query = parse_qs(parsed.query)
            offset = int(query.get("offset", ["0"])[0])
            self._send_json(GLOBAL_STATE.get_snapshot(offset=offset))
        elif path == "/api/report":
            with GLOBAL_STATE.lock:
                html = GLOBAL_STATE.report_html
            if html:
                self._send_html(html)
            else:
                self._send_html(
                    "<h3>No report has been generated yet. Please run an analysis first.</h3>",
                    status=HTTPStatus.NOT_FOUND,
                )
        elif path == "/api/report/download":
            query = parse_qs(parsed.query)
            fmt = query.get("format", ["html"])[0].lower()
            with GLOBAL_STATE.lock:
                html = GLOBAL_STATE.report_html
                md = GLOBAL_STATE.report_md
                ticker = GLOBAL_STATE.ticker or "analysis"
                date_str = GLOBAL_STATE.trade_date or datetime.date.today().isoformat()

            if fmt == "md":
                if not md:
                    self.send_error(HTTPStatus.NOT_FOUND, "No markdown report generated yet.")
                    return
                filename = f"TradingAgents_Report_{ticker}_{date_str}.md"
                payload = md.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)
            else:
                if not html:
                    self.send_error(HTTPStatus.NOT_FOUND, "No HTML report generated yet.")
                    return
                filename = f"TradingAgents_Report_{ticker}_{date_str}.html"
                payload = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)

        elif path == "/api/reports/list":
            reports_dir = Path.home() / ".tradingagents" / "logs" / "reports"
            items = []
            if reports_dir.exists():
                for d in sorted(
                    reports_dir.iterdir(),
                    key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                    reverse=True,
                ):
                    if d.is_dir():
                        has_html = (d / "complete_report.html").exists()
                        has_md = (d / "complete_report.md").exists()
                        name_parts = d.name.rsplit("_", 2)
                        ticker = name_parts[0] if name_parts else d.name
                        ts = datetime.datetime.fromtimestamp(d.stat().st_mtime).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        items.append(
                            {
                                "folder": d.name,
                                "ticker": ticker,
                                "timestamp": ts,
                                "has_html": has_html,
                                "has_md": has_md,
                            }
                        )
            self._send_json(items[:50])

        elif path == "/api/reports/saved":
            query = parse_qs(parsed.query)
            folder = query.get("folder", [""])[0].strip()
            fmt = query.get("format", ["html"])[0].lower()
            is_download = query.get("download", ["0"])[0] == "1"

            safe_folder = Path(folder).name
            file_name = "complete_report.html" if fmt == "html" else "complete_report.md"
            file_path = (
                Path.home() / ".tradingagents" / "logs" / "reports" / safe_folder / file_name
            )

            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Saved report not found")
                return

            content = file_path.read_bytes()
            c_type = "text/html; charset=utf-8" if fmt == "html" else "text/markdown; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", c_type)
            if is_download:
                dl_name = f"TradingAgents_Report_{safe_folder}.{fmt}"
                self.send_header("Content-Disposition", f'attachment; filename="{dl_name}"')
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)

        elif path == "/api/mf/search":
            query = parse_qs(parsed.query)
            q = query.get("q", [""])[0].strip()
            if not q:
                self._send_json([])
                return
            try:
                from tradingagents.dataflows.vendors.amfi_mf import search_mutual_fund

                results = search_mutual_fund(q, limit=8)
                self._send_json(results)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        elif path == "/api/mf/details":
            query = parse_qs(parsed.query)
            code = query.get("code", [""])[0].strip()
            if not code:
                self._send_json(
                    {"error": "Missing 'code' parameter"}, status=HTTPStatus.BAD_REQUEST
                )
                return
            try:
                from tradingagents.dataflows.vendors.amfi_mf import get_mutual_fund_details

                details = get_mutual_fund_details(code)
                self._send_json(details)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        elif path == "/api/etf/details":
            query = parse_qs(parsed.query)
            ticker = query.get("ticker", [""])[0].strip()
            if not ticker:
                self._send_json(
                    {"error": "Missing 'ticker' parameter"}, status=HTTPStatus.BAD_REQUEST
                )
                return
            try:
                from tradingagents.dataflows.vendors.etf_vendor import get_etf_details

                details = get_etf_details(ticker)
                self._send_json(details)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        elif path == "/api/portfolio/download":
            with GLOBAL_STATE.lock:
                p_html = GLOBAL_STATE.portfolio_html
            if not p_html:
                self.send_error(HTTPStatus.NOT_FOUND, "No portfolio report generated yet.")
                return
            date_str = datetime.date.today().isoformat()
            filename = f"TradingAgents_Portfolio_Report_{date_str}.html"
            payload = p_html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/log":
            with GLOBAL_STATE.lock:
                lpath = GLOBAL_STATE.log_file_path
            if not lpath or not Path(lpath).exists():
                self.send_error(HTTPStatus.NOT_FOUND, "No active log file found.")
                return
            log_content = Path(lpath).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(log_content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(log_content)

        elif path == "/api/config":
            self._send_json(
                {
                    "colab_url": os.environ.get("COLAB_LLM_URL", ""),
                    "local_url": os.environ.get("LOCAL_LLM_URL")
                    or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                    "quick_colab": os.environ.get("COLAB_QUICK_THINK_LLM", "qwen3:8b"),
                    "deep_colab": os.environ.get("COLAB_DEEP_THINK_LLM", "deepseek-r1:14b"),
                    "quick_local": os.environ.get("LOCAL_QUICK_THINK_LLM", "qwen2.5-coder:1.5b"),
                    "deep_local": os.environ.get("LOCAL_DEEP_THINK_LLM", "qwen2.5-coder:7b"),
                }
            )
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            with GLOBAL_STATE.lock:
                if GLOBAL_STATE.status == "running":
                    self._send_json(
                        {"error": "An analysis run is already in progress."},
                        status=HTTPStatus.CONFLICT,
                    )
                    return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                params = json.loads(body.decode("utf-8"))
            except Exception:
                params = {}

            worker = threading.Thread(target=_run_pipeline_worker, args=(params,), daemon=True)
            worker.start()
            self._send_json({"message": "Analysis started successfully."})

        elif parsed.path == "/api/portfolio/analyze":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}

            holdings = data.get("holdings", [])
            cash = float(data.get("cash", 0.0))
            if not holdings:
                self._send_json({"error": "No holdings provided."}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                from dataclasses import asdict

                from tradingagents.analysis.portfolio_analyzer import PortfolioAnalyzer

                analyzer = PortfolioAnalyzer(cash=cash)
                results = analyzer.evaluate_portfolio(holdings)
                p_html = render_portfolio_html_report(results, analyzer)

                with GLOBAL_STATE.lock:
                    GLOBAL_STATE.portfolio_html = p_html
                    GLOBAL_STATE.portfolio_results = results

                resp = {
                    "summary": results["summary"],
                    "holdings": [asdict(h) for h in results["holdings"]],
                    "sector_distribution": results["sector_distribution"],
                    "best_performers": [asdict(b) for b in results["best_performers"]],
                    "worst_performers": [asdict(w) for w in results["worst_performers"]],
                    "html_report": p_html,
                }
                self._send_json(resp)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def run_web_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the interactive TradingAgents web dashboard server."""
    server = ThreadingHTTPServer((host, port), WebDashboardHandler)
    url = f"http://{host}:{port}"
    print("\n============================================================")
    print(f"🚀 Tradex Agent Web Dashboard is running at: {url}")
    print("Multi-Asset Intelligence: Equities, Mutual Funds, ETFs, and Portfolio Audit")
    print("Full uncropped live terminal, styled HTML reports & one-click downloads!")
    print("============================================================\n")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web dashboard server...")
        server.shutdown()


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tradex Agent Web Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.1); }
    ::-webkit-scrollbar-thumb { background: rgba(100,116,139,0.5); border-radius: 3px; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col">

  <!-- Top Global Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
    <div class="flex items-center space-x-3">
      <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20 font-bold text-xl">
        <i class="fa-solid fa-chart-line"></i>
      </div>
      <div>
        <h1 class="text-lg font-bold tracking-tight text-white flex items-center gap-2">
          Tradex Agent <span class="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">v0.6.0 Live</span>
        </h1>
        <p class="text-[11px] text-slate-400">Institutional Multi-Asset Financial Intelligence</p>
      </div>
    </div>

    <!-- Navigation Bar Use Case Tabs -->
    <nav class="flex items-center bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
      <button id="nav-btn-ticker" onclick="switchNav('ticker')" class="px-3.5 py-1.5 rounded-lg font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 transition">
        <i class="fa-solid fa-arrow-trend-up"></i> Ticker Analysis
      </button>
      <button id="nav-btn-mf" onclick="switchNav('mf')" class="px-3.5 py-1.5 rounded-lg font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-1.5 transition">
        <i class="fa-solid fa-coins"></i> Mutual Funds
      </button>
      <button id="nav-btn-etf" onclick="switchNav('etf')" class="px-3.5 py-1.5 rounded-lg font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-1.5 transition">
        <i class="fa-solid fa-layer-group"></i> ETF Screener
      </button>
      <button id="nav-btn-portfolio" onclick="switchNav('portfolio')" class="px-3.5 py-1.5 rounded-lg font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-1.5 transition">
        <i class="fa-solid fa-briefcase"></i> Portfolio Audit
      </button>
    </nav>

    <!-- Right Actions & LLM Host Status -->
    <div class="flex items-center space-x-3">
      <button onclick="openSavedReportsModal()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 shadow transition">
        <i class="fa-solid fa-folder-open text-amber-400"></i> Saved Reports
      </button>

      <div id="host-indicator" class="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-slate-300 font-medium" id="current-host-display">Google Colab Hosted</span>
      </div>
    </div>
  </header>

  <!-- ========================================== -->
  <!-- 1. VIEW: EQUITIES TICKER ANALYSIS          -->
  <!-- ========================================== -->
  <main id="view-ticker" class="view-panel flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">

    <!-- Left Controls Panel (4 Cols) -->
    <div class="lg:col-span-4 space-y-6">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-5">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <i class="fa-solid fa-sliders text-emerald-400"></i> Analysis Parameters
        </h2>

        <!-- Ticker Input & Presets -->
        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1.5">Ticker / Asset Symbol</label>
          <div class="relative">
            <input type="text" id="ticker-input" value="VEDPOWER" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white font-medium focus:border-emerald-500 focus:outline-none transition uppercase">
            <span class="absolute right-3 top-2.5 text-xs text-slate-500">e.g. VEDPOWER</span>
          </div>
          <div class="flex flex-wrap gap-1.5 mt-2">
            <button onclick="setTicker('VEDPOWER')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">VEDPOWER (NSE)</button>
            <button onclick="setTicker('RELIANCE.NS')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">RELIANCE</button>
            <button onclick="setTicker('TCS.NS')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">TCS</button>
            <button onclick="setTicker('HDFCBANK.NS')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">HDFC Bank</button>
            <button onclick="setTicker('NVDA')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">NVDA (US)</button>
          </div>
        </div>

        <!-- LLM Host Switcher -->
        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1.5">Inference Host Environment</label>
          <div class="grid grid-cols-2 gap-2">
            <button id="host-btn-colab" onclick="selectHost('colab')" class="px-3 py-2 rounded-xl border border-emerald-500 bg-emerald-500/10 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition">
              <i class="fa-solid fa-cloud"></i> Google Colab
            </button>
            <button id="host-btn-local" onclick="selectHost('local')" class="px-3 py-2 rounded-xl border border-slate-700 bg-slate-950 text-slate-400 hover:text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition">
              <i class="fa-solid fa-server"></i> Local Ollama
            </button>
          </div>
          <p id="host-desc" class="text-[11px] text-slate-400 mt-1.5">Using remote T4 GPU: deepseek-r1:14b & qwen3:8b.</p>
        </div>

        <!-- Date & Research Depth -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1.5">Analysis Date</label>
            <input type="date" id="date-input" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none">
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1.5">Research Depth</label>
            <select id="depth-select" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none">
              <option value="1">1 Round (Fast)</option>
              <option value="2">2 Rounds (Balanced)</option>
              <option value="3">3 Rounds (Deep)</option>
            </select>
          </div>
        </div>

        <!-- Analysts Selection -->
        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1.5">Analyst Agents</label>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <label class="flex items-center space-x-2 bg-slate-950 border border-slate-800 rounded-lg p-2 cursor-pointer hover:border-slate-700">
              <input type="checkbox" id="analyst-market" checked class="rounded text-emerald-500 focus:ring-0">
              <span>Market / Tech</span>
            </label>
            <label class="flex items-center space-x-2 bg-slate-950 border border-slate-800 rounded-lg p-2 cursor-pointer hover:border-slate-700">
              <input type="checkbox" id="analyst-news" checked class="rounded text-emerald-500 focus:ring-0">
              <span>News / Macro</span>
            </label>
            <label class="flex items-center space-x-2 bg-slate-950 border border-slate-800 rounded-lg p-2 cursor-pointer hover:border-slate-700">
              <input type="checkbox" id="analyst-fundamentals" checked class="rounded text-emerald-500 focus:ring-0">
              <span>Fundamentals</span>
            </label>
            <label class="flex items-center space-x-2 bg-slate-950 border border-slate-800 rounded-lg p-2 cursor-pointer hover:border-slate-700">
              <input type="checkbox" id="analyst-social" checked class="rounded text-emerald-500 focus:ring-0">
              <span>Sentiment</span>
            </label>
          </div>
        </div>

        <!-- Launch Button -->
        <button id="run-btn" onclick="startAnalysis()" class="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white font-semibold text-sm shadow-lg shadow-emerald-500/25 flex items-center justify-center gap-2 transition active:scale-[0.98]">
          <i class="fa-solid fa-play"></i> Run Multi-Agent Analysis
        </button>
      </div>

      <!-- Agent Workflow Status Pipeline -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <i class="fa-solid fa-diagram-project text-teal-400"></i> Execution Pipeline
        </h2>
        <div class="space-y-2 text-xs" id="pipeline-list">
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800" id="step-analysts">
            <span class="flex items-center gap-2"><i class="fa-solid fa-users text-slate-400"></i> I. Analysts Team</span>
            <span class="status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">idle</span>
          </div>
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800" id="step-research">
            <span class="flex items-center gap-2"><i class="fa-solid fa-comments text-slate-400"></i> II. Bull / Bear Debate</span>
            <span class="status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">idle</span>
          </div>
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800" id="step-trader">
            <span class="flex items-center gap-2"><i class="fa-solid fa-hand-holding-dollar text-slate-400"></i> III. Trader Proposal</span>
            <span class="status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">idle</span>
          </div>
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800" id="step-risk">
            <span class="flex items-center gap-2"><i class="fa-solid fa-shield-halved text-slate-400"></i> IV. Risk Committee</span>
            <span class="status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">idle</span>
          </div>
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800" id="step-portfolio">
            <span class="flex items-center gap-2"><i class="fa-solid fa-stamp text-slate-400"></i> V. Portfolio Manager</span>
            <span class="status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">idle</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Right Content Area (8 Cols) -->
    <div class="lg:col-span-8 flex flex-col space-y-4">

      <!-- In-Page Completion Action Banner (Visible upon finish) -->
      <div id="ticker-completion-banner" class="hidden p-4 rounded-2xl bg-gradient-to-r from-emerald-950/80 via-slate-900 to-teal-950/80 border border-emerald-500/40 shadow-xl flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-lg font-bold border border-emerald-500/30">
            <i class="fa-solid fa-circle-check"></i>
          </div>
          <div>
            <h3 class="text-sm font-bold text-white flex items-center gap-2" id="completion-title">
              Analysis Complete: <span id="completion-ticker" class="text-emerald-400">VEDPOWER</span>
            </h3>
            <p class="text-xs text-slate-400" id="completion-subtitle">
              Rating: <span id="completion-rating" class="font-semibold text-emerald-300">BUY</span> • Ready to read or download
            </p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button onclick="switchTab('report')" class="px-3.5 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-2 shadow-lg shadow-emerald-500/20 transition active:scale-[0.98]">
            <i class="fa-solid fa-book-open"></i> Read Report in Dashboard
          </button>
          <a id="btn-download-html" href="/api/report/download?format=html" download class="px-3.5 py-2 rounded-xl text-xs font-semibold bg-teal-600 hover:bg-teal-500 text-white flex items-center gap-2 shadow-lg shadow-teal-500/20 transition active:scale-[0.98]">
            <i class="fa-solid fa-file-arrow-down"></i> Download HTML Report
          </a>
          <a id="btn-download-md" href="/api/report/download?format=md" download class="px-3 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition">
            <i class="fa-solid fa-file-lines"></i> Markdown
          </a>
          <a href="/api/report" target="_blank" class="px-3 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition">
            <i class="fa-solid fa-arrow-up-right-from-square"></i> New Tab
          </a>
        </div>
      </div>

      <!-- View Switcher Tabs -->
      <div class="flex items-center justify-between border-b border-slate-800 pb-2">
        <div class="flex space-x-2">
          <button id="tab-live" onclick="switchTab('live')" class="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-2">
            <i class="fa-solid fa-terminal"></i> Live Stream Log
          </button>
          <button id="tab-report" onclick="switchTab('report')" class="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-2">
            <i class="fa-solid fa-file-contract"></i> Full Formatted Report
          </button>
        </div>
        <div id="status-pill" class="text-xs px-3 py-1 rounded-full bg-slate-800 text-slate-400 font-medium">Ready</div>
      </div>

      <!-- Live Log Stream Container -->
      <div id="panel-live" class="flex-1 bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col min-h-[560px]">
        <div class="flex flex-wrap items-center justify-between text-xs text-slate-400 pb-3 border-b border-slate-800 gap-2">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="font-medium text-slate-200">Real-time Uncropped Messages & Agent Tool Calls</span>
          </div>
          <div class="flex items-center gap-2.5">
            <div id="log-file-container" class="hidden text-[11px] text-slate-300 font-mono bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 flex items-center gap-2">
              <i class="fa-solid fa-file-lines text-teal-400"></i>
              <span id="log-file-path" class="text-slate-300 truncate max-w-sm">--</span>
              <a href="/api/log" target="_blank" class="text-teal-400 hover:text-teal-300 ml-1 font-sans font-semibold text-[10px]" title="Open Raw Log in Browser">
                <i class="fa-solid fa-arrow-up-right-from-square"></i> Open Log
              </a>
            </div>
            <button onclick="clearLogs()" class="hover:text-slate-200 transition"><i class="fa-solid fa-trash-can"></i> Clear</button>
          </div>
        </div>
        <div id="log-container" class="flex-1 overflow-y-auto space-y-2.5 pt-3 mono text-xs leading-relaxed max-h-[600px]">
          <div class="text-slate-500 italic p-4 text-center">No analysis running. Fill in parameters and click "Run Multi-Agent Analysis" on the left.</div>
        </div>
      </div>

      <!-- Full Report Frame Container -->
      <div id="panel-report" class="hidden flex-1 bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl min-h-[620px] flex flex-col">
        <!-- Report Top Header with Action Buttons -->
        <div class="bg-slate-950 border-b border-slate-800 px-4 py-2.5 flex items-center justify-between">
          <div class="flex items-center space-x-2 text-xs">
            <i class="fa-solid fa-file-lines text-teal-400"></i>
            <span class="font-semibold text-slate-200">Generated Tauric Research HTML Report</span>
          </div>
          <div class="flex items-center space-x-2">
            <a href="/api/report/download?format=html" download class="px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow transition">
              <i class="fa-solid fa-file-arrow-down"></i> Download HTML
            </a>
            <a href="/api/report/download?format=md" download class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition">
              <i class="fa-solid fa-file-lines"></i> Download MD
            </a>
            <a href="/api/report" target="_blank" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition">
              <i class="fa-solid fa-arrow-up-right-from-square"></i> New Tab
            </a>
          </div>
        </div>
        <iframe id="report-iframe" class="w-full flex-1 min-h-[600px] border-none bg-white" src="about:blank"></iframe>
      </div>

    </div>
  </main>

  <!-- ========================================== -->
  <!-- 2. VIEW: MUTUAL FUND (MF) ANALYSIS         -->
  <!-- ========================================== -->
  <main id="view-mf" class="view-panel hidden flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-coins text-emerald-400"></i> Indian Mutual Fund (AMFI) Intelligence
          </h2>
          <p class="text-xs text-slate-400 mt-1">Live NAV, historical returns (CAGR), risk categorization, and AMFI scheme analytics</p>
        </div>
      </div>

      <!-- Search & Presets -->
      <div class="grid grid-cols-1 md:grid-cols-12 gap-4">
        <div class="md:col-span-8 relative">
          <label class="block text-xs font-medium text-slate-300 mb-1.5">Search AMFI Scheme Name or Scheme Code</label>
          <div class="flex gap-2">
            <input type="text" id="mf-query" value="Parag Parikh Flexi Cap" placeholder="e.g. Parag Parikh, Quant Small Cap, or scheme code 122639" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none">
            <button onclick="fetchMFDetails()" class="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center gap-2 transition">
              <i class="fa-solid fa-magnifying-glass"></i> Analyze
            </button>
          </div>
          <!-- Autocomplete results dropdown -->
          <div id="mf-search-dropdown" class="hidden absolute left-0 right-0 top-full mt-1 bg-slate-950 border border-slate-800 rounded-xl shadow-2xl z-50 max-h-60 overflow-y-auto"></div>
        </div>
        <div class="md:col-span-4">
          <label class="block text-xs font-medium text-slate-300 mb-1.5">Popular Indian Mutual Funds</label>
          <div class="flex flex-wrap gap-1.5">
            <button onclick="loadMF('122639')" class="px-2 py-1 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">Parag Parikh Flexi Cap</button>
            <button onclick="loadMF('120828')" class="px-2 py-1 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">Quant Small Cap</button>
            <button onclick="loadMF('119598')" class="px-2 py-1 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">SBI Bluechip</button>
            <button onclick="loadMF('118778')" class="px-2 py-1 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">Nippon India Small Cap</button>
          </div>
        </div>
      </div>
    </div>

    <!-- MF Results Container -->
    <div id="mf-results" class="hidden space-y-6">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div class="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
          <div>
            <h3 id="mf-scheme-name" class="text-lg font-bold text-white">Scheme Name</h3>
            <p id="mf-meta" class="text-xs text-slate-400 mt-0.5">Fund House • Scheme Category</p>
          </div>
          <div class="text-right">
            <div class="text-xs text-slate-400">Current NAV</div>
            <div id="mf-nav" class="text-2xl font-bold text-emerald-400">₹0.00</div>
            <div id="mf-nav-date" class="text-[10px] text-slate-500">As of Date</div>
          </div>
        </div>

        <!-- Returns KPI Cards -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-center">
            <div class="text-[11px] text-slate-400">1 Month</div>
            <div id="mf-ret-1m" class="text-base font-bold text-emerald-400 mt-1">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-center">
            <div class="text-[11px] text-slate-400">6 Months</div>
            <div id="mf-ret-6m" class="text-base font-bold text-emerald-400 mt-1">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-center">
            <div class="text-[11px] text-slate-400">1 Year (CAGR)</div>
            <div id="mf-ret-1y" class="text-base font-bold text-emerald-400 mt-1">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-center">
            <div class="text-[11px] text-slate-400">3 Years (CAGR)</div>
            <div id="mf-ret-3y" class="text-base font-bold text-emerald-400 mt-1">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-center">
            <div class="text-[11px] text-slate-400">5 Years (CAGR)</div>
            <div id="mf-ret-5y" class="text-base font-bold text-emerald-400 mt-1">--</div>
          </div>
        </div>

        <!-- Strategy Profile Card -->
        <div class="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
          <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <i class="fa-solid fa-lightbulb text-amber-400"></i> Investment Strategy & Profiling
          </h4>
          <p id="mf-strategy" class="text-xs text-slate-300 leading-relaxed">Strategy insights and benchmark alignment details will appear here.</p>
        </div>
      </div>
    </div>
  </main>

  <!-- ========================================== -->
  <!-- 3. VIEW: ETF SCREENER                      -->
  <!-- ========================================== -->
  <main id="view-etf" class="view-panel hidden flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-layer-group text-teal-400"></i> Indian Exchange Traded Funds (ETFs)
          </h2>
          <p class="text-xs text-slate-400 mt-1">Real-time quotes, 52-week price channels, volume liquidity, and underlying benchmark indexes</p>
        </div>
      </div>

      <!-- Input & Chips -->
      <div class="space-y-3">
        <label class="block text-xs font-medium text-slate-300">ETF Symbol (NSE)</label>
        <div class="flex max-w-md gap-2">
          <input type="text" id="etf-input" value="NIFTYBEES" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white uppercase focus:border-teal-500 focus:outline-none">
          <button onclick="fetchETFDetails()" class="px-5 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-semibold text-xs flex items-center gap-2 transition">
            <i class="fa-solid fa-chart-simple"></i> Lookup
          </button>
        </div>
        <div class="flex flex-wrap gap-1.5 pt-1">
          <button onclick="setETF('NIFTYBEES')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">NIFTYBEES (Nifty 50)</button>
          <button onclick="setETF('BANKBEES')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">BANKBEES (Nifty Bank)</button>
          <button onclick="setETF('GOLDBEES')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">GOLDBEES (Gold)</button>
          <button onclick="setETF('SILVERBEES')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">SILVERBEES (Silver)</button>
          <button onclick="setETF('ITBEES')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">ITBEES (IT Sector)</button>
          <button onclick="setETF('CPSEETF')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">CPSEETF (PSU)</button>
          <button onclick="setETF('MON100')" class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">MON100 (Nasdaq 100)</button>
        </div>
      </div>
    </div>

    <!-- ETF Results Card -->
    <div id="etf-results" class="hidden bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      <div class="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
        <div>
          <div class="flex items-center gap-2">
            <h3 id="etf-name" class="text-xl font-bold text-white">Nippon India ETF Nifty 50 BeES</h3>
            <span id="etf-badge" class="px-2 py-0.5 rounded text-[11px] bg-teal-500/20 text-teal-300 border border-teal-500/30">Large Cap Equity</span>
          </div>
          <p id="etf-benchmark" class="text-xs text-slate-400 mt-1">Underlying: Nifty 50 Index • NSE India</p>
        </div>
        <div class="text-right">
          <div class="text-xs text-slate-400">Current Market Price</div>
          <div id="etf-price" class="text-3xl font-bold text-white">₹0.00</div>
        </div>
      </div>

      <!-- 52-Week Range Gauge -->
      <div class="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
        <div class="flex justify-between text-xs text-slate-400">
          <span>52-Week Low: <strong id="etf-low" class="text-white">₹0.00</strong></span>
          <span>52-Week High: <strong id="etf-high" class="text-white">₹0.00</strong></span>
        </div>
        <div class="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden relative">
          <div id="etf-range-bar" class="bg-gradient-to-r from-teal-500 to-emerald-400 h-2.5 rounded-full" style="width: 50%"></div>
        </div>
      </div>

      <!-- Volume & Liquidity -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-4 rounded-xl bg-slate-950 border border-slate-800">
          <div class="text-xs text-slate-400">Trading Volume Today</div>
          <div id="etf-volume" class="text-lg font-bold text-slate-200 mt-1">--</div>
        </div>
        <div class="p-4 rounded-xl bg-slate-950 border border-slate-800">
          <div class="text-xs text-slate-400">Average Daily Volume</div>
          <div id="etf-avg-volume" class="text-lg font-bold text-slate-200 mt-1">--</div>
        </div>
      </div>
    </div>
  </main>

  <!-- ========================================== -->
  <!-- 4. VIEW: PORTFOLIO AUDIT                   -->
  <!-- ========================================== -->
  <main id="view-portfolio" class="view-panel hidden flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-briefcase text-emerald-400"></i> Indian Stock Portfolio Health & Strategy Engine
          </h2>
          <p class="text-xs text-slate-400 mt-1">Real-time pricing, Screener.in fundamentals, sector skew (HHI index), and AI rebalancing advice</p>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="loadSamplePortfolio('growth')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition">
            <i class="fa-solid fa-bolt text-amber-400"></i> Load Growth Sample
          </button>
          <button onclick="loadSamplePortfolio('defensive')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition">
            <i class="fa-solid fa-shield text-cyan-400"></i> Load Bluechip Sample
          </button>
        </div>
      </div>

      <!-- Holdings Grid Input -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <label class="text-xs font-semibold uppercase tracking-wider text-slate-400">Holdings List (Ticker, Quantity, Buy Price)</label>
          <button onclick="addHoldingRow()" class="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1">
            <i class="fa-solid fa-plus-circle"></i> Add Stock Row
          </button>
        </div>

        <div id="holdings-table-container" class="space-y-2">
          <!-- Dynamic Rows -->
        </div>

        <div class="pt-2 flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center space-x-2">
            <label class="text-xs text-slate-400">Available Cash (₹):</label>
            <input type="number" id="portfolio-cash" value="25000" class="w-32 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white">
          </div>
          <button id="btn-run-portfolio" onclick="runPortfolioAudit()" class="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white font-semibold text-xs flex items-center gap-2 shadow-lg shadow-emerald-500/20 transition active:scale-[0.98]">
            <i class="fa-solid fa-play"></i> Run Full Portfolio Audit
          </button>
        </div>
      </div>
    </div>

    <!-- Portfolio Results Container -->
    <div id="portfolio-results" class="hidden space-y-6">

      <!-- In-Page Action Bar (HTML Report Download & CSV Export) -->
      <div class="p-4 rounded-2xl bg-gradient-to-r from-emerald-950/80 via-slate-900 to-teal-950/80 border border-emerald-500/40 shadow-xl flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-lg font-bold border border-emerald-500/30">
            <i class="fa-solid fa-file-shield"></i>
          </div>
          <div>
            <h3 class="text-sm font-bold text-white">Portfolio Audit Completed</h3>
            <p class="text-xs text-slate-400">Download the self-contained Tauric Research styled report or export raw holdings CSV</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <a href="/api/portfolio/download" download class="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-2 shadow-lg shadow-emerald-500/20 transition">
            <i class="fa-solid fa-file-arrow-down"></i> Download Portfolio HTML Report
          </a>
          <button onclick="exportHoldingsCSV()" class="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition">
            <i class="fa-solid fa-file-csv text-teal-400"></i> Export CSV
          </button>
        </div>
      </div>

      <!-- KPI Summary Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow">
          <div class="text-xs text-slate-400">Invested Capital</div>
          <div id="port-invested" class="text-xl font-bold text-white mt-1">₹0.00</div>
        </div>
        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow">
          <div class="text-xs text-slate-400">Current Market Value</div>
          <div id="port-current" class="text-xl font-bold text-white mt-1">₹0.00</div>
        </div>
        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow">
          <div class="text-xs text-slate-400">Unrealized P&L</div>
          <div id="port-pnl" class="text-xl font-bold text-emerald-400 mt-1">₹0.00 (+0.0%)</div>
        </div>
        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow">
          <div class="text-xs text-slate-400">Concentration (HHI Index)</div>
          <div id="port-hhi" class="text-xl font-bold text-cyan-400 mt-1">0.0</div>
          <div id="port-skew-risk" class="text-[10px] text-slate-400 mt-0.5">Balanced</div>
        </div>
      </div>

      <!-- Holdings Evaluation Matrix -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
        <h3 class="text-sm font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-table text-emerald-400"></i> Stock-by-Stock Fundamentals & Action Matrix
        </h3>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400">
                <th class="py-2.5 px-3">Stock</th>
                <th class="py-2.5 px-3">Weight</th>
                <th class="py-2.5 px-3">P&L %</th>
                <th class="py-2.5 px-3">CMP (₹)</th>
                <th class="py-2.5 px-3">Stock P/E</th>
                <th class="py-2.5 px-3">Industry P/E</th>
                <th class="py-2.5 px-3">ROCE</th>
                <th class="py-2.5 px-3">Sentiment</th>
                <th class="py-2.5 px-3">Action</th>
              </tr>
            </thead>
            <tbody id="portfolio-holdings-tbody" class="divide-y divide-slate-800/60">
              <!-- Rendered rows -->
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </main>

  <!-- ========================================== -->
  <!-- 5. MODAL: SAVED REPORTS BROWSER            -->
  <!-- ========================================== -->
  <div id="modal-saved-reports" class="hidden fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-folder-open text-amber-400"></i> Saved Analysis Reports
        </h3>
        <button onclick="closeSavedReportsModal()" class="text-slate-400 hover:text-white text-lg">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>

      <p class="text-xs text-slate-400">Historical trading reports saved on disk under <code class="mono text-slate-300">~/.tradingagents/logs/reports/</code>.</p>

      <div id="saved-reports-list" class="max-h-80 overflow-y-auto space-y-2 pr-1 text-xs">
        <div class="text-center text-slate-500 py-6">Loading reports...</div>
      </div>

      <div class="border-t border-slate-800 pt-3 flex justify-end">
        <button onclick="closeSavedReportsModal()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition">
          Close
        </button>
      </div>
    </div>
  </div>

  <script>
    let activeHost = 'colab';
    let pollInterval = null;
    let messageOffset = 0;
    let currentPortfolioHoldings = [];

    // Set today's date
    document.getElementById('date-input').value = new Date().toISOString().split('T')[0];

    // Initialize 3 default holding rows for portfolio audit
    loadSamplePortfolio('growth');

    // Tab Navigation Switcher
    function switchNav(tab) {
      document.querySelectorAll('.view-panel').forEach(p => p.classList.add('hidden'));
      const navBtns = ['ticker', 'mf', 'etf', 'portfolio'];
      navBtns.forEach(t => {
        const btn = document.getElementById(`nav-btn-${t}`);
        if (t === tab) {
          btn.className = "px-3.5 py-1.5 rounded-lg font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 transition";
        } else {
          btn.className = "px-3.5 py-1.5 rounded-lg font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-1.5 transition";
        }
      });
      document.getElementById(`view-${tab}`).classList.remove('hidden');
    }

    function setTicker(t) {
      document.getElementById('ticker-input').value = t;
    }

    function setETF(t) {
      document.getElementById('etf-input').value = t;
      fetchETFDetails();
    }

    function selectHost(host) {
      activeHost = host;
      const colabBtn = document.getElementById('host-btn-colab');
      const localBtn = document.getElementById('host-btn-local');
      const desc = document.getElementById('host-desc');
      const display = document.getElementById('current-host-display');

      if (host === 'colab') {
        colabBtn.className = "px-3 py-2 rounded-xl border border-emerald-500 bg-emerald-500/10 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition";
        localBtn.className = "px-3 py-2 rounded-xl border border-slate-700 bg-slate-950 text-slate-400 hover:text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition";
        desc.innerText = "Using remote T4 GPU: deepseek-r1:14b & qwen3:8b.";
        display.innerText = "Google Colab Hosted";
      } else {
        localBtn.className = "px-3 py-2 rounded-xl border border-emerald-500 bg-emerald-500/10 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition";
        colabBtn.className = "px-3 py-2 rounded-xl border border-slate-700 bg-slate-950 text-slate-400 hover:text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition";
        desc.innerText = "Using local Ollama: qwen2.5-coder:1.5b & 7b.";
        display.innerText = "Local Ollama";
      }
    }

    function switchTab(tab) {
      const liveBtn = document.getElementById('tab-live');
      const reportBtn = document.getElementById('tab-report');
      const livePanel = document.getElementById('panel-live');
      const reportPanel = document.getElementById('panel-report');

      if (tab === 'live') {
        liveBtn.className = "px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-2";
        reportBtn.className = "px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-2";
        livePanel.classList.remove('hidden');
        reportPanel.classList.add('hidden');
      } else {
        reportBtn.className = "px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-2";
        liveBtn.className = "px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent flex items-center gap-2";
        reportPanel.classList.remove('hidden');
        livePanel.classList.add('hidden');
        document.getElementById('report-iframe').src = '/api/report?t=' + Date.now();
      }
    }

    function clearLogs() {
      document.getElementById('log-container').innerHTML = '';
      messageOffset = 0;
    }

    async function startAnalysis() {
      const ticker = document.getElementById('ticker-input').value.trim();
      const date = document.getElementById('date-input').value;
      const depth = document.getElementById('depth-select').value;
      const runBtn = document.getElementById('run-btn');

      const analysts = [];
      if (document.getElementById('analyst-market').checked) analysts.push('market');
      if (document.getElementById('analyst-news').checked) analysts.push('news');
      if (document.getElementById('analyst-fundamentals').checked) analysts.push('fundamentals');
      if (document.getElementById('analyst-social').checked) analysts.push('social');

      runBtn.disabled = true;
      runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Initializing Agents...';
      clearLogs();
      document.getElementById('ticker-completion-banner').classList.add('hidden');

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, date, depth, analysts, host: activeHost }),
        });
        const data = await res.json();
        if (data.error) {
          alert(data.error);
          runBtn.disabled = false;
          runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Multi-Agent Analysis';
          return;
        }

        switchTab('live');
        startPolling();
      } catch (err) {
        alert('Failed to connect: ' + err);
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Multi-Agent Analysis';
      }
    }

    function startPolling() {
      if (pollInterval) clearInterval(pollInterval);
      pollInterval = setInterval(pollStatus, 1500);
    }

    async function pollStatus() {
      try {
        const res = await fetch(`/api/status?offset=${messageOffset}`);
        const data = await res.json();

        // Update status pill
        const pill = document.getElementById('status-pill');
        if (data.log_file) {
          const lCont = document.getElementById('log-file-container');
          if (lCont) {
            lCont.classList.remove('hidden');
            document.getElementById('log-file-path').innerText = data.log_file;
          }
        }
        if (data.status === 'running') {
          pill.className = "text-xs px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium animate-pulse";
          pill.innerText = 'Analysis In Progress...';
        } else if (data.status === 'completed') {
          pill.className = "text-xs px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium";
          pill.innerText = 'Completed: ' + (data.final_decision || 'Success');
          clearInterval(pollInterval);
          document.getElementById('run-btn').disabled = false;
          document.getElementById('run-btn').innerHTML = '<i class="fa-solid fa-play"></i> Run Multi-Agent Analysis';

          // Show in-page completion banner
          const banner = document.getElementById('ticker-completion-banner');
          document.getElementById('completion-ticker').innerText = data.ticker || 'VEDPOWER';
          document.getElementById('completion-rating').innerText = data.final_decision || 'BUY';
          banner.classList.remove('hidden');

          // Automatically switch to report
          switchTab('report');
        } else if (data.status === 'error') {
          pill.className = "text-xs px-3 py-1 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30 font-medium";
          pill.innerText = 'Failed: ' + (data.error_message || 'Error');
          clearInterval(pollInterval);
          document.getElementById('run-btn').disabled = false;
          document.getElementById('run-btn').innerHTML = '<i class="fa-solid fa-play"></i> Run Multi-Agent Analysis';
        }

        // Update pipeline step badges
        updateBadge('step-analysts', data.agent_statuses.market === 'completed' && data.agent_statuses.news === 'completed');
        updateBadge('step-research', data.agent_statuses.researcher);
        updateBadge('step-trader', data.agent_statuses.trader);
        updateBadge('step-risk', data.agent_statuses.risk_mgmt);
        updateBadge('step-portfolio', data.agent_statuses.portfolio_manager);

        // Append new messages
        if (data.new_messages && data.new_messages.length > 0) {
          const container = document.getElementById('log-container');
          data.new_messages.forEach(msg => {
            const row = document.createElement('div');
            let color = 'text-slate-300';
            let tagBg = 'bg-slate-800 text-slate-300';

            if (msg.type === 'system') { color = 'text-cyan-400'; tagBg = 'bg-cyan-950/60 text-cyan-300 border border-cyan-800'; }
            else if (msg.type === 'error') { color = 'text-rose-400'; tagBg = 'bg-rose-950/60 text-rose-300 border border-rose-800'; }
            else if (msg.type === 'success') { color = 'text-emerald-400'; tagBg = 'bg-emerald-950/60 text-emerald-300 border border-emerald-800'; }

            row.className = "p-2 rounded bg-slate-950/70 border border-slate-800/80";
            row.innerHTML = `
              <div class="flex items-center space-x-2 mb-1">
                <span class="text-[10px] text-slate-500">${msg.timestamp}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold ${tagBg}">[${msg.sender}]</span>
              </div>
              <div class="${color} break-words whitespace-pre-wrap">${escapeHtml(msg.content)}</div>
            `;
            container.appendChild(row);
          });
          messageOffset = data.total_messages;
          container.scrollTop = container.scrollHeight;
        }

      } catch (err) {
        console.error('Polling error:', err);
      }
    }

    function updateBadge(id, status) {
      const badge = document.querySelector(`#${id} .status-badge`);
      if (!badge) return;
      if (status === 'completed' || status === true) {
        badge.className = "status-badge px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
        badge.innerText = 'done';
      } else if (status === 'in_progress') {
        badge.className = "status-badge px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse";
        badge.innerText = 'active';
      } else {
        badge.className = "status-badge px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-500";
        badge.innerText = 'pending';
      }
    }

    // ==========================================
    // MUTUAL FUND CLIENT LOGIC
    // ==========================================
    function loadMF(code) {
      document.getElementById('mf-query').value = code;
      fetchMFDetails();
    }

    async function fetchMFDetails() {
      const q = document.getElementById('mf-query').value.trim();
      if (!q) return;

      const resultsDiv = document.getElementById('mf-results');
      resultsDiv.classList.add('hidden');

      try {
        const res = await fetch(`/api/mf/details?code=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (data.error) {
          alert('Mutual Fund error: ' + data.error);
          return;
        }

        const meta = data.meta || {};
        document.getElementById('mf-scheme-name').innerText = meta.scheme_name || q;
        document.getElementById('mf-meta').innerText = `${meta.fund_house || 'Indian AMC'} • ${meta.scheme_category || 'Equity'}`;
        document.getElementById('mf-nav').innerText = `₹${parseFloat(data.current_nav || 0).toFixed(2)}`;
        document.getElementById('mf-nav-date').innerText = `As of ${data.last_updated || 'Latest'}`;

        const ret = data.returns || {};
        setReturn('mf-ret-1m', ret['1M']);
        setReturn('mf-ret-6m', ret['6M']);
        setReturn('mf-ret-1y', ret['1Y']);
        setReturn('mf-ret-3y', ret['3Y']);
        setReturn('mf-ret-5y', ret['5Y']);

        document.getElementById('mf-strategy').innerText = data.recommendation_rationale ||
          `This ${meta.scheme_category || 'fund'} is managed by ${meta.fund_house || 'AMC'}. Real-time tracking through AMFI NAV feeds shows consistent historical returns with risk alignment.`;

        resultsDiv.classList.remove('hidden');
      } catch (err) {
        alert('Failed to load Mutual Fund details: ' + err);
      }
    }

    function setReturn(id, val) {
      const el = document.getElementById(id);
      if (val !== undefined && val !== null) {
        const num = parseFloat(val);
        el.innerText = `${num >= 0 ? '+' : ''}${num.toFixed(1)}%`;
        el.className = num >= 0 ? "text-base font-bold text-emerald-400 mt-1" : "text-base font-bold text-rose-400 mt-1";
      } else {
        el.innerText = "N/A";
        el.className = "text-base font-bold text-slate-500 mt-1";
      }
    }

    // ==========================================
    // ETF CLIENT LOGIC
    // ==========================================
    async function fetchETFDetails() {
      const ticker = document.getElementById('etf-input').value.trim();
      if (!ticker) return;

      const resDiv = document.getElementById('etf-results');
      resDiv.classList.add('hidden');

      try {
        const res = await fetch(`/api/etf/details?ticker=${encodeURIComponent(ticker)}`);
        const data = await res.json();
        if (data.error) {
          alert('ETF error: ' + data.error);
          return;
        }

        document.getElementById('etf-name').innerText = data.name || ticker;
        document.getElementById('etf-badge').innerText = data.asset_class || 'ETF';
        document.getElementById('etf-benchmark').innerText = `Underlying: ${data.underlying_benchmark || 'Index'} • ${data.exchange || 'NSE'}`;
        document.getElementById('etf-price').innerText = `₹${parseFloat(data.current_price || 0).toFixed(2)}`;

        const high = parseFloat(data['52_week_high'] || 0);
        const low = parseFloat(data['52_week_low'] || 0);
        const curr = parseFloat(data.current_price || 0);

        document.getElementById('etf-low').innerText = `₹${low.toFixed(2)}`;
        document.getElementById('etf-high').innerText = `₹${high.toFixed(2)}`;

        let pct = 50;
        if (high > low) {
          pct = Math.max(0, Math.min(100, Math.round(((curr - low) / (high - low)) * 100)));
        }
        document.getElementById('etf-range-bar').style.width = `${pct}%`;

        document.getElementById('etf-volume').innerText = (data.volume || 0).toLocaleString();
        document.getElementById('etf-avg-volume').innerText = (data.average_volume || 0).toLocaleString();

        resDiv.classList.remove('hidden');
      } catch (err) {
        alert('Failed to load ETF: ' + err);
      }
    }

    // ==========================================
    // PORTFOLIO CLIENT LOGIC
    // ==========================================
    function addHoldingRow(ticker = '', qty = 10, buyPrice = 1000) {
      const container = document.getElementById('holdings-table-container');
      const row = document.createElement('div');
      row.className = "flex items-center gap-2 holding-row";
      row.innerHTML = `
        <input type="text" placeholder="Ticker (e.g. RELIANCE)" value="${ticker}" class="holding-ticker uppercase flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white">
        <input type="number" placeholder="Qty" value="${qty}" class="holding-qty w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white">
        <input type="number" placeholder="Buy Price (₹)" value="${buyPrice}" class="holding-price w-32 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white">
        <button onclick="this.parentElement.remove()" class="text-slate-500 hover:text-rose-400 p-1.5"><i class="fa-solid fa-trash-can"></i></button>
      `;
      container.appendChild(row);
    }

    function loadSamplePortfolio(preset) {
      const container = document.getElementById('holdings-table-container');
      container.innerHTML = '';
      if (preset === 'growth') {
        addHoldingRow('RELIANCE.NS', 20, 2750);
        addHoldingRow('TCS.NS', 15, 3400);
        addHoldingRow('INFY.NS', 25, 1420);
        addHoldingRow('TATAMOTORS.NS', 50, 680);
      } else {
        addHoldingRow('HDFCBANK.NS', 30, 1600);
        addHoldingRow('ITC.NS', 80, 420);
        addHoldingRow('NTPC.NS', 100, 310);
        addHoldingRow('BHARTIARTL.NS', 25, 1150);
      }
    }

    async function runPortfolioAudit() {
      const rows = document.querySelectorAll('.holding-row');
      const holdings = [];
      rows.forEach(r => {
        const ticker = r.querySelector('.holding-ticker').value.trim();
        const quantity = parseFloat(r.querySelector('.holding-qty').value || 0);
        const buy_price = parseFloat(r.querySelector('.holding-price').value || 0);
        if (ticker && quantity > 0) {
          holdings.push({ ticker, quantity, buy_price });
        }
      });

      if (holdings.length === 0) {
        alert('Please add at least one stock holding.');
        return;
      }

      currentPortfolioHoldings = holdings;
      const cash = parseFloat(document.getElementById('portfolio-cash').value || 0);
      const btn = document.getElementById('btn-run-portfolio');
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Auditing Portfolio...';

      try {
        const res = await fetch('/api/portfolio/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ holdings, cash }),
        });
        const data = await res.json();
        if (data.error) {
          alert('Portfolio Audit error: ' + data.error);
          btn.disabled = false;
          btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Full Portfolio Audit';
          return;
        }

        const s = data.summary;
        document.getElementById('port-invested').innerText = `₹${s.total_invested.toLocaleString()}`;
        document.getElementById('port-current').innerText = `₹${s.total_current_value.toLocaleString()}`;

        const pnlEl = document.getElementById('port-pnl');
        pnlEl.innerText = `₹${s.total_unrealized_pnl.toLocaleString()} (${s.total_pnl_percent >= 0 ? '+' : ''}${s.total_pnl_percent}%)`;
        pnlEl.className = s.total_unrealized_pnl >= 0 ? "text-xl font-bold text-emerald-400 mt-1" : "text-xl font-bold text-rose-400 mt-1";

        document.getElementById('port-hhi').innerText = s.hhi_index;
        document.getElementById('port-skew-risk').innerText = `${s.skew_status} (${s.skew_risk})`;

        // Populate Table
        const tbody = document.getElementById('portfolio-holdings-tbody');
        tbody.innerHTML = '';
        data.holdings.forEach(h => {
          const tr = document.createElement('tr');
          const pnlColor = h.pnl_percent >= 0 ? 'text-emerald-400' : 'text-rose-400';
          let actionColor = 'bg-slate-800 text-slate-300';
          if (h.recommendation === 'BUY') actionColor = 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
          else if (h.recommendation === 'SELL') actionColor = 'bg-rose-500/20 text-rose-300 border border-rose-500/30';

          tr.innerHTML = `
            <td class="py-2.5 px-3 font-semibold text-white">${h.ticker}<div class="text-[10px] text-slate-400">${h.sector}</div></td>
            <td class="py-2.5 px-3">${h.portfolio_weight.toFixed(1)}%</td>
            <td class="py-2.5 px-3 font-bold ${pnlColor}">${h.pnl_percent >= 0 ? '+' : ''}${h.pnl_percent.toFixed(1)}%</td>
            <td class="py-2.5 px-3">₹${h.current_price.toLocaleString()}</td>
            <td class="py-2.5 px-3">${h.stock_pe ? h.stock_pe.toFixed(1) : 'N/A'}</td>
            <td class="py-2.5 px-3">${h.industry_pe ? h.industry_pe.toFixed(1) : 'N/A'}</td>
            <td class="py-2.5 px-3">${h.roce ? h.roce.toFixed(1) + '%' : 'N/A'}</td>
            <td class="py-2.5 px-3">${h.sentiment_label} (${h.sentiment_score}/10)</td>
            <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${actionColor}">${h.recommendation}</span></td>
          `;
          tbody.appendChild(tr);
        });

        document.getElementById('portfolio-results').classList.remove('hidden');
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Full Portfolio Audit';
      } catch (err) {
        alert('Failed to audit portfolio: ' + err);
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Full Portfolio Audit';
      }
    }

    function exportHoldingsCSV() {
      if (!currentPortfolioHoldings || currentPortfolioHoldings.length === 0) {
        alert('No holdings to export.');
        return;
      }
      let csvContent = "data:text/csv;charset=utf-8,ticker,quantity,buy_price\\n";
      currentPortfolioHoldings.forEach(h => {
        csvContent += `${h.ticker},${h.quantity},${h.buy_price}\\n`;
      });
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `Tradex_Holdings_${new Date().toISOString().split('T')[0]}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    // ==========================================
    // SAVED REPORTS MODAL
    // ==========================================
    async function openSavedReportsModal() {
      document.getElementById('modal-saved-reports').classList.remove('hidden');
      const listEl = document.getElementById('saved-reports-list');
      listEl.innerHTML = '<div class="text-center text-slate-500 py-6">Loading reports...</div>';

      try {
        const res = await fetch('/api/reports/list');
        const items = await res.json();
        if (!items || items.length === 0) {
          listEl.innerHTML = '<div class="text-center text-slate-500 py-6">No saved reports found yet.</div>';
          return;
        }

        listEl.innerHTML = '';
        items.forEach(it => {
          const row = document.createElement('div');
          row.className = "flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition";
          row.innerHTML = `
            <div>
              <div class="font-bold text-white flex items-center gap-2">
                <span>${it.ticker}</span>
                <span class="text-[10px] text-slate-400 font-normal">${it.timestamp}</span>
              </div>
              <div class="text-[10px] text-slate-500 mono">${it.folder}</div>
            </div>
            <div class="flex items-center space-x-2">
              <a href="/api/reports/saved?folder=${encodeURIComponent(it.folder)}&format=html" target="_blank" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs">
                <i class="fa-solid fa-eye"></i> View
              </a>
              <a href="/api/reports/saved?folder=${encodeURIComponent(it.folder)}&format=html&download=1" download class="px-2.5 py-1 rounded bg-teal-600 hover:bg-teal-500 text-white text-xs">
                <i class="fa-solid fa-download"></i> HTML
              </a>
            </div>
          `;
          listEl.appendChild(row);
        });
      } catch (err) {
        listEl.innerHTML = `<div class="text-rose-400 text-center py-4">Failed to load reports: ${err}</div>`;
      }
    }

    function closeSavedReportsModal() {
      document.getElementById('modal-saved-reports').classList.add('hidden');
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
  </script>
</body>
</html>
"""
