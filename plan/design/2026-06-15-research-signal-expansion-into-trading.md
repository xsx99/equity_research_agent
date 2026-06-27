# Research Signal Expansion Into Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the trading signal pipeline so deterministic research inputs such as insider activity and social/macro updates, including Trump-related updates, become replayable trading signal families without feeding research-agent LLM conclusions into trading.

**Architecture:** Keep the trading path deterministic and point-in-time. Add two new signal families, `insider` and `social_macro`, by normalizing upstream raw source rows into trading-side source contracts, then aggregate those rows into pre-open snapshots, intraday refresh, alerts, strategy matching, and downstream trading context. Reuse research-side raw data sources only as upstream inputs; do not read `ResearchOutput` or other LLM-generated conclusions.

**Tech Stack:** Python, pytest, SQLAlchemy, Alembic, existing trading signal pipeline, legacy insider-trade tables, global-context providers, FastAPI/CLI smoke tooling.

---

## Required Pre-Read

- `documents/general_instructions.md`
- `plan/research_app/trading_agent_refactor/module_contracts.md`
- `plan/research_app/trading_agent_refactor/design/03_strategy_architecture.md`
- `plan/research_app/trading_agent_refactor/design/04_signal_snapshots.md`
- `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- `src/research/workflows/batch_research.py`
- `src/research/repositories/research_repository.py`
- `src/trading/signals/source_ingestion.py`
- `src/trading/signals/snapshots.py`
- `src/trading/strategies/matching.py`
- `src/trading/runtime/intraday_refresh_runner.py`
- `src/trading/runtime/intraday_refresh_helpers.py`
- `docs/superpowers/plans/2026-06-15-today-dashboard-operator-ui.md`

## Scope And Non-Goals

- In scope: deterministic research inputs already represented or fetchable without LLM help, specifically legacy insider/Form 4 rows plus global-context buckets such as `trump_updates`, `official_updates`, and `geopolitical_news`.
- In scope: pre-open snapshots, intraday refresh, alerting, and strategy scoring for those inputs.
- In scope: producing structured backend fields so `/today` can selectively surface material insider and social/policy signals instead of dumping raw source rows.
- In scope: conservative point-in-time handling for legacy insider rows that do not currently have full timestamp fidelity.
- Out of scope: passing `research_outputs`, `thesis_summary`, `decision`, or other research-agent LLM fields into trading.
- Out of scope: full transcript interpretation, deep SEC filing interpretation beyond structured insider fields, free-form social-media NLP, or generic macro-only single-name bearish trading.
- Out of scope: replacing the separate risk/macro backend plan; this plan only adds a new signal family and its immediate trading consumption path.

## Current Gap This Plan Fixes

- The research pipeline already assembles `insider_activity` and `global_context.trump_updates`, but the trading `SignalPipeline` only emits `technical`, `fundamental`, and `events_news`.
- `StrategyMatcher` still treats insider/Form 4 requirements as unsupported through `full_sec_insider_interpretation`.
- Trading has no normalized source table for global-context social/policy items, so intraday policy/news shocks cannot become replayable trading signals.
- Trading should not depend on `research_runs.input_json` or `research_outputs` as its critical-path source of truth.

## Contract Decisions This Plan Locks In

- Add two supported snapshot families: `insider` and `social_macro`.
- `insider` is a structured subset, not “full SEC interpretation.” Supported fields include:
  - `purchase_count_30d`
  - `sale_count_30d`
  - `insider_net_buy_value_30d`
  - `insider_net_buy_value_90d`
  - `insider_cluster_buy_count_90d`
  - `officer_buy_flag`
  - `director_buy_flag`
  - `sale_concentration_score`
  - `recent_form4_filing_at`
- `social_macro` is a structured subset of global context, not free-form social reasoning. Supported fields include:
  - `trump_update_count_24h`
  - `official_update_count_24h`
  - `geopolitical_risk_count_24h`
  - `social_macro_sentiment_direction`
  - `policy_headwind_flag`
  - `policy_tailwind_flag`
  - `explicit_ticker_mention_flag`
  - `explicit_theme_mention_flag`
  - `social_macro_importance_score`
  - `latest_social_macro_category`
  - `latest_social_macro_published_at`
- Social/policy items only become ticker-level trading signals when one of these is true:
  - the item explicitly mentions the ticker or company name
  - the item maps to a configured theme/relationship and the ticker belongs to that theme
- Social/policy context can reduce size, block adds, or increase alert severity, but by itself cannot create a high-confidence single-name short.
- The backend output must support selective UI display:
  - `insider` should expose compact operator-facing summary fields such as `cluster_buy`, `net_buy_value`, `sale_concentration`, and `freshness`
  - `social_macro` should expose compact operator-facing summary fields such as `category`, `importance`, `headwind_or_tailwind`, `ticker_or_theme_mention`, and `freshness`
  - raw underlying source rows remain available for audit, but they are not the default UI payload
- Until precise filing timestamps exist for legacy insider rows, the trading PIT contract must use a conservative availability rule: `available_for_decision_at` is the later of the row ingest time and the next market open after `filing_date`.

## File Map

- Modify: `plan/research_app/trading_agent_refactor/module_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/03_strategy_architecture.md`
- Modify: `plan/research_app/trading_agent_refactor/design/04_signal_snapshots.md`
- Modify: `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/022_research_signal_expansion_tables.py`
- Create: `src/trading/signals/insider.py`
- Create: `src/trading/signals/social_macro.py`
- Modify: `src/trading/signals/__init__.py`
- Modify: `src/trading/signals/sources.py`
- Modify: `src/trading/signals/source_ingestion.py`
- Modify: `src/trading/signals/snapshots.py`
- Modify: `src/trading/workflows/signal_snapshot.py`
- Modify: `src/trading/repositories/source_sqlalchemy.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/strategies/catalog.py`
- Modify: `src/trading/strategies/matching.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Modify: `src/trading/intraday/news_alerts.py`
- Create: `scripts/run_trading_signal_family_smoke.py`
- Create: `tests/trading/test_insider_signals.py`
- Create: `tests/trading/test_social_macro_signals.py`
- Modify: `tests/trading/test_signal_sources.py`
- Modify: `tests/trading/test_signal_source_sqlalchemy.py`
- Modify: `tests/trading/test_pipeline.py`
- Modify: `tests/trading/test_strategy_matching.py`
- Modify: `tests/trading/test_strategy_catalog.py`
- Modify: `tests/trading/test_intraday_signals.py`
- Modify: `tests/trading/test_news_alerts.py`
- Modify: `tests/trading/test_runtime_intraday_live.py`
- Modify: `tests/db/test_trading_models.py`
- Create: `tests/scripts/test_run_trading_signal_family_smoke.py`
- Modify: `documents/repo_overview.md`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Task 1: Lock Contracts And Persistence Boundaries

