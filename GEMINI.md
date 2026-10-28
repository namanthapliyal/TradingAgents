# GEMINI.md - Tradex Agent Development & Skill Activation Guide

This file guides Google Antigravity / Gemini agents working within the `tradex-agent` repository.

## 🚀 Core Mandate: Specialized Skills Activation

Whenever you are asked to perform coding, design, testing, debugging, or strategy work in this repository, **you must proactively reference and adhere to the specialized skills** installed under `.agents/skills/` (sourced from `agentic-awesome-skills`).

### Domain Skill Mapping

| Task Domain | Activated Skills (`.agents/skills/`) | Primary Focus & Principles |
| :--- | :--- | :--- |
| **LangGraph & Multi-Agent** | `langgraph`<br>`multi-agent-architect`<br>`llm-application-dev-langchain-agent`<br>`langchain-architecture`<br>`multi-agent-patterns` | Stateful graph construction, node/edge routing, checkpointers (`SqliteSaver`), supervisor & swarm patterns, state isolation, cycle handling, ReAct loops. |
| **Agent Evals, Memory & Security** | `agent-observability`<br>`agent-evals`<br>`agent-memory-systems`<br>`ai-agent-security`<br>`ai-engineer`<br>`llm-prompt-optimizer` | Traceability, token & cost metrics, automated eval rubrics, defense against prompt injection and tool abuse, prompt token optimization. |
| **Trading, Quant & Backtesting** | `backtesting-frameworks`<br>`quant-analyst`<br>`calibrate-first`<br>`krexa` | Rigorous backtesting without lookahead bias or survivorship bias, slippage & fee modeling, risk metrics (Sharpe, Sortino, max drawdown), signal detection floors. |
| **Python 3.11+ & Async Core** | `python-pro`<br>`async-python-patterns`<br>`python-development` | Modern Python features, strict type hinting (`typing`), `asyncio` streaming dataflows, resilient error handling, package structure. |
| **Testing & TDD** | `pytest-skill`<br>`python-testing-patterns`<br>`tdd`<br>`agentic-test-audit`<br>`agentic-verify` | Red-Green-Refactor, parameterized unit tests, mock external broker/dataflow APIs, test isolation, mutant testing, verifying coverage. |
| **Systematic Debugging** | `systematic-debugging`<br>`debugging-and-error-recovery` | 4-phase root cause analysis before making code edits. Hypothesize, isolate, reproduce with test, fix root cause, verify. |
| **Code Quality & Architecture** | `clean-code`<br>`clean-code-guard`<br>`code-refactoring-refactor-clean`<br>`code-review-checklist`<br>`architecture-patterns` | Robert C. Martin ("Uncle Bob") Clean Code, SOLID, DRY, Hexagonal / Clean Architecture, refactoring tech debt, pre-commit checklists. |
| **API, DevOps & Workflows** | `api-design-principles`<br>`container-hardening`<br>`git-pr-workflows-git-workflow` | REST API standards, Dockerfile minimal attack surface, structured Git branch & PR workflows. |

---

## 🏗️ Project Architecture Quick Reference

- **`tradingagents/`**: Core multi-agent trading framework
  - `dataflows/vendors/`: Market data providers (Screener.in, Moneycontrol, TradingView, Kotak Neo, Interactive Brokers)
  - `wallet/manager.py`: Central portfolio, risk rules, position sizing, live & paper modes
  - `strategies/`: Intraday technical momentum, long-term fundamental value
  - `analysis/`: Institutional flows (FII/DII), mutual fund analyzer
  - `alerting/manager.py`: Real-time notification & alert delivery
- **`cli/`**: Typer & Rich CLI application
- **`tests/`**: Pytest suite (run with `pytest -m "not integration"`)

---

## 🔧 Workflow Execution Standards

1. **Before Modifying Code**:
   - For bugs: Consult `systematic-debugging` or `debugging-and-error-recovery`. Formulate a hypothesis and create a reproducing test.
   - For architecture/agents: Consult `langgraph` and `multi-agent-architect`. Ensure state schemas and nodes are properly defined.
   - For trading logic: Consult `backtesting-frameworks` and `quant-analyst`. Verify assumptions against bias.

2. **Writing Code**:
   - Follow `clean-code` and `python-pro`. Use explicit types and docstrings.
   - For async tasks: Follow `async-python-patterns`.

3. **Verifying Code**:
   - Run `pytest` to verify changes.
   - Run `ruff check .` and `ruff format .` to maintain code standards.

