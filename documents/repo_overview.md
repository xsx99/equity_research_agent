# Repository Overview

This repository contains the research app and the staged V2 trading-agent refactor.

## Current Architecture

- `src/agents/` contains bounded agent code. Existing research behavior still uses `src/prompts/registry.py`; PR 1a adds `src/agents/prompt_registry.py` for trading-agent prompt metadata, template hashes, and rendered prompt hashes.
- `src/db/models/` contains SQLAlchemy ORM models using the shared `Base` and `ChoiceEnum` helpers. PR 1a adds trading foundation models for strategy definitions, LLM prompt templates, prompt runs, and usage telemetry. PR 1b adds portfolio-intent and relationship graph models. PR 2 adds universe, manual request, provider telemetry, source ingestion, fundamental/event source, and signal snapshot models. PR 3 adds strategy runs, candidate scores, trade classifications, historical replay runs, and candidate outcome evaluations.
- `src/trading/` contains data-only trading foundation helpers. PR 1a seeds the initial strategy catalog and portfolio-pool trade identity taxonomy without changing runtime trading behavior. PR 1b adds pure portfolio-intent and relationship helpers for later classifier/signal consumers. PR 2 adds deterministic universe filtering, manual request state, provider resilience guardrails, provider-backed source ingestion adapters, point-in-time source filtering, technical/fundamental/events-news signal builders, and a pre-open signal pipeline. PR 3 adds deterministic strategy matching, primary strategy selection, trade classification, confidence calibration, historical replay, and outcome evaluation helpers.
- `alembic/versions/` contains database migrations. PR 1a adds revision `005` for `strategy_definitions`, `llm_prompt_templates`, `llm_prompt_runs`, and `llm_usage_events`. PR 1b adds revision `006` for `portfolio_intents`, `ticker_relationships`, `peer_baskets`, and `theme_taxonomy`. PR 2 adds revision `007` for universe/signal MVP operational state. PR 3 adds revision `008` for strategy matching and replay outcome tables.
- `plan/research_app/trading_agent_refactor/` is the canonical modular plan for the V2 trading-agent work. Implementation proceeds one PR slice at a time and stops for review before the next slice.

## PR 1a Scope

PR 1a is a minimal durable foundation only:

- versioned strategy definition seed data
- trade identity taxonomy policies
- prompt registry metadata and deterministic rendering
- ORM models and Alembic schema for strategy/prompt telemetry

It intentionally does not add universe scanning, signal snapshots, strategy scoring runs, portfolio intents, relationship graph tables, scheduler jobs, paper trading, options execution, or UI changes.

## PR 1b Scope

PR 1b adds the durable schema and pure helper layer for portfolio intents and structured relationship data:

- active portfolio-intent approval helpers for `core_holding` eligibility
- max-weight and allowed tactical interaction lookups for approved core holdings
- explicit relationship allowed-use checks
- deterministic peer-basket member construction from source-backed relationships
- ORM models and Alembic schema for `portfolio_intents`, `ticker_relationships`, `peer_baskets`, and `theme_taxonomy`

It intentionally does not add universe scanning, signal snapshots, strategy scoring, relationship inference, trading decisions, paper orders, or UI changes.

## PR 2 Scope

PR 2 adds the deterministic universe-to-signal MVP path:

- configurable universe filters with liquidity, sector/industry, exchange/asset-type, and manual exclusion reasons
- `TRADING_UNIVERSE_SYMBOLS` local fallback for fixture/dev universe rows
- provider resilience guardrails for request budgets, cache freshness, retries/backoff, circuit state, degraded-mode telemetry, and request-run recording
- active manual ticker request helpers for `review_only` and `paper_trade_eligible` modes
- provider-backed source ingestion adapters that call existing market/news providers behind `ProviderResiliencePolicy` and record source/provider run metadata through repository abstractions
- point-in-time source row filtering with source refs, available times, max input availability, and future-row exclusion counts
- technical, fundamental, and events/news signal family builders with explicit missing placeholders for deferred source families
- pre-open signal pipeline that merges scanner symbols and active manual requests without adding trading approval
- ORM models and Alembic schema for universe snapshots/symbols, manual requests, provider/source telemetry, fundamental/event source rows, and `signal_snapshots`

It intentionally does not add strategy scoring, trading decisions, risk checks, paper orders, intraday refresh, full SEC/insider/transcript parsing, option-chain signals, live provider smoke tests, or UI changes.

## PR 3 Scope

PR 3 adds the deterministic strategy-matching and replay layer before any trading agent or paper order behavior:

- strategy candidate scoring from PR 2 point-in-time technical, fundamental, and events/news signal snapshots
- explicit unsupported/deferred source-family handling for transcript, SEC/insider, macro/read-through, and option-chain-dependent strategies
- primary strategy and expression-bucket selection that freezes attribution context before later trading decisions
- trade classification into `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, or `watch_only`, with `catalyst_watch` and `ordinary_watch` as watch types
- confidence-calibration bucket inputs from historical candidate outcome rows
- historical replay runner that reconstructs candidates only from decision-available snapshots, then evaluates future outcomes over a configured horizon
- ORM models and Alembic schema for strategy runs, candidate scores, trade classifications, replay runs, and outcome evaluations

It intentionally does not call `TradingPipeline`, generate paper orders, implement option-chain strategy replay, or backfill unavailable deferred source families.
