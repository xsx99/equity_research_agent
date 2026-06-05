# Repository Overview

This repository contains the research app and the staged V2 trading-agent refactor.

## Current Architecture

- `src/agents/` contains bounded agent code. Existing research behavior still uses `src/prompts/registry.py`; PR 1a adds `src/agents/prompt_registry.py` for trading-agent prompt metadata, template hashes, and rendered prompt hashes. PR 5 adds `src/agents/trading.py` and `src/agents/trading_schemas.py` for bounded trading decisions with one repair retry, Pydantic validation, safe fallback, and prompt/usage telemetry handoff into the trading workflow. PR 9 adds `src/agents/reflection.py` and `src/agents/reflection_schemas.py` for post-close reflection with the same retry/fallback telemetry pattern plus structured learning-factor proposals.
- `src/db/models/` contains SQLAlchemy ORM models using the shared `Base` and `ChoiceEnum` helpers. PR 1a adds trading foundation models for strategy definitions, LLM prompt templates, prompt runs, and usage telemetry. PR 1b adds portfolio-intent and relationship graph models. PR 2 adds universe, manual request, provider telemetry, source ingestion, fundamental/event source, and signal snapshot models. PR 3 adds strategy runs, candidate scores, trade classifications, historical replay runs, and candidate outcome evaluations.
- `src/providers/` contains real external data provider implementations and provider-level helper functions for market data, news, and global macro/news context. Agent-callable wrappers live separately under `src/tools/`.
- `src/tools/` contains the tool registry, tool context/base classes, agent-callable wrappers, and DB-backed insider query tools. It should not contain provider implementation modules.
- `src/research/workflows/` contains legacy research-app orchestration, including batch research and evaluation workflows. `src/research/repositories/` contains research DB helper functions. Old root-level research compatibility modules were removed because this layout has not been released yet.
- `src/trading/` contains the trading domain packages and runtime entrypoints. PR 1a seeds the initial strategy catalog and portfolio-pool trade identity taxonomy without changing runtime trading behavior. PR 1b adds pure portfolio-intent and relationship helpers for later classifier/signal consumers. PR 2 adds deterministic universe filtering, manual request state, provider resilience guardrails, provider-backed source ingestion adapters, point-in-time source filtering, technical/fundamental/events-news signal builders, and a pre-open signal pipeline. PR 3 adds deterministic strategy matching, primary strategy selection, trade classification, confidence calibration, historical replay, and outcome evaluation helpers. Workflow entrypoints live under `src/trading/workflows/`; signal source contracts, PIT helpers, builders, snapshots, and ingestion live under `src/trading/signals/`; strategy catalog, matching, selection, classification, taxonomy, and calibration live under `src/trading/strategies/`; universe/provider guardrails live under `src/trading/data_sources/`; manual ticker request contracts live under `src/trading/manual_review/`; broker adapters live under `src/trading/brokers/`; portfolio-intent helpers and portfolio state mappers live under `src/trading/portfolio/`; option instrument-planning helpers live under `src/trading/options/`; option assignment-risk and risk-hedge helpers live under `src/trading/risk/`; relationship graph helpers live under `src/trading/relationships/`; intraday signal, alert, and rebalance helpers live under `src/trading/intraday/`; historical replay and outcome evaluation live under `src/trading/replay/`; canonical post-close reflection and strategy-evolution logic now lives under `src/trading/post_close/`, while `src/trading/reflection_pipeline.py` and `src/trading/strategy_evolution.py` remain as compatibility shims; canonical scheduler/runtime orchestration now lives under `src/trading/runtime/`, with `src/trading/runtime/__init__.py` exposing the stable `TRADING_JOB_PHASES`, `AVAILABLE_SMOKE_MODES`, `run_job_phase(...)`, and `run_smoke_mode(...)` facade, while old root modules such as `src/trading/runtime_live.py`, `src/trading/runtime_dispatch.py`, and `src/trading/runtime_smoke.py` remain as compatibility shims. Trading artifact repositories now include both the in-memory store in `src/trading/repositories/in_memory.py` and a SQLAlchemy-backed persistence adapter in `src/trading/repositories/sqlalchemy.py`. PR 5 adds `src/trading/workflows/trading_decision.py`, which consumes selected candidates plus PR 4 risk decisions, invokes the bounded trading agent, enforces V2 guardrails such as long-only common stock and `review_only` manual request downgrades, persists prompt telemetry into the in-memory repository, and records `TradingDecisionRecord` artifacts without creating any paper orders. PR 6 uses Alpaca paper trading as the execution source of truth via `src/trading/brokers/paper_stock.py`, maps broker `/v2/account` and `/v2/positions` payloads into local portfolio audit records in `src/trading/portfolio/state.py`, centralizes broker account/position sync plus PR 4 `PortfolioContext` construction in `src/trading/workflows/portfolio_sync.py`, persists broker-backed orders/executions/positions/snapshots through `src/trading/workflows/paper_execution.py`, and includes `scripts/run_trading_paper_order_smoke.py` plus `scripts/run_trading_paper_execution.py` for standalone smoke verification and direct workflow-driven manual execution. PR 7 adds a paper-only option strategy layer, assignment-risk evaluation, simulated option order/position artifacts, and option overlays that share the same unified paper margin-account context as broker-synced stock positions. PR 8 adds intraday-specific contracts under `src/trading/intraday/` for hourly scoped signal refreshes, normalized deduped alerts, bounded intraday rebalance decisions with retry/fallback, and optional execution reuse for existing-position exits/reductions.
- PR 4 extends `src/trading/` with a deterministic risk layer under `src/trading/risk/`. This package introduces fixture-friendly `PortfolioContext` / `TradeRiskRequest` contracts, generated risk-appetite configs, deterministic position sizing, factor exposure aggregation, and final risk approve/reduce/reject decisions without coupling to paper broker or portfolio DB wiring. PR 4 also extends the in-memory trading repository with persisted sizing decisions, portfolio risk snapshots, factor exposures, and risk decisions for later PR consumers.
- PR 5 extends the in-memory trading repository with prompt templates, prompt runs, usage events, and trading decisions so unit tests can verify guardrail behavior before DB-backed repositories arrive.
- `alembic/versions/` contains database migrations. PR 1a adds revision `005` for `strategy_definitions`, `llm_prompt_templates`, `llm_prompt_runs`, and `llm_usage_events`. PR 1b adds revision `006` for `portfolio_intents`, `ticker_relationships`, `peer_baskets`, and `theme_taxonomy`. PR 2 adds revision `007` for universe/signal MVP operational state. PR 3 adds revision `008` for strategy matching and replay outcome tables.
- PR 4 adds revision `009` for `position_sizing_decisions`, `portfolio_risk_snapshots`, `risk_factor_exposures`, and `risk_decisions`, and broadens trade-identity DB constraints to include `risk_hedge_overlay`.
- PR 5 adds revision `010` for `trading_decisions`, linking candidate/classification/risk artifacts to prompt-run telemetry and persisted guardrailed decisions.
- PR 6 adds revision `011` for `paper_orders`, `paper_executions`, `paper_positions`, and `portfolio_snapshots`.
- PR 7 adds revision `012` for `option_strategy_decisions`, `paper_option_orders`, `paper_option_executions`, `paper_option_positions`, and `option_risk_snapshots`.
- PR 8 adds revision `013` for `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts`, and `intraday_rebalance_decisions`.
- PR 9 adds revision `014` for `daily_reflections`, `learning_factors`, and `learning_factor_applications`.
- PR 10 adds revision `015` for `strategy_proposals` and `strategy_evaluation_results`.
- `plan/research_app/trading_agent_refactor/` is the canonical modular plan for the V2 trading-agent work. Implementation proceeds one PR slice at a time and stops for review before the next slice.
- `plan/research_app/navigation_refactor/` tracks the one-PR behavior-preserving source-tree navigation refactor.

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