**Files:**

- Modify: `plan/research_app/trading_agent_refactor/module_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/03_strategy_architecture.md`
- Modify: `plan/research_app/trading_agent_refactor/design/04_signal_snapshots.md`
- Modify: `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- Modify: `src/db/models/trading.py`
- Modify: `src/trading/signals/sources.py`
- Create: `alembic/versions/022_research_signal_expansion_tables.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_signal_source_sqlalchemy.py`

- [ ] Step 1: Write failing model/repository tests asserting that `signal_snapshots.signal_json` may carry `insider` and `social_macro`, that `SocialMacroItem` rows round-trip through the SQLAlchemy source repository, and that legacy `insider_trades` reconstruct into `SourceRecord(..., source_family="insider")`.
- [ ] Step 2: Update the design/module-contract docs so “insider unsupported” becomes “structured insider supported, deep SEC interpretation still deferred,” and so `social_macro` is documented as a deterministic source family rather than a research-agent side channel.
- [ ] Step 3: Add a `SocialMacroItem` ORM table and migration with PIT timestamps, category, sentiment/direction, importance, mention metadata, dedupe key, and provider/source refs.
- [ ] Step 4: Extend `src/trading/signals/sources.py` with `SocialMacroItemRecord`, `source_record_from_social_macro_item()`, and a conservative `source_record_from_insider_trade()` adapter.
- [ ] Step 5: Codify the insider availability rule in one place so replay never assumes same-day Form 4 availability without timestamp evidence.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_signal_source_sqlalchemy.py tests/db/test_trading_models.py -q`.

Expected result: persistence and PIT contracts can represent the two new families before any scoring logic changes.

