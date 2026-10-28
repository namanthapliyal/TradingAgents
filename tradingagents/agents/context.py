"""Prompt context shared by the agents: instrument identity, output language and portfolio."""

import functools
import logging
from collections.abc import Mapping
from typing import Any

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.vendors.yahoo.fundamentals import get_company_profile

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    # The labelled lines are read by the program, so they keep their English
    # label and value: a translated rating line leaves the reader prose to
    # search, where a negated rating ("not a Sell") reads as the call (#1435).
    return (
        f" Write your entire response in {lang}, except the labelled lines the format"
        f" asks for (the \"**Rating**:\" line, \"FINAL TRANSACTION PROPOSAL:\"):"
        f" keep their label and value in English, exactly as specified."
    )


def opponent_argument_or_opening(text: str, opponent: str) -> str:
    """Opponent's latest argument, or an explicit opening marker when empty.

    The first speaker in each debate round receives an empty opponent response;
    interpolating it into a "refute the opponent" prompt makes the model
    fabricate the other side's position. Returning a clear "has not spoken yet"
    marker instead lets it open with its own case (#1176).
    """
    text = (text or "").strip()
    if text:
        return text
    return f"(The {opponent} has not spoken yet — open the debate with your own case.)"


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. An answer
    is cached for the process; a failed lookup is asked again next time.

    Identity resolves for the same instrument the price path fetches
    (``XAUUSD`` -> ``GC=F``, #983).
    """
    try:
        return _identity(ticker)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}


@functools.lru_cache(maxsize=256)
def _identity(ticker: str) -> dict:
    """The vendor's identity fields for ``ticker``; raises if the lookup fails."""
    identity: dict[str, str] = {}
    clean_ticker = ticker.strip()

    # 1. Check if Indian Mutual Fund (AMFI scheme code or MF keywords)
    if clean_ticker.isdigit() or any(
        w in clean_ticker.lower()
        for w in [
            "mutual fund",
            "flexi cap",
            "small cap",
            "large cap",
            "mid cap",
            "growth option",
            "direct plan",
        ]
    ):
        try:
            from tradingagents.dataflows.vendors.amfi_mf import get_mutual_fund_details

            mf = get_mutual_fund_details(clean_ticker)
            if mf:
                identity["company_name"] = mf.get("scheme_name", clean_ticker)
                identity["sector"] = mf.get("category", "Mutual Fund")
                identity["industry"] = mf.get("fund_house", "Indian AMC")
                identity["quote_type"] = "MUTUAL_FUND"
                identity["exchange"] = "AMFI India"
                return identity
        except Exception:
            pass

    # 2. Check if Indian ETF (e.g. NIFTYBEES, GOLDBEES, BANKBEES, MON100)
    upper_ticker = clean_ticker.upper()
    if (
        upper_ticker.endswith("BEES")
        or upper_ticker.endswith("BEES.NS")
        or upper_ticker.endswith("ETF")
        or upper_ticker.endswith("ETF.NS")
        or upper_ticker in {"MON100", "CPSEETF", "JUNIORBEES"}
    ):
        try:
            from tradingagents.dataflows.vendors.etf_vendor import get_etf_details

            etf = get_etf_details(clean_ticker)
            if etf:
                identity["company_name"] = etf.get("name", clean_ticker)
                identity["sector"] = etf.get("asset_class", "Exchange Traded Fund")
                identity["industry"] = etf.get("underlying_benchmark", "Benchmark Index")
                identity["quote_type"] = "ETF"
                identity["exchange"] = "NSE India"
                return identity
        except Exception:
            pass

    # 3. Standard yfinance company profile
    try:
        info = get_company_profile(ticker)
        company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
            info.get("shortName")
        )
        if company_name:
            identity["company_name"] = company_name
        for source_key, target_key in (
            ("sector", "sector"),
            ("industry", "industry"),
            ("exchange", "exchange"),
            ("quoteType", "quote_type"),
        ):
            value = _clean_identity_value(info.get(source_key))
            if value:
                identity[target_key] = value
        if identity.get("company_name"):
            return identity
    except Exception:
        pass

    # 4. Fallback for Indian stocks via Screener.in
    if not identity.get("company_name"):
        try:
            from tradingagents.dataflows.vendors.screener_in.fundamentals import (
                get_fundamentals_dict,
            )

            screener_data = get_fundamentals_dict(clean_ticker)
            if screener_data.get("company_name"):
                identity["company_name"] = screener_data["company_name"]
                if screener_data.get("sector"):
                    identity["sector"] = screener_data["sector"]
                if screener_data.get("industry"):
                    identity["industry"] = screener_data["industry"]
                identity["exchange"] = "NSE / BSE India"
                identity["quote_type"] = "EQUITY"
        except Exception:
            pass

    if not identity:
        raise ValueError(f"Could not resolve identity for {ticker}")
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
    trade_date: str | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity, asset type, and ticker."""
    identity = identity or {}
    quote_type = identity.get("quote_type", "").upper()

    is_crypto = asset_type == "crypto" or quote_type == "CRYPTOCURRENCY"
    is_mf = asset_type in ("mutual_fund", "mf") or quote_type == "MUTUAL_FUND"
    is_etf = asset_type == "etf" or quote_type == "ETF"

    if is_crypto:
        instrument_label = "crypto asset"
    elif is_mf:
        instrument_label = "Indian mutual fund scheme"
    elif is_etf:
        instrument_label = "Indian exchange traded fund (ETF)"
    else:
        instrument_label = "equity stock"

    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "The tools serve this instrument; refer to it by this exact ticker/code in every report and recommendation, "
        "preserving any exchange suffix (e.g. `.NS`, `.BO`, `-USD`)."
    )

    name = identity.get("company_name") or identity.get("name")
    if is_crypto:
        label = "Name"
    elif is_mf:
        label = "Scheme Name"
    elif is_etf:
        label = "ETF Name"
    else:
        label = "Company"

    details = []
    if is_historical(trade_date):
        if name:
            details.append(
                f"{label}: {name} (its current name, given only to identify it; "
                f"on {trade_date} it may have been named differently)"
            )
    else:
        if name:
            details.append(f"{label}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Classification / Category: {sector} / {industry}")
        elif sector:
            details.append(f"Category / Sector: {sector}")
        elif industry:
            details.append(f"Industry / Benchmark: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or asset unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    elif is_mf:
        context += (
            " Treat it as an Indian Mutual Fund (AMFI/SEBI regulated). It trades on daily NAV rather than corporate share prices. "
            "Do not look for corporate income statements or balance sheets; instead evaluate NAV historical returns (1M, 6M, 1Y, 3Y, 5Y), "
            "category benchmark comparison, fund house track record, and suitability for SIP or lumpsum investment using `get_mutual_fund_info`."
        )
    elif is_etf:
        context += (
            " Treat it as an Exchange Traded Fund (ETF) listed on Indian exchanges. "
            "Evaluate underlying benchmark index replication, trading liquidity/spread, expense ratio, and broader thematic trend using `get_etf_info`."
        )
    else:
        context += (
            " Treat it as an Indian equity stock. Focus on corporate operational metrics, EBITDA margins, ROCE, Net Profit, "
            "P/E valuation versus industry peers, and business moats using `get_fundamentals` and `get_news`."
        )

    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a yfinance call mid-graph.
    """
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(
        str(state["company_of_interest"]),
        state.get("asset_type", "stock"),
    )


def report_or_absent(text: str, source: str) -> str:
    """An analyst's report, or a marker saying it was never produced.

    A report is empty when its analyst was not selected, refused, or returned
    nothing. Interpolating that into a labelled section presents an absence as a
    blank finding, and the reading agent fills it in from nothing, the same way
    an empty opponent argument used to invite an invented rebuttal (#1176).
    """
    text = (text or "").strip()
    if text:
        return text
    return f"(No {source} report in this run: it is not available, not an empty finding.)"


def get_portfolio_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the caller's portfolio block, or a notice that none was given.

    A run without portfolio context must not read as a flat book: the agents
    would otherwise size as if the caller held nothing, which is a claim about
    an account we were never told about.
    """
    context = state.get("portfolio_context")
    if isinstance(context, str) and context.strip():
        return context
    return (
        "Portfolio context: not provided. You do not know the caller's current "
        "holdings or cash, so do not assume a flat book; give direction and "
        "sizing guidance in terms the caller can apply to their own position."
    )