## PR 4 Scope

PR 4 adds deterministic sizing and final risk approval before any paper broker wiring:

- operator-facing `conservative` / `balanced` / `aggressive` risk appetite presets resolved into generated effective risk configs
- explicit `PortfolioContext` and `TradeRiskRequest` dataclasses so unit tests and later PR wiring can inject portfolio state without reading paper-position tables directly
- deterministic position sizing with strategy-budget, macro-budget, volatility, liquidity, and single-name caps
- portfolio factor exposure aggregation across sector, strategy, horizon, direction, beta bucket, volatility bucket, liquidity bucket, event type, and macro sensitivity
- final `RiskManager` gates for missing/stale signals, unestimable margin, core-holding approval, macro-only bearish single-name shorts, and concentration-cap reduce/reject decisions
- ORM models and Alembic schema for `position_sizing_decisions`, `portfolio_risk_snapshots`, `risk_factor_exposures`, and `risk_decisions`

It intentionally does not call an LLM, create broker orders, or read live paper portfolio tables directly. PR 6 remains responsible for wiring real paper positions and margin-account snapshots into `PortfolioContext`.

## PR 5 Scope

PR 5 adds the bounded trading-decision layer after deterministic risk approval and before any broker wiring:

- trading-agent prompt template under `src/agents/prompts/trading/`
- Pydantic trading input/output/fallback schemas
- one-retry trading agent with validation-error repair prompt and safe fallback
- `TradingDecisionPipeline` that merges candidate/classification/risk artifacts into one auditable decision context
- guardrails for long-only common stock, `watch_only` classifications, `review_only` manual requests, and risk-rejected trades
- ORM model and Alembic schema for `trading_decisions`