## Task 2: Add Trading-Side Source Ingestion For Social Macro And Insider

**Files:**

- Modify: `src/trading/signals/source_ingestion.py`
- Modify: `src/trading/repositories/source_sqlalchemy.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/workflows/signal_snapshot.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/trading/test_signal_source_sqlalchemy.py`
- Test: `tests/trading/test_pipeline.py`

- [ ] Step 1: Write failing ingestion tests where pre-open refresh requests `social_macro`, persists `trump_update` and `geopolitical_news` rows, and exposes them through `latest_available_by_family(..., "social_macro", ...)`.
- [ ] Step 2: Extend `SourceIngestionService` to accept a trading-side global-context fetch path and include `social_macro` in `source_families`.
- [ ] Step 3: Normalize `trump_updates`, `official_updates`, and `geopolitical_news` into `SocialMacroItemRecord` rows with deterministic category, importance, dedupe, and publication/availability metadata.
- [ ] Step 4: Load insider rows directly from the legacy `insider_trades` table through `SQLAlchemySignalSourceRepository` instead of reading `research_runs.input_json` or `ResearchOutput`.
- [ ] Step 5: Update `SignalPipeline.build_pre_open_snapshots()` so the refresh list becomes `technical`, `fundamental`, `events_news`, `social_macro`, and `option_chain`, while insider rows come from Postgres-backed source reconstruction.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py tests/trading/test_signal_source_sqlalchemy.py tests/trading/test_pipeline.py -q`.

Expected result: the trading pipeline can fetch or reconstruct both new raw source families without depending on the research agent.

## Task 3: Build `insider` And `social_macro` Signal Families

**Files:**

- Create: `src/trading/signals/insider.py`
- Create: `src/trading/signals/social_macro.py`
- Modify: `src/trading/signals/__init__.py`
- Modify: `src/trading/signals/snapshots.py`
- Test: `tests/trading/test_insider_signals.py`
- Test: `tests/trading/test_social_macro_signals.py`
- Test: `tests/trading/test_pipeline.py`

- [ ] Step 1: Write failing unit tests for `build_insider_signals()` from clustered buys/sales and `build_social_macro_signals()` from Trump/official/geopolitical items with explicit ticker and theme mentions.
- [ ] Step 2: Implement supported insider aggregations for 30d/90d net value, cluster-buy count, officer/director flags, sale concentration, and recent filing freshness.
- [ ] Step 3: Implement supported social/macro aggregations for 24h counts, sentiment direction, policy headwind/tailwind flags, explicit mention flags, importance score, and latest-category metadata.
- [ ] Step 4: Update `build_signal_snapshot()` so `signal_json` emits `insider` and `social_macro`, `source_freshness_json` tracks both families, and generic insider placeholders are narrowed to only the still-deferred SEC features.
- [ ] Step 5: Keep the family boundary strict: `social_macro` items may annotate or constrain a ticker, but they must not overwrite `events_news.direct_negative_catalyst_type` unless the item is already a direct company event.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_insider_signals.py tests/trading/test_social_macro_signals.py tests/trading/test_pipeline.py -q`.

Expected result: pre-open signal snapshots now contain five supported families instead of three.

## Task 4: Consume New Families In Strategy Matching

**Files:**

- Modify: `src/trading/strategies/catalog.py`
- Modify: `src/trading/strategies/matching.py`
- Test: `tests/trading/test_strategy_catalog.py`
- Test: `tests/trading/test_strategy_matching.py`

