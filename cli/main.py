import sys

import typer

from cli.display import console
from cli.models import AnalystType, AssetType
from cli.prompts import filter_analysts_for_asset_type, parse_analysts
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import load_portfolio

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


def _execute_analysis(
    checkpoint: bool | None,
    clear_checkpoints: bool,
    portfolio: str | None,
    ticker: str | None,
    date: str | None,
    analysts: str | None,
    save: bool | None,
    show: bool | None,
    html: bool | None,
    host: str | None = None,
    colab: bool = False,
    local: bool = False,
):
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints

        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    portfolio_context = None
    if portfolio:
        try:
            portfolio_context = load_portfolio(portfolio)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    try:
        flags = {
            "ticker": ticker,
            "date": date,
            "analysts": analysts,
            "save": save,
            "show": show,
            "html": html,
        }
        if host is not None:
            flags["host"] = host
        if colab:
            flags["colab"] = colab
        if local:
            flags["local"] = local
        run_analysis(checkpoint=checkpoint, portfolio=portfolio_context, flags=flags)
    except _NO_CONSOLE_ERRORS:
        # A terminal with no console buffer cannot host the interactive prompts.
        # Emit one actionable line on stderr instead of a prompt_toolkit
        # traceback; plain text, since rich may not render here either (#1138).
        typer.echo(
            "Error: no Windows console available. The interactive CLI needs a real "
            "console buffer — run it from Windows Terminal, PowerShell, or cmd.exe "
            "rather than a piped or embedded terminal.",
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def analyze(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="JSON file with current holdings and cash, so the trader, risk and "
        "portfolio agents size against your actual position.",
    ),
    ticker: str = typer.Option(
        None, "--ticker", help="Ticker to analyze, e.g. NVDA or 0700.HK; skips the prompt"
    ),
    date: str = typer.Option(None, "--date", help="Analysis date, YYYY-MM-DD; skips the prompt"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts, e.g. market,news; skips the prompt"
    ),
    save: bool | None = typer.Option(
        None, "--save/--no-save", help="Save the report under results_dir without asking"
    ),
    show: bool | None = typer.Option(
        None, "--show/--no-show", help="Show the full report at the end without asking"
    ),
    html: bool | None = typer.Option(
        None,
        "--html/--no-html",
        help="Save the report as one HTML page too, complete_report.html, without asking (default: yes)",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="LLM host: 'colab' (Google Colab via Cloudflare tunnel) or 'local'/'self-hosted' (Ollama).",
    ),
    colab: bool = typer.Option(
        False,
        "--colab",
        help="Use Google Colab hosted LLM (shorthand for --host colab).",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "--self-hosted",
        help="Use self-hosted local Ollama LLM (shorthand for --host local).",
    ),
):
    """Run an analysis. This is what a bare `tradingagents` does.

    Flags answer their questions; with provider, models, depth and language also
    set through TRADINGAGENTS_* variables, the run asks nothing.
    """
    if ctx.invoked_subcommand is not None:
        return
    _execute_analysis(
        checkpoint,
        clear_checkpoints,
        portfolio,
        ticker,
        date,
        analysts,
        save,
        show,
        html,
        host=host,
        colab=colab,
        local=local,
    )


@app.command(name="run")
def run_command(
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="JSON file with current holdings and cash, so the trader, risk and "
        "portfolio agents size against your actual position.",
    ),
    ticker: str = typer.Option(
        None, "--ticker", help="Ticker to analyze, e.g. VEDPOWER, 122639, NIFTYBEES"
    ),
    date: str = typer.Option(None, "--date", help="Analysis date, YYYY-MM-DD; skips the prompt"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts, e.g. market,news; skips the prompt"
    ),
    save: bool | None = typer.Option(
        None, "--save/--no-save", help="Save the report under results_dir without asking"
    ),
    show: bool | None = typer.Option(
        None, "--show/--no-show", help="Show the full report at the end without asking"
    ),
    html: bool | None = typer.Option(
        None,
        "--html/--no-html",
        help="Save the report as one HTML page too, complete_report.html, without asking (default: yes)",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="LLM host: 'colab' (Google Colab via Cloudflare tunnel) or 'local'/'self-hosted' (Ollama).",
    ),
    colab: bool = typer.Option(
        False,
        "--colab",
        help="Use Google Colab hosted LLM (shorthand for --host colab).",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "--self-hosted",
        help="Use self-hosted local Ollama LLM (shorthand for --host local).",
    ),
):
    """Run multi-agent trading analysis for a ticker (alias for default command)."""
    _execute_analysis(
        checkpoint,
        clear_checkpoints,
        portfolio,
        ticker,
        date,
        analysts,
        save,
        show,
        html,
        host=host,
        colab=colab,
        local=local,
    )