It intentionally does not create staged paper orders, mutate portfolio state, or wire DB-backed prompt/decision repositories yet. PR 6 remains responsible for turning approved decisions into paper stock order state.

## PR 6 Scope

PR 6 adds the first paper-broker and portfolio-state layer after bounded trading decisions:

- Alpaca paper trading is the execution source of truth for stock orders, buying power, cash, equity, and open positions
- `PaperStockBroker` still enforces V2 long-only stock rules and repeated `review_only` manual-request gating before the broker call, then submits `market` / `day` orders to Alpaca with deterministic `client_order_id`
- broker `/v2/account` and `/v2/positions` payloads are mapped into local `PortfolioSnapshot`, `StockPosition`, and PR 4 `PortfolioContext` views for audit and downstream risk consumers
- `PaperExecutionWorkflow` persists broker-backed paper orders, executions, positions, and portfolio snapshots through the in-memory repository
- the same PR 6 paper-execution and broker-sync workflows can also persist through `SQLAlchemyTradingRepository`, so live broker-backed portfolio mirrors are no longer limited to test-only in-memory storage
- `PortfolioLedger` remains available only as an offline helper for replay/local simulation paths; it is no longer the primary PR 6 execution path
- ORM models and Alembic schema for `paper_orders`, `paper_executions`, `paper_positions`, and `portfolio_snapshots` now include broker order identifiers and client order identifiers for reconciliation
- `scripts/run_trading_paper_order_smoke.py` submits a tiny real Alpaca paper order for smoke verification
- `scripts/run_trading_paper_execution.py` constructs a minimal PR 6 `TradingDecisionRecord`/`RiskDecisionRecord` pair and runs the real `PaperExecutionWorkflow` against Alpaca, including `exit` sells for manual cleanup

It intentionally does not add option execution, assignment-risk handling, or intraday rebalance behavior. Those remain in later PR slices.

## PR 7 Scope

PR 7 adds the initial paper-only options and assignment-risk layer:

- whitelisted option strategy construction for `long_call`, `long_put`, `put_credit_spread`, `call_credit_spread`, `long_straddle`, and `long_strangle`
- per-leg option persistence plus strategy-level option risk and assignment-notional calculation
- local paper option order/execution/position persistence for tactical option trades and paper risk-hedge overlays
- unified portfolio-context overlays so stock broker state and open option exposure share one margin-account view
- ORM models and Alembic schema for option decisions, option orders/executions/positions, and option risk snapshots

It intentionally does not add a real broker-backed option execution path or intraday option rebalance behavior.

## PR 8 Scope

PR 8 adds the first intraday refresh and rebalance path on top of the morning baseline:

- `build_intraday_signal_snapshot()` records refreshed high-frequency families, carried-forward baseline families, and deltas versus both the morning baseline and the prior intraday snapshot
- `NewsAlertService` turns normalized event/news rows into deduped actionable alerts with severity, sentiment, strategy relevance, and affected position/candidate/theme context
- `IntradayRebalancePipeline` loads an intraday rebalance prompt, validates/retries/falls back via Pydantic, blocks unauthorized `open_new` actions, records prompt telemetry, persists rebalance decisions, and can reuse the PR 6 paper-execution workflow for existing-position `exit` / `reduce` actions
- repositories, ORM models, and Alembic revision `013` now persist intraday scans, snapshots, alerts, and rebalance decisions