- [ ] Step 1: Write failing tests for an `insider_accumulation_momentum_v1` candidate, for existing bullish strategies using insider confirmation as evidence, and for negative social/policy context downgrading a candidate without creating a macro-only short.
- [ ] Step 2: Seed at least one real consumer strategy for the new family, for example `insider_accumulation_momentum_v1`, with insider plus technical confirmation requirements.
- [ ] Step 3: Extend scoring helpers so insider confirmation and social/policy headwind or tailwind become bounded deterministic modifiers instead of hidden prompt-only context.
- [ ] Step 4: Update `DEFERRED_SIGNAL_FAMILY_MARKERS` so only truly unsupported SEC/transcript/read-through families remain blocked.
- [ ] Step 5: Preserve the bearish evidence contract: `social_macro` can reduce score, block adds, or force watch/risk-warning states, but cannot by itself create high-confidence single-name bearish trade candidates.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_catalog.py tests/trading/test_strategy_matching.py -q`.

Expected result: the new families materially affect candidate scoring instead of existing as unused snapshot payload.

## Task 5: Extend Intraday Refresh, Alerts, And Rebalance Context

**Files:**

- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Modify: `src/trading/intraday/news_alerts.py`
- Test: `tests/trading/test_intraday_signals.py`
- Test: `tests/trading/test_news_alerts.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] Step 1: Write failing tests for hourly refresh to pull fresh `social_macro` rows, carry forward baseline `insider` values, and surface deltas for policy/social shocks.
- [ ] Step 2: Add a targeted refresh hook so the intraday runtime can refresh `technical`, `events_news`, `social_macro`, and `option_chain` for the scoped ticker set before building snapshots.
- [ ] Step 3: Extend `_build_intraday_refresh_payload()` and intraday snapshot tests so `social_macro` can refresh intraday while `insider` is explicitly carried forward unless a newer filing source row exists.
- [ ] Step 4: Extend alert loading and `NewsAlertService` so high-importance `SocialMacroItem` rows can produce replayable policy/social alerts with dedupe keys and `source_family` provenance.
- [ ] Step 5: Feed social/policy deltas into rebalance metadata as risk context only; they may tighten risk or trigger review, but they must not enable unsupported `open_new` or macro-only bearish behavior.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_signals.py tests/trading/test_news_alerts.py tests/trading/test_runtime_intraday_live.py -q`.

Expected result: intraday refresh can react to Trump/policy/geopolitical updates while keeping insider data low-frequency and PIT-safe.

## Task 6: Add End-To-End Smoke Coverage And Documentation

**Files:**

- Create: `scripts/run_trading_signal_family_smoke.py`
- Create: `tests/scripts/test_run_trading_signal_family_smoke.py`
- Modify: `documents/repo_overview.md`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] Step 1: Write a fixture-backed standalone smoke script that seeds one insider row plus one `social_macro` row and prints the resulting snapshot families and candidate evidence for a tiny ticker set.
- [ ] Step 2: Add a tiny opt-in live mode that calls the global-context fetch path once and confirms `social_macro` persistence without creating any orders.
- [ ] Step 3: Update `documents/repo_overview.md` with the new five-family signal surface and the rule that trading consumes raw deterministic research inputs, not research-agent conclusions.
- [ ] Step 4: Update the runbook with the conservative insider PIT policy, the new social-macro refresh path, and the standalone smoke-test commands.
- [ ] Step 5: Update `plan/research_app/trading_agent_refactor/progress_tracker.md` after each completed task with verification evidence and the final verification command set.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_insider_signals.py tests/trading/test_social_macro_signals.py tests/trading/test_signal_sources.py tests/trading/test_signal_source_sqlalchemy.py tests/trading/test_pipeline.py tests/trading/test_strategy_catalog.py tests/trading/test_strategy_matching.py tests/trading/test_intraday_signals.py tests/trading/test_news_alerts.py tests/trading/test_runtime_intraday_live.py tests/db/test_trading_models.py tests/scripts/test_run_trading_signal_family_smoke.py -q`.
- [ ] Step 7: Run `source ~/.venv/bin/activate && python scripts/run_trading_signal_family_smoke.py --ticker NVDA --fixture --json`.

Expected result: the feature has deterministic regression coverage, a standalone smoke path, and updated architecture/runbook documentation.

## Acceptance Criteria

- `SignalSnapshotResult.signal_json` includes `insider` and `social_macro` for supported tickers.
- Trading no longer relies on `ResearchOutput` or `research_runs.input_json` for critical-path signal consumption.
- `StrategyMatcher` no longer blanket-blocks insider strategies through `full_sec_insider_interpretation` when the required signals are now deterministically supported.
- Intraday refresh can generate replayable policy/social alerts from `social_macro`.
- Macro-only or social-only context still cannot create unsupported single-name bearish trades.
- The backend artifacts include enough structured fields for `/today` to selectively surface material insider and social/policy signals while keeping raw rows behind audit details.
- A standalone smoke script can demonstrate one ticker carrying the two new families end-to-end.
