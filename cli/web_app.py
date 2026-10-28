"""Web UI Dashboard for TradingAgents.

Runs a local web server (pure standard library http.server) providing an
interactive web browser UI to configure runs, monitor agent progress in real time
without terminal truncation, and view full markdown/HTML reports.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from tradingagents.default_config import build_default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.report_html import render_report
from tradingagents.reporting import _report_parts


def build_html_report(final_state: dict, ticker: str, settings: dict | None = None) -> str:
    """Render the full standalone HTML report."""
    parts = _report_parts(final_state)
    return render_report(ticker, final_state, settings, parts)


class AnalysisState:
    """Thread-safe state store for active and completed runs."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
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
            self.final_decision: str | None = None
            self.final_state: dict[str, Any] | None = None

    def add_message(self, sender: str, content: str, msg_type: str = "message") -> None:
        with self.lock:
            self.messages.append(
                {
                    "id": len(self.messages),
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    "sender": sender,
                    "content": content,
                    "type": msg_type,
                }
            )

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
                "agent_statuses": dict(self.agent_statuses),
                "new_messages": self.messages[offset:],
                "total_messages": len(self.messages),
                "has_report": bool(self.report_html),
                "final_decision": self.final_decision,
            }


GLOBAL_STATE = AnalysisState()


def _run_pipeline_worker(params: dict[str, Any]) -> None:
    """Execute the TradingAgents graph in a background thread."""
    ticker = params.get("ticker", "VEDPOWER").strip().upper()
    trade_date = params.get("date") or datetime.date.today().isoformat()
    host_mode = params.get("host", "colab").strip().lower()
    analysts = params.get("analysts", ["market", "news", "fundamentals"])
    if isinstance(analysts, str):
        analysts = [a.strip() for a in analysts.split(",") if a.strip()]

    depth = int(params.get("depth", 1))

    with GLOBAL_STATE.lock:
        GLOBAL_STATE.status = "running"
        GLOBAL_STATE.ticker = ticker
        GLOBAL_STATE.trade_date = trade_date
        GLOBAL_STATE.host_mode = host_mode
        GLOBAL_STATE.messages.clear()
        GLOBAL_STATE.error_message = None
        GLOBAL_STATE.report_html = None
        GLOBAL_STATE.final_decision = None
        for k in GLOBAL_STATE.agent_statuses:
            GLOBAL_STATE.agent_statuses[k] = "in_progress" if k in analysts else "pending"

    GLOBAL_STATE.add_message(
        "System", f"Starting multi-agent trading analysis for {ticker} ({trade_date})...", "system"
    )
    GLOBAL_STATE.add_message("System", f"Selected Host Mode: {host_mode.upper()}", "system")
    GLOBAL_STATE.add_message("System", f"Active Analysts: {', '.join(analysts)}", "system")

    # Build run configuration
    os.environ["TRADINGAGENTS_LLM_HOST"] = host_mode
    config = build_default_config()
    config["max_debate_rounds"] = depth
    config["max_risk_discuss_rounds"] = depth

    if host_mode == "colab":
        colab_url = params.get("colab_url") or os.environ.get("COLAB_LLM_URL")
        if colab_url:
            config["backend_url"] = colab_url
        GLOBAL_STATE.add_message(
            "System", f"Connecting via Colab endpoint: {config.get('backend_url')}", "system"
        )
    else:
        local_url = os.environ.get("LOCAL_LLM_URL") or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434/v1"
        )
        config["backend_url"] = local_url
        GLOBAL_STATE.add_message("System", f"Connecting via Local Ollama: {local_url}", "system")

    try:
        graph = TradingAgentsGraph(selected_analysts=analysts, config=config, debug=False)
        init_agent_state = graph.create_run_state(ticker, trade_date, "stock")
        graph_args = graph.propagator.get_graph_args()

        # Step through the graph execution
        final_state = dict(init_agent_state)
        for chunk in graph.graph.stream(init_agent_state, graph_args, stream_mode="values"):
            final_state = dict(chunk)

            # Update analyst progress
            for a in analysts:
                report_key = f"{a}_report"
                if report_key in chunk and chunk[report_key]:
                    GLOBAL_STATE.update_agent(a, "completed")

            # Check research progress
            if chunk.get("bull_statement") or chunk.get("bear_statement"):
                GLOBAL_STATE.update_agent("researcher", "in_progress")
            if chunk.get("investment_plan"):
                GLOBAL_STATE.update_agent("researcher", "completed")
                GLOBAL_STATE.update_agent("trader", "in_progress")

            # Check trader progress
            if chunk.get("trader_investment_plan"):
                GLOBAL_STATE.update_agent("trader", "completed")
                GLOBAL_STATE.update_agent("risk_mgmt", "in_progress")

            # Check risk progress
            if chunk.get("final_trade_decision"):
                GLOBAL_STATE.update_agent("risk_mgmt", "completed")
                GLOBAL_STATE.update_agent("portfolio_manager", "completed")
                GLOBAL_STATE.final_decision = chunk.get("final_trade_decision")

            # Log updates
            if "messages" in chunk and chunk["messages"]:
                last_msg = chunk["messages"][-1]
                content = getattr(last_msg, "content", str(last_msg))
                sender = getattr(last_msg, "name", "Agent")
                if content and isinstance(content, str):
                    clean_text = content.strip().replace("\n\n", " ")[:400]
                    GLOBAL_STATE.add_message(sender, clean_text, "agent")

        # Generate complete HTML report
        html = build_html_report(final_state, ticker, config)

        with GLOBAL_STATE.lock:
            GLOBAL_STATE.final_state = final_state
            GLOBAL_STATE.report_html = html
            GLOBAL_STATE.status = "completed"
            for k in GLOBAL_STATE.agent_statuses:
                GLOBAL_STATE.agent_statuses[k] = "completed"

        GLOBAL_STATE.add_message(
            "System", f"Analysis completed successfully for {ticker}!", "success"
        )

    except Exception as exc:
        with GLOBAL_STATE.lock:
            GLOBAL_STATE.status = "error"
            GLOBAL_STATE.error_message = str(exc)
        GLOBAL_STATE.add_message("Error", f"Execution failed: {exc}", "error")


class WebDashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the TradingAgents Web UI."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stdout access logs to keep terminal quiet."""
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
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
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
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
                    "<h3>No report has been generated yet.</h3>", status=HTTPStatus.NOT_FOUND
                )
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

            # Spawn worker thread
            worker = threading.Thread(target=_run_pipeline_worker, args=(params,), daemon=True)
            worker.start()
            self._send_json({"message": "Analysis started successfully."})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def run_web_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the interactive TradingAgents web dashboard server."""
    server = ThreadingHTTPServer((host, port), WebDashboardHandler)
    url = f"http://{host}:{port}"
    print("\n============================================================")
    print(f"🚀 Tradex Agent Web Dashboard is running at: {url}")
    print("Interactive inputs, real-time uncropped progress & live HTML report!")
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

  <!-- Top Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20 font-bold text-xl">
        <i class="fa-solid fa-chart-line"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          Tradex Agent <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">v0.6.0 Live</span>
        </h1>
        <p class="text-xs text-slate-400">12-Agent Financial Intelligence Framework</p>
      </div>
    </div>

    <!-- Active LLM Host Pill -->
    <div class="flex items-center space-x-4">
      <div id="host-indicator" class="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-slate-300 font-medium" id="current-host-display">Google Colab Hosted</span>
      </div>
      <a href="/api/report" target="_blank" id="open-report-btn" class="hidden px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow transition">
        <i class="fa-solid fa-file-invoice"></i> Open Full Report
      </a>
    </div>
  </header>

  <!-- Main Container -->
  <div class="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">

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
            <button onclick="setTicker('122639')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">Parag Parikh MF</button>
            <button onclick="setTicker('NIFTYBEES')" class="px-2 py-0.5 rounded text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">NIFTY ETF</button>
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
        <div class="flex items-center justify-between text-xs text-slate-400 pb-3 border-b border-slate-800">
          <span>Real-time Uncropped Messages & Agent Tool Calls</span>
          <button onclick="clearLogs()" class="hover:text-slate-200"><i class="fa-solid fa-trash-can"></i> Clear</button>
        </div>
        <div id="log-container" class="flex-1 overflow-y-auto space-y-2.5 pt-3 mono text-xs leading-relaxed max-h-[600px]">
          <div class="text-slate-500 italic p-4 text-center">No analysis running. Fill in parameters and click "Run Multi-Agent Analysis" above.</div>
        </div>
      </div>

      <!-- Full Report Frame Container -->
      <div id="panel-report" class="hidden flex-1 bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl min-h-[620px] flex flex-col">
        <iframe id="report-iframe" class="w-full flex-1 min-h-[600px] border-none bg-white" src="about:blank"></iframe>
      </div>

    </div>
  </div>

  <script>
    let activeHost = 'colab';
    let pollInterval = null;
    let messageOffset = 0;

    document.getElementById('date-input').value = new Date().toISOString().split('T')[0];

    function setTicker(t) {
      document.getElementById('ticker-input').value = t;
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
        if (data.status === 'running') {
          pill.className = "text-xs px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium animate-pulse";
          pill.innerText = 'Analysis In Progress...';
        } else if (data.status === 'completed') {
          pill.className = "text-xs px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium";
          pill.innerText = 'Completed: ' + (data.final_decision || 'Success');
          clearInterval(pollInterval);
          document.getElementById('run-btn').disabled = false;
          document.getElementById('run-btn').innerHTML = '<i class="fa-solid fa-play"></i> Run Multi-Agent Analysis';
          document.getElementById('open-report-btn').classList.remove('hidden');
          // Automatically show report
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

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
  </script>
</body>
</html>
"""