The current PR 8 implementation intentionally keeps intraday rebalance separate from the morning trading-decision pipeline. It reuses prompt telemetry and paper-execution building blocks, but it does not collapse morning and intraday flows into one shared top-level workflow.

## PR 11 Scope

PR 11 adds the first operator-facing V2 trading workstation in the existing FastAPI app:

- `/today` is now the default landing page and renders a tabbed workstation around persisted V2 trading artifacts instead of the legacy research list
- the page aggregates current portfolio snapshots, risk snapshots, trading decisions, positions, option positions, hedge overlays, candidate rows, manual review requests, learning factors, strategy proposals, and LLM usage into structured tables/cards
- trade rows support a detail drill-down that surfaces linked signal snapshot, prompt output, strategy-score context, risk decision, and replay outcome summaries when available
- the `Candidates` tab includes the initial operator mutations allowed by the PR: create/dismiss pinned manual ticker reviews and update the active universe filter profile
- `/research` remains intact as the legacy audit UI, but top-level navigation now prioritizes the `Today` workstation

This PR intentionally stops at the UI/read-model layer. It does not add new pipeline producers, calendar-event persistence, or a dedicated UI-specific repository abstraction yet.

## PR 11A Scope

PR 11A refines the initial `/today` workstation into a ticker-first operator view without changing the persistence model:

- `src/web/presenters/today_workspace.py` now owns ticker-centric read-model shaping for the workstation, including attention-bucket assignment, current-state ticker selection, summary-first detail payloads, explicit empty states, and deterministic datetime-aware ordering across rail/detail/history sections
- `src/web/routers/today.py` now builds per-ticker collections from persisted trading, signal, risk, news, and portfolio artifacts and exposes a `ticker_workspace` payload alongside temporary compatibility trade-detail data
- `src/templates/today.html` now renders the `Trades` section as a ticker-first workstation with `Action Now`, `In Position`, and `Watch` rail buckets plus `Latest Conclusion`, `Timeline`, `Trend`, `Decisions`, and `Risk` detail sections
- route and presenter coverage now live in `tests/web/test_today.py` and `tests/web/test_today_workspace.py`, with focused assertions around ticker selection, fallback behavior, empty states, and ordering consistency

This refinement intentionally keeps FastAPI + Jinja server rendering and does not yet introduce a dedicated front-end state layer.

## PR 11B Scope

PR 11B refreshes the `/today` workstation into a navigation-driven command-center shell without changing the underlying trading artifacts:

- the page header is now grouped into an operator strip with action-driving metrics separated from quieter session context
- top-level workstation tabs now render one focused surface at a time instead of stacking every major section into one viewport
- the `Trades` tab remains ticker-first, but now reads as a single selected-ticker canvas with hero/support hierarchy, lighter local detail navigation, and timeline list-to-detail drill-down
- `Overview`, `Portfolio`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, and `Ops & Cost` now render as focused standalone surfaces with summary-first blocks and denser tables pushed lower
- `/today` empty states and responsive behavior now use a more consistent low-noise presentation while staying fully server-rendered through FastAPI + Jinja

This refinement intentionally stays presentation-only. It does not add new persistence, new producer pipelines, or a client-side state layer.

## PR 13 Scope

PR 13 starts the live preopen cutover on top of the existing fixture-first scheduler/runtime layer:

