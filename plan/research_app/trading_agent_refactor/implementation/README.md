# Trading Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V2 relative-strength catalyst trading workflow in reviewable PR slices, starting with a verifiable MVP of universe -> point-in-time signal snapshots -> strategy scoring -> historical replay/outcome evaluation before adding paper trading, options, intraday refresh, reflection, learning adaptation, strategy evolution, and UI.

**Architecture:** Keep Python orchestration as the source of truth. LLM calls are bounded, Pydantic-validated, retried on schema failure, and downgraded to safe fallbacks when validation still fails. Each pipeline persists point-in-time snapshots with `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at` so candidate selection, trade identity, confidence calibration, replay outcomes, risk decisions, paper stock/options orders, worst-case assignment exposure, portfolio state, prompt versions, LLM calls, reflection, and learning factors can be audited without lookahead.

**Tech Stack:** Python, SQLAlchemy, Alembic, Postgres JSONB, FastAPI/Jinja, APScheduler, pytest, existing market/news/global-context providers.

**Contracts:** Before changing any PR module, check [Module Contracts](../module_contracts.md). The PR modules are split for readability but keep the original PR order and stop-after-review policy.

**Reading Guide:** Use [PR Reading Guide](reading_guide.md) to choose the smallest design-module set needed for the current PR. Do not load every design and implementation module by default.

---

## Execution Rules

- Each PR slice stops after verification. Do not begin the next slice until the user has reviewed and merged.
- Use TDD for implementation code: write failing tests, run targeted tests, implement, rerun targeted tests, then run the broader relevant suite.
- After every completed implementation slice, update `plan/research_app/trading_agent_refactor/progress_tracker.md`.
- For major refactor slices, update `documents/repo_overview.md`. If the file is absent, create it with the current architecture summary.
- For Python commands, run `source ~/.venv/bin/activate` first.
- Any DB/API smoke test must be standalone and rate-limit conscious.
- Unit tests must use fake providers. Integration tests that touch external-provider behavior should use recorded `vcrpy` cassettes or equivalent fixtures. Live provider smoke tests are opt-in and must not block ordinary CI.
- Deployment changes must preserve Docker Compose and persistent disk Postgres requirements.

## PR Slice Overview

1. **PR 1a: Minimal Trading Foundation**
   Add only the minimum durable foundation: strategy definition schema, prompt registry/schema, portfolio-pool trade identity enums, and a versioned in-code seed catalog for the 15 broad tactical strategies, 4 eval-derived playbook strategies, and 5 initial strategy expression buckets from the design doc, including defined-risk option expressions. No universe, source ingestion, relationship graph, scheduler, API calls, or trading behavior yet.
2. **PR 1b: Portfolio Intents + Relationship Graph Schema**
   Add `portfolio_intents`, `ticker_relationships`, `peer_baskets`, and `theme_taxonomy` plus focused services/tests for core-holding eligibility and structured peer/theme read-through inputs. No signal pipeline or strategy scoring yet.
3. **PR 2: Provider Resilience + Three-Family Point-in-Time Signal MVP**
   Add provider adapter guardrails, fake providers, request budgeting/rate-limit/backoff/circuit-breaker metadata, user-editable liquidity/sector universe filters, manual ticker request ingestion, and deterministic pre-open signal snapshots across MVP technical, fundamental, and events/news signal families.
4. **PR 3: Strategy Matching + Historical Replay Outcome Evaluator**
   Match scanner and manual-request symbols to strategy definitions and persist ranked candidates with strategy horizon/evidence, source attribution, primary strategy selection, trade identity classification, catalyst-watch vs ordinary-watch distinction, confidence-calibration inputs, and deterministic replay/outcome evaluation against `SPY`, `QQQ`, sector/theme ETF, and decision-time peer baskets.
5. **PR 4: Position Sizing + Portfolio Risk Manager**
   Add deterministic sizing, risk appetite presets, generated risk configs, risk factor exposure calculation, unified margin-account buying-power caps, conservative broker-profile margin estimates, concentration caps, embedded bearish-evidence gating, and reduce/reject decisions.
6. **PR 5: Trading Decision Agent Guardrails**
   Add bounded trading agent output with Pydantic schema validation, retry, safe fallback, manual request mode gating, prompt/schema persistence, and no paper order side effects yet.
7. **PR 6: Alpaca-Backed Paper Stock Broker + Portfolio State**
   Add Alpaca-backed stock paper orders/executions, broker-synced positions, and unified paper margin-account portfolio snapshots with margin model profile/source metadata.
8. **PR 7: Paper Options Strategy Layer + Assignment Risk**
   Add paper-only leg-based option strategy decisions, option legs, option orders/positions, open/close/roll/adjust/avoid-event actions, an initial whitelist of long call/put, credit spread, long straddle, and long strangle strategies, strategy-level option risk, conservative option margin requirements, and worst-case assigned-portfolio risk checks when assignment is possible.
9. **PR 8: Intraday Signal Refresh + News Alerts + Rebalance**
   Add hourly intraday signal refresh, normalized alerts, material signal-change detection, and risk-gated intraday rebalance decisions for stocks, paper option strategies, and hedge overlays.
10. **PR 9: Reflection + Learning Factors**
   Add post-close reflection with highest-quality model routing, Pydantic validation/fallback, learning factor lifecycle defaulting to candidate/observation, replay outcome consumption, benchmark/peer attribution, bullish/bearish calibration, paper options attribution, and strategy proposal hints.
11. **PR 10: Strategy Evolution + Dynamic Strategy Catalog**
   Convert repeated learning patterns into proposed strategies, shadow-test them, and promote/retire strategy definitions.
12. **PR 11: Today Dashboard UI**
   Add `/today`, pinned review, candidate, trade, options, risk exposure, reflection, and learning views.
13. **PR 12: Scheduler, Smoke Tests, Deploy Docs**
   Wire daily jobs, standalone smoke scripts, and deployment/runbook docs.

## PR Module Files

| PR | Module |
| --- | --- |
| PR 1a | [pr_01a_minimal_trading_foundation.md](pr_01a_minimal_trading_foundation.md) |
| PR 1b | [pr_01b_portfolio_intents_relationship_graph.md](pr_01b_portfolio_intents_relationship_graph.md) |
| PR 2 | [pr_02_provider_resilience_signal_mvp.md](pr_02_provider_resilience_signal_mvp.md) |
| PR 3 | [pr_03_strategy_matching_replay.md](pr_03_strategy_matching_replay.md) |
| PR 4 | [pr_04_position_sizing_risk_manager.md](pr_04_position_sizing_risk_manager.md) |
| PR 5 | [pr_05_trading_decision_agent_guardrails.md](pr_05_trading_decision_agent_guardrails.md) |
| PR 6 | [pr_06_paper_stock_broker_portfolio_state.md](pr_06_paper_stock_broker_portfolio_state.md) |
| PR 7 | [pr_07_paper_options_assignment_risk.md](pr_07_paper_options_assignment_risk.md) |
| PR 8 | [pr_08_intraday_refresh_rebalance.md](pr_08_intraday_refresh_rebalance.md) |
| PR 9 | [pr_09_reflection_learning_factors.md](pr_09_reflection_learning_factors.md) |
| PR 10 | [pr_10_strategy_evolution.md](pr_10_strategy_evolution.md) |
| PR 11 | [pr_11_today_dashboard_ui.md](pr_11_today_dashboard_ui.md) |
| PR 12 | [pr_12_scheduler_smoke_deploy_docs.md](pr_12_scheduler_smoke_deploy_docs.md) |

---