@app.command()
def backtest(
    tickers: str = typer.Argument(..., help="Comma-separated tickers, e.g. NVDA,AAPL"),
    start: str = typer.Option(..., "--start", help="First analysis date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Last analysis date, YYYY-MM-DD"),
    every: int = typer.Option(7, "--every", help="Days between analysis dates"),
    analysts: str = typer.Option(
        None,
        "--analysts",
        help="Comma-separated analysts to run: market, sentiment, news, fundamentals; omit for all the asset type allows",
    ),
    asset_type: str = typer.Option("stock", "--asset-type", help="stock or crypto"),
    portfolio: str = typer.Option(
        None, "--portfolio", help="JSON file with holdings and cash, held constant across the grid"
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="Continue an earlier sweep: its cells are skipped and its log reused"
    ),
):
    """Score past decisions over a grid of tickers and dates."""

    try:
        dates = iter_grid(start, end, every)
        book = load_portfolio(portfolio) if portfolio else None
        kind = AssetType(asset_type.strip().lower())
        # The analysts are named and checked as for an analysis; without a
        # choice, every analyst the asset type allows runs.
        chosen = (
            parse_analysts(analysts, kind)
            if analysts
            else filter_analysts_for_asset_type(list(AnalystType), kind)
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    names = [t.strip() for t in tickers.split(",") if t.strip()]
    if not names:
        console.print("[red]No ticker to analyze; pass them comma-separated, e.g. NVDA,AAPL[/red]")
        raise typer.Exit(code=1)

    def show_progress(done, total, ticker, date):
        console.print(f"[dim][{done}/{total}] {ticker} {date}[/dim]")

    kwargs = {
        "asset_type": kind.value,
        "portfolio": book,
        "run_id": run_id,
        "progress": show_progress,
        "selected_analysts": [a.value for a in chosen],
    }

    try:
        result = run_backtest(names, dates, DEFAULT_CONFIG, **kwargs)
    except Exception as exc:  # a missing key or an unknown analyst is a setup error
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(summarize(result).render())
    console.print(
        f"\nRan {result.cells_run} cells, skipped {result.skipped}. Log: {result.log_path}"
    )
    console.print(f"Continue or settle this sweep: --run-id {result.run_id}")
    for ticker, date, reason in result.failures:
        console.print(f"[yellow]failed:[/yellow] {ticker} {date}: {reason}")
    for ticker, reason in result.settlement_failures:
        console.print(f"[yellow]unsettled:[/yellow] {ticker}: {reason}")


@app.command("portfolio-analyze")
def portfolio_analyze(
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        "-p",
        help="Path to portfolio JSON or CSV file",
    ),
    holdings: str = typer.Option(
        None,
        "--holdings",
        help="Comma-separated ticker:quantity:buy_price (e.g. 'RELIANCE:100:1050,TCS:50:2200')",
    ),
    cash: float = typer.Option(
        0.0,
        "--cash",
        "-c",
        help="Free cash available in INR",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Save markdown analysis report to this file",
    ),
):
    """Analyze an Indian stock portfolio profile: fundamentals, news sentiment, sector skew, and recommendations."""
    import csv
    import json
    import os

    from tradingagents.analysis.portfolio_analyzer import PortfolioAnalyzer

    holdings_list = []
    if portfolio:
        if not os.path.exists(portfolio):
            console.print(f"[red]Error: Portfolio file not found: {portfolio}[/red]")
            raise typer.Exit(code=1)
        if portfolio.endswith(".json"):
            with open(portfolio, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "positions" in data:
                    holdings_list = data["positions"]
                    if "cash" in data and cash == 0.0:
                        cash = float(data["cash"])
                elif isinstance(data, list):
                    holdings_list = data
        elif portfolio.endswith(".csv"):
            with open(portfolio, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    holdings_list.append(
                        {
                            "ticker": r.get("ticker") or r.get("symbol") or r.get("Stock", ""),
                            "quantity": float(
                                r.get("quantity") or r.get("qty") or r.get("Shares", 0)
                            ),
                            "buy_price": float(
                                r.get("buy_price") or r.get("average_price") or r.get("Price", 0)
                            ),
                        }
                    )
    elif holdings:
        for item in holdings.split(","):
            parts = item.strip().split(":")
            if len(parts) >= 3:
                holdings_list.append(
                    {
                        "ticker": parts[0].strip(),
                        "quantity": float(parts[1].strip()),
                        "buy_price": float(parts[2].strip()),
                    }
                )
    else:
        console.print(
            "[yellow]No portfolio input specified. Running demonstration with sample Indian holdings...[/yellow]\n"
        )
        holdings_list = [
            {"ticker": "RELIANCE", "quantity": 100, "buy_price": 1050.0},
            {"ticker": "TCS", "quantity": 50, "buy_price": 2200.0},
            {"ticker": "HDFCBANK", "quantity": 150, "buy_price": 650.0},
            {"ticker": "INFY", "quantity": 80, "buy_price": 1500.0},
            {"ticker": "TATAMOTORS", "quantity": 120, "buy_price": 720.0},
            {"ticker": "ITC", "quantity": 200, "buy_price": 425.0},
        ]
        cash = 100000.0

    analyzer = PortfolioAnalyzer(cash=cash)
    console.print(
        f"[cyan]Evaluating {len(holdings_list)} portfolio holdings with Screener.in fundamentals and Google News India...[/cyan]"
    )
    results = analyzer.evaluate_portfolio(holdings_list)
    markdown_report = analyzer.format_markdown_report(results)

    console.print(markdown_report)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        console.print(f"\n[green][+] Analysis saved to: {output}[/green]")


@app.command("ui")
@app.command("web")
def web_ui(
    port: int = typer.Option(8080, "--port", "-p", help="Port to serve the Web Dashboard on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind to"),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Do not open browser automatically"
    ),
):
    """Launch the interactive Tradex Agent Web Dashboard in your browser."""
    from cli.web_app import run_web_server

    run_web_server(host=host, port=port, open_browser=not no_browser)


if __name__ == "__main__":
    app()