- `src/trading/runtime_live.py` now defines a dedicated live morning runtime boundary with explicit dependencies for active universe-filter loading, active manual-request loading, universe scan, signal snapshots, strategy scoring, portfolio sync, risk approval, trading decisions, and optional paper execution
- `run_live_preopen_once()` can now build its default live dependency graph from a real DB session instead of requiring test-only injection, and `src/trading/runtime.py` delegates the scheduler-facing `preopen` phase to that live entrypoint
- SQL-backed adapters were added for active manual-request loading/evaluation updates and normalized source persistence / point-in-time source reconstruction: `src/trading/manual_review/sqlalchemy.py` and `src/trading/repositories/source_sqlalchemy.py`
- `src/trading/repositories/sqlalchemy.py` now includes the live-runtime persistence helpers needed by the morning chain: active universe-filter loading, universe snapshots/symbols, persisted signal and strategy artifacts, plus PR 4 risk snapshots / factor exposures / sizing decisions / risk decisions
- the live runtime now bootstraps the initial 24-row strategy seed catalog into Postgres when `strategy_definitions` is empty, so a fresh production database can still produce persisted `candidate_scores` / `trade_classifications` on the first real preopen run
- `scripts/run_trading_once.py` now exposes an explicit `--mode live-preopen` path and keeps paper execution opt-in through `--execute-paper-orders`, so manual morning runs default to dry-run decision/risk persistence unless an operator explicitly enables order submission
- `src/trading/data_sources/live_universe.py` adds a live universe-provider adapter that can either normalize provider asset rows or enrich explicit target tickers from real bars/context data; `runtime_live` now prefers the scoped `manual_include + active manual request` path so live preopen does not scan and persist thousands of unusable zero-liquidity asset rows before the morning decision flow starts
- `src/trading/workflows/signal_snapshot.py` and `src/trading/workflows/strategy_scoring.py` were tightened to remove hidden in-memory assumptions: live DB-backed manual-request evaluation now persists signal snapshots before FK updates, and strategy manual-review result updates now use the current candidate batch instead of reading repository-only in-memory state
- `src/agents/trading.py` now has a production default runner using the same phi/OpenAI-or-Gemini backend pattern as the research agent, and `runtime_live` now normalizes risk-decision persistence so every `risk_decision` row points at the already-saved portfolio risk snapshot from the current run instead of a transient in-memory ID
- the live trading prompt path is now more tolerant of real model output drift: `src/agents/trading.py` normalizes common schema-shape mismatches before validation, and `src/agents/prompts/trading/trading_decision_v1.yaml` now spells out the required scalar fields and conservative defaults explicitly so live preopen decisions do not fall back unnecessarily
- live multi-ticker source ingestion no longer crashes on shared provider headlines: `src/trading/signals/source_ingestion.py` now namespaces persisted `event_news_items.dedupe_key` values by ticker so the same article can be stored once per relevant symbol without violating the global unique constraint
- `scripts/run_trading_live_preopen_order_smoke.py` now provides a standalone execution smoke for the live morning runtime. It keeps the real Postgres/provider/broker wiring intact, but applies smoke-only deterministic overrides to the target ticker’s classification/decision path so operators can prove that the scheduler-facing preopen runtime can submit a real Alpaca paper order end-to-end

This implementation is intentionally still scoped to the morning live path. It does not replace the existing fixture smoke modes, and it does not yet redesign intraday, reflection, or strategy-evolution runtime assembly.

## PR 14 Slice 1 Scope

PR 14 slice 1 lands the runtime-structure split without yet migrating new live phases:

- `src/trading/runtime.py` is now a thin facade that only exposes the stable `TRADING_JOB_PHASES`, `AVAILABLE_SMOKE_MODES`, `run_job_phase(...)`, and `run_smoke_mode(...)` surface
- `src/trading/runtime_dispatch.py` centralizes phase and smoke handler lookup so scheduler/CLI entrypoints can stay stable while implementation modules move underneath
- `src/trading/runtime_smoke.py` now owns the fixture-first smoke implementations, including the optional Postgres universe/signal write check
- `src/trading/runtime_support.py` now holds shared live-runtime helpers for normalized phase/execution reports, strategy seed bootstrap, and default live news-provider selection
- `src/trading/runtime_live.py` keeps the live preopen behavior intact, but now builds its public reports and shared bootstrap pieces through the new support module
- `scripts/run_trading_smoke_test.py` now reads smoke-mode choices from the dedicated smoke module instead of the mixed runtime facade

This slice intentionally does not yet add dedicated live runtimes for manual review, intraday refresh, reflection, or strategy evolution. Those remain follow-up PR 14 tasks.

## PR 14 Slice 2 Scope

PR 14 slice 2 migrates the scheduler-facing `manual_review` phase onto an explicit live runtime without changing the operator-facing phase name:

- `src/trading/runtime_manual_review_live.py` now owns a dedicated live manual-review runtime and entrypoint, `run_live_manual_review_once(...)`
- the manual-review live runtime reuses the preopen dependency graph, but narrows the universe scope to active manual requests only instead of combining them with scanner-side `manual_include` symbols
- `src/trading/runtime_dispatch.py` now routes `run_job_phase("manual_review")` to the live manual-review runtime instead of the fixture smoke handler
- the runtime report now exposes manual-review-specific summary counts such as active request count and `review_only` vs `paper_trade_eligible` mode counts while keeping the common `status` / `phase` / `as_of` / `summary` / `execution` contract intact
- fixture-only `manual_review_fixture` behavior remains available under `src/trading/runtime_smoke.py` for standalone smoke checks

This slice intentionally stops short of adding dedicated live runtimes for intraday refresh, reflection, or strategy evolution.

## PR 14 Slice 3 Scope

PR 14 slice 3 migrates the scheduler-facing `intraday_refresh` phase onto an explicit live runtime while keeping the phase name and CLI surface stable:

- `src/trading/runtime_intraday_live.py` now owns a dedicated live intraday runtime and entrypoint, `run_live_intraday_refresh_once(...)`
- the live intraday runtime builds a scoped ticker set, loads same-day preopen baselines plus prior intraday snapshots, persists `intraday_signal_scans` / `intraday_signal_snapshots` / `news_alerts`, and then runs `IntradayRebalancePipeline`
- `src/trading/runtime_dispatch.py` now routes `run_job_phase("intraday_refresh")` to the live intraday runtime instead of the fixture smoke handler
- `src/trading/repositories/sqlalchemy.py` now includes intraday-specific read helpers for same-day scope construction, baseline snapshot lookup, prior intraday snapshot lookup, existing alert dedupe keys, and per-ticker request context assembly
- fixture-only `intraday_refresh_fixture` behavior remains available under `src/trading/runtime_smoke.py` for standalone smoke checks

This slice intentionally keeps dry-run intraday execution as the default runtime behavior and does not yet add the post-close live reflection or strategy-evolution runtimes.

## PR 14 Slice 4 Scope

PR 14 slice 4 migrates the scheduler-facing `reflection` phase onto an explicit live runtime and introduces real `skipped` semantics for missing same-day post-close prerequisites:

- `src/trading/runtime_reflection_live.py` now owns a dedicated live reflection runtime and entrypoint, `run_live_reflection_once(...)`
- the new `LiveReflectionRequestLoader` assembles a `ReflectionPipelineRequest` from persisted same-day artifacts through one repository-backed aggregation point instead of relying on fixture payloads
- when required post-close inputs such as `portfolio_outcome` or `portfolio_snapshots` are missing, the runtime returns `status="skipped"` with explicit reasons instead of fabricating a successful fixture run
- `src/trading/runtime_dispatch.py` now routes `run_job_phase("reflection")` to the live reflection runtime instead of the fixture smoke handler
- `src/trading/repositories/sqlalchemy.py` now includes reflection-oriented aggregation and persistence helpers, including `load_reflection_inputs(...)`, `save_daily_reflection(...)`, and `save_learning_factor(...)`
- fixture-only `reflection_fixture` behavior remains available under `src/trading/runtime_smoke.py` for standalone smoke checks

## PR 14 Slice 5 Scope

PR 14 slice 5 migrates the scheduler-facing `strategy_evolution` phase onto an explicit live runtime and carries the same post-close `skipped` semantics into strategy proposal generation:

- `src/trading/runtime_strategy_evolution_live.py` now owns a dedicated live strategy-evolution runtime and entrypoint, `run_live_strategy_evolution_once(...)`
- the new `LiveStrategyEvolutionRequestLoader` assembles a `StrategyEvolutionRequest` from persisted same-day `daily_reflections`, `learning_factors`, rejected candidates, and candidate outcome evaluations through one repository-backed aggregation point
- when the same-day reflection artifact is absent, the runtime returns `status="skipped"` with explicit reasons instead of falling back to fixture success semantics
- `src/trading/runtime_dispatch.py` now routes `run_job_phase("strategy_evolution")` to the live strategy-evolution runtime instead of the fixture smoke handler
- `src/trading/repositories/sqlalchemy.py` now includes strategy-evolution aggregation helpers alongside the existing reflection persistence helpers
- fixture-only `strategy_evolution_fixture` behavior remains available under `src/trading/runtime_smoke.py` for standalone smoke checks

PR 14 slice 6 then normalizes the operator-facing semantics around these live results:

- `scripts/run_trading_once.py` still accepts the same `--phase` values, but now treats `status="skipped"` as a non-failed operational result and exits non-zero only when a runtime reports `status="failed"`
- trading scheduler jobs still call `run_job_phase(...)` with the same phase strings, but now emit explicit `*_job_skipped` warnings with propagated reason lists instead of logging skipped post-close runs as normal completions
