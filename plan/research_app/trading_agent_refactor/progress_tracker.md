# Trading Agent Refactor Progress Tracker

## 2026-05-29

- Created the V2 staged implementation plan, now modularized under `plan/research_app/trading_agent_refactor/implementation/`.
- Execution policy: implement one PR slice at a time, stop after verification, wait for user review/merge before continuing.
- Updated the design and implementation plan to include strategy evolution: the system can summarize repeated learning into new strategy proposals, add them to the strategy catalog as candidate/shadow strategies, and promote them through gated lifecycle states.
- Updated the design and implementation plan to include hourly intraday signal refresh, news scans, and risk-gated immediate rebalance actions for material signal changes or critical/high positive or negative news.
- Updated the design and implementation plan with 500+ eval learnings: V2 is explicitly a relative-strength catalyst bot, bullish catalyst signals are higher-trust than bearish macro narratives, macro risk is a sizing/risk-budget input rather than a single-name short trigger, and confidence must be calibrated by historical pattern quality.
- Added trade identity requirements for portfolio pools: core holdings, tactical stock trades, tactical option trades, RiskManager hedge overlays, and watch-only candidates.
- Added paper/simulation-only options strategy layer requirements for leg-based option strategies.
- Added option-risk requirements: every option strategy needs leg-level metadata, strategy-level max-loss/margin-requirement/buying-power/Greeks risk, and worst-case assigned-portfolio checks when assignment can occur.
- Added Manual Ticker Review / Pinned Review design: users can force evaluation of non-scanner tickers in `review_only` or `paper_trade_eligible` mode, while keeping the same signal, strategy, confidence, and risk gates.
- Clarified that `SignalPipeline` builds full per-ticker snapshots from market bars plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, and existing research context sources, not only price/technical signals.
- Clarified strategy flow: score all eligible strategies first, then use `PrimaryStrategySelector` plus `TradeClassifier` to choose the selected strategy, expression bucket, and portfolio-pool trade identity before `TradingPipeline` proposes a trade.
- Clarified intraday loop: hourly refresh should scan material signal changes across price/volume, relative strength, options, news/events, and freshness checks for low-frequency sources, not news alone.
- Updated UI design to a tabbed trading workstation: Overview, Portfolio, Trades, Risk & Macro, Candidates, Learning & Strategies, and Ops & Cost, with full trade drill-down audit trails.
- Added prompt versioning and persistence requirement: every LLM pipeline must load version-controlled prompts through a prompt registry and persist prompt/template version, rendered prompt hash, input context, raw/parsed output, schema version, usage, cost, latency, and errors.
- Clarified attribution policy: benchmark and peer-basket alpha must use the selected strategy's configured holding horizon, with interim marks for open trades, rather than assuming every strategy is a one-day trade.
- Clarified that bearish evidence handling and trade identity are learned constraints embedded across the normal strategy, trading, sizing, risk, reflection, and UI flow; they are not standalone trading functions.
- Refined trade identity taxonomy into portfolio-pool identities: `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, `risk_hedge_overlay`, and `watch_only`; strategy expression buckets remain the alpha/expression layer, and risk hedge overlays are RiskManager-owned paper option actions.
- Scoped the initial options layer whitelist to long calls, long puts, call/put credit spreads, long straddles, and long strangles, with non-whitelisted structures rejected or downgraded.
- Clarified option simulation collateral model: V2 assumes a margin account / buying-power model for option trades, not cash-secured or security-secured requirements, while still tracking assignment exposure for short-option structures.
- Clarified account model: paper stock and option trades share one simulated margin account with unified account equity, margin requirement, buying power, excess liquidity, and assignment-risk checks.
- Refined the default estimated margin model: V2 should use a more realistic `estimated_fidelity_like_conservative_v1` broker-profile estimate with Reg T style initial requirements, house maintenance assumptions, conservative add-ons, explicit margin model/source metadata, and a future path for broker-observed requirement imports.
- Split mixed strategy/expression names: strong-theme, valuation-repair, and core-accumulation ideas are strategy playbooks, while `long_stock`, `defined_risk_directional_option`, `defined_risk_income_spread`, `volatility_event_option`, and `core_stock_accumulation` are pure expression buckets.
- Added peer/sector-leader earnings read-through as a `SignalPipeline` source family classified with macro/sector/theme context, not as a target-company signal.
- Clarified that target-company earnings releases, guidance, transcripts, and post-earnings analyst revisions remain ticker-level company signals in that ticker's own `quant_signal_snapshot`.
- Added portfolio-aware future event calendar requirements: normalize macro/earnings/Fed/company events, score relevance against current holdings/candidates/options/horizons, and show only material upcoming risks in the UI.
- Reframed peer earnings read-through rules as embedded event-calendar and signal-snapshot behavior, not a standalone function.
- Added source-ingestion freshness and signal coordination design: pre-open snapshots are the daily baseline, intraday snapshots reuse the same canonical schema as scoped deltas, and hourly refresh runs targeted freshness-gated source updates instead of full pipeline reruns.
- Clarified legacy table policy: `research_runs`, `research_outputs`, and `eval_results` are optional archival/compatibility artifacts, not required V2 trading-path dependencies or trade/portfolio scoring tables.
- Simplified risk configuration into `conservative`, `balanced`, and `aggressive` risk appetite presets; `RiskConfigResolver` generates detailed effective risk configs for audit/replay while hard safety rails remain invariant across presets.
- Resolved initial design questions: universe uses user-editable liquidity/sector filters, common-stock paper trading is long-only, holding period comes from strategy definitions, and manual ticker requests stay active until dismissed. Superseded on 2026-05-31: learning factors no longer activate immediately by default.

## 2026-05-31

- Updated the design and implementation plan to add point-in-time / no-lookahead data constraints. Source records and signal snapshots now require `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at`, and replay/decision paths must filter by decision-time availability.
- Added `HistoricalReplayOutcomeEvaluator` before reflection so trades, rejected candidates, watch items, manual requests, and shadow strategies are evaluated over strategy horizons against `SPY`, `QQQ`, sector/theme ETF, and decision-time peer baskets.
- Changed learning factor lifecycle policy: new factors default to `candidate` or `observation`; only risk-tightening factors may become automatically active, while score/risk expansion requires shadow/test evidence or explicit promotion.
- Added LLM output safety requirements: trading, intraday, reflection, learning extraction, and strategy proposal JSON must pass Pydantic validation with bounded retry and safe fallback.
- Added provider resilience requirements: rate limit, batch fetch, exponential backoff, request budget, cache/freshness gate, circuit breaker, persisted provider request telemetry, and degraded mode.
- Shrank the MVP/PR blast radius: first prove universe -> point-in-time signal snapshot -> strategy scoring -> replay/outcome evaluator before paper trading, options, intraday, reflection, or strategy evolution.
- Added `portfolio_intents` for approved core holdings, target/max weight, add/trim rules, thesis invalidators, and allowed tactical interactions.
- Added structured relationship data requirements: `ticker_relationships`, `peer_baskets`, and `theme_taxonomy` for peer/theme read-through, relative strength, and attribution.
- Added deterministic testing policy: unit tests use fake providers, provider integration tests use `vcrpy`/recorded cassettes, and live API smoke tests are opt-in and non-blocking for normal CI.
- Split the original oversized PR 1 into PR 1a minimal strategy/prompt/taxonomy foundation and PR 1b portfolio-intent/relationship graph schema, leaving universe/signal/replay operational tables for later PRs.
- Clarified PR 4 risk manager sequencing: PR 4 consumes fixture-backed `PortfolioContext` / `RiskContext`; PR 6 wires real paper portfolio snapshots into the same contract.
- Clarified historical replay v0 scope: PR 3 evaluates the three deterministic MVP signal families available after PR 2 and marks deeper transcript, SEC/insider, options, and macro/read-through strategies as unsupported/missing instead of pretending full-strategy replay exists.
- Expanded the PR 2 MVP signal surface from mostly market/relative-strength signals to three required families: technical, fundamental, and events/news, with point-in-time `FundamentalSnapshot` and `EventNewsItem` source rows.

## 2026-06-01

- Split the oversized design doc and implementation plan into modular docs under `plan/research_app/trading_agent_refactor/`, kept the old files as compatibility indexes, and added `module_contracts.md` to make cross-module inputs, outputs, consumers, and hard constraints explicit.
- Added `plan/research_app/trading_agent_refactor/implementation/reading_guide.md` with a PR-by-PR minimal context matrix so implementation agents can read only the required design modules, current PR module, module contracts, and direct upstream artifacts.
- Organized `documents/` and `plan/`: moved research-app deploy/runbook docs under `documents/research_app/`, archived older MVP and architecture-refactor plans under `plan/archive/`, added README indexes for active vs archived docs, updated references to moved paths, and removed stray `.DS_Store` files from `plan/`.
- Aggressively cleaned the active trading-agent plan entrypoints: moved the progress tracker into `plan/research_app/trading_agent_refactor/progress_tracker.md`, removed the old compatibility index files, and updated active docs to point directly at modular design and implementation files.
- Implemented PR 1a minimal trading foundation on branch `trading-agent-pr1a`:
  - Added seed strategy catalog helpers in `src/trading/strategy_catalog.py` with 19 tactical strategy/playbook rows and 5 expression buckets.
  - Added trade identity policy taxonomy in `src/trading/trade_taxonomy.py`.
  - Added trading prompt registry foundation in `src/agents/prompt_registry.py` and prompt metadata docs under `src/agents/prompts/`.
  - Added PR 1a ORM models and enums in `src/db/models/trading.py` and exported them from `src/db/models/__init__.py`.
  - Added Alembic migration `alembic/versions/005_trading_minimal_foundation_tables.py`.
  - Added focused tests under `tests/trading/`, `tests/agents/`, and `tests/db/`.
  - Added package markers for the new test directories so full pytest collection keeps unique module names.
  - Known gaps by design: no universe/signal pipeline behavior, no portfolio-intent/relationship graph schema, and no DB smoke/migration execution against Postgres in unit tests.
- Implemented PR 1b portfolio intents and relationship graph schema on branch `pr1b-portfolio-intents-relationships`:
  - Added pure portfolio-intent helpers in `src/trading/portfolio_intents.py` for active core-holding approval, max-weight lookup, and tactical interaction checks.
  - Added pure relationship graph helpers in `src/trading/relationships.py` for explicit allowed-use checks, deterministic peer-basket members, peer-basket definitions, and theme taxonomy nodes.
  - Added PR 1b ORM models and enums in `src/db/models/trading.py` and exported them from `src/db/models/__init__.py`.
  - Added Alembic migration `alembic/versions/006_portfolio_intents_relationship_graph.py`.
  - Added focused tests under `tests/trading/` and extended `tests/db/test_trading_models.py`.
  - Known gaps by design: no universe/signal pipeline behavior, no strategy scoring, no relationship inference, and no live Postgres migration smoke test.
- Implemented PR 2 provider resilience and three-family point-in-time signal MVP on branch `pr02-provider-resilience-signal-mvp`:
  - Added universe filtering in `src/trading/universe.py` with default common-stock/liquidity filters, sector/industry/exchange filters, manual exclusion reasons, and `TRADING_UNIVERSE_SYMBOLS` local fallback.
  - Added provider guardrails in `src/trading/provider_resilience.py` with cache/freshness decisions, request budgets, retry/backoff, circuit state, degraded-mode telemetry, and in-memory request recording for tests.
  - Added manual ticker request service in `src/trading/manual_requests.py` for active requests, dismiss/cancel state, result metadata, and `review_only` / `paper_trade_eligible` modes.
  - Added point-in-time source filtering and source repositories in `src/trading/point_in_time.py` and `src/trading/signal_sources.py`.
  - Added deterministic technical, fundamental, and events/news signal builders in `src/trading/technical_signals.py`, `src/trading/fundamental_signals.py`, and `src/trading/event_news_signals.py`, with explicit missing placeholders for deferred SEC/insider/transcript/options/macro read-through families.
  - Added pre-open `SignalPipeline` and `UniverseScanPipeline` in `src/trading/pipeline.py`, including active manual-request merge without trade approval bypass.
  - Added PR 2 ORM models/enums in `src/db/models/trading.py`, exports from `src/db/models/__init__.py`, and Alembic migration `alembic/versions/007_universe_signal_mvp_tables.py`.
  - Extended market-data provider contracts with universe asset support and added an Alpaca active-asset adapter method.
  - Added a minimal `SourceIngestionService` adapter that calls existing market/news providers behind `ProviderResiliencePolicy`, converts technical bars, provider context, and news rows into `SourceRecord` plus repository-level `FundamentalSnapshot` / `EventNewsItem` artifacts, and records `SourceIngestionRun` / linked `ProviderRequestRun` metadata through the repository abstraction.
  - Added standalone PR 2 source-ingestion smoke coverage in `scripts/run_trading_source_ingestion_smoke.py` and documented the opt-in live API commands in the PR reading guide.
  - Known gaps by design: no strategy scoring, trading decisions, risk checks, paper orders, intraday refresh, UI, full SEC/insider/transcript parsing, option-chain signals, or live Postgres migration smoke test.
- Implemented PR 3 strategy matching and historical replay outcome evaluator on branch `pr3-strategy-matching-replay`:
  - Added deterministic strategy matching in `src/trading/strategy_matching.py` for PR 2 technical, fundamental, and events/news MVP signals, with rejected rows for direct negative catalysts and unsupported deferred source families.
  - Added primary strategy selection in `src/trading/primary_strategy_selector.py` to freeze one selected strategy and expression bucket per ticker/action before trade classification.
  - Added trade identity classification in `src/trading/trade_classifier.py`, including `catalyst_watch` vs ordinary `watch_only` handling and active portfolio-intent gating for `core_holding`.
  - Added confidence calibration inputs in `src/trading/confidence_calibration.py` from historical `candidate_outcome_evaluations`.
  - Added deterministic outcome evaluation and replay orchestration in `src/trading/outcome_evaluator.py` and `src/trading/historical_replay.py`; replay reconstructs from stored decision-available signal snapshots and uses future prices only for outcome measurement.
  - Extended `src/trading/repository.py` and `src/trading/pipeline.py` with PR 3 in-memory persistence and a `StrategyPipeline` that stops before `TradingPipeline`.
  - Added PR 3 ORM models/enums in `src/db/models/trading.py`, exports from `src/db/models/__init__.py`, and Alembic migration `alembic/versions/008_strategy_matching_replay_tables.py`.
  - Added focused tests for strategy matching, primary selection, trade classification, confidence calibration, outcome evaluation, historical replay, repository storage, and DB model/migration coverage.
  - Known gaps by design: no TradingPipeline call, no paper orders, no risk/sizing, no live Postgres migration smoke test, no option-chain strategy replay, and no backfill for full transcript, SEC/insider, or macro/read-through source families.

## PR Slice Status

| Slice | Scope | Status | Notes |
| --- | --- | --- | --- |
| PR 1a | Minimal trading foundation | Ready for review | Adds strategy definitions, prompt registry/schema, 15 broad tactical strategies, 4 eval-derived playbooks, 5 expression buckets, and trade identity taxonomy. No universe/signal/relationship tables. Verified with targeted and broader PR 1a tests. |
| PR 1b | Portfolio intents + relationship graph schema | Ready for review | Adds portfolio intents, ticker relationships, peer baskets, theme taxonomy, and pure helpers for core-holding eligibility and structured peer/theme data. No signal pipeline, strategy scoring, or relationship inference. |
| PR 2 | Provider resilience + three-family point-in-time signal MVP | Ready for review | Adds provider guardrails, provider-backed source ingestion adapter with fake-provider test path, request telemetry, user-editable universe filters, persistent manual requests, technical/fundamental/events-news signal snapshots, `FundamentalSnapshot`/`EventNewsItem` source rows, and source availability metadata. |
| PR 3 | Strategy matching + historical replay outcome evaluator | Ready for review | Adds source attribution, primary strategy selection, trade classification, catalyst-watch split, bearish gating, confidence calibration inputs, and replay v0 for the PR 2 technical/fundamental/events-news MVP signal families. Stops before TradingPipeline/paper trading. |
| PR 4 | Position sizing + portfolio risk manager | Pending | Depends on candidates and risk tables; adds fixture-backed `PortfolioContext` / `RiskContext`, simple risk appetite presets, generated risk configs, invariant hard safety rails, and conservative broker-profile margin estimates. |
| PR 5 | Trading decision agent guardrails | Pending | Adds bounded LLM trading output with Pydantic validation, retry, safe fallback, prompt/schema persistence, full context snapshot, and no paper order side effects yet. |
| PR 6 | Paper stock broker + portfolio state | Pending | Adds stock paper orders/executions/positions, unified simulated margin account, margin model/source metadata, and order idempotency. |
| PR 7 | Paper options strategy layer + assignment risk | Pending | Paper/simulation-only whitelisted option strategies: long call/put, call/put credit spread, long straddle, and long strangle; includes conservative option margin formulas, RiskManager-owned hedge overlays, option-risk snapshots, and worst-case assignment checks when relevant. |
| PR 8 | Intraday signal refresh + news alerts + rebalance | Pending | Hourly freshness-gated signal/news refresh during market hours; intraday snapshots are scoped deltas vs pre-open baseline and previous hourly snapshot before risk-gated stock/paper-option actions. |
| PR 9 | Reflection + learning factors | Pending | Uses highest-quality configured reflection model with Pydantic fallback; consumes replay outcomes; new learning factors default to candidate/observation unless risk-tightening. |
| PR 10 | Strategy evolution + dynamic strategy catalog | Pending | Converts repeated learning into candidate/shadow strategies beyond the initial seeds after replay evidence and schema-validated proposals. |
| PR 11 | Today dashboard UI | Pending | Tabbed workstation with PIT audit, trade drill-downs, strategy performance, relationship/core-intent views, and LLM/API/provider telemetry. |
| PR 12 | Scheduler, smoke tests, deploy docs | Pending | Final operational wiring, including manual ticker review job, intraday signal refresh job, replay smoke, fixture/cassette tests, opt-in live smoke, and deploy docs. |

## Verification Log

- 2026-05-29: `git diff --check` passed for the planning-only update.
- 2026-05-29: `git diff --check` passed after adding Manual Ticker Review / Pinned Review planning updates.
- 2026-05-29: `git diff --check` passed after adding tabbed UI workstation planning updates.
- 2026-05-29: `git diff --check` passed after adding prompt versioning and persistence planning updates.
- 2026-05-30: `git diff --check` passed after clarifying strategy-horizon attribution wording.
- 2026-05-30: `git diff --check` passed after embedding bearish evidence handling and trade identity as cross-pipeline constraints.
- 2026-05-30: `git diff --check` passed after separating trading strategies, expression buckets, portfolio-pool trade identities, and RiskManager-owned hedge overlays.
- 2026-05-30: `git diff --check` passed after generalizing the paper options layer from put-only plans to leg-based single-leg and multi-leg option strategies.
- 2026-05-30: `git diff --check` passed after changing option simulation from cash-secured assumptions to margin requirement and buying-power modeling.
- 2026-05-30: `git diff --check` passed after unifying paper stock and option trades under one simulated margin account.
- 2026-05-30: `git diff --check` passed after splitting mixed strategy/expression IDs into strategy playbooks and pure expression buckets.
- 2026-05-30: `git diff --check` passed after classifying peer earnings read-through as macro/sector/theme context in the signal pipeline.
- 2026-05-30: `git diff --check` passed after clarifying target-company earnings as ticker-level company signals.
- 2026-05-30: `git diff --check` passed after adding portfolio-aware upcoming event calendar design and UI requirements.
- 2026-05-30: `git diff --check` passed after embedding peer earnings read-through rules into event-calendar and signal-snapshot workflow text.
- 2026-05-30: `git diff --check` passed after adding source-ingestion freshness, pre-open baseline, and intraday delta snapshot coordination.
- 2026-05-30: `git diff --check` passed after refining the default estimated margin model into a conservative broker-profile model with margin model/source metadata.
- 2026-05-30: `git diff --check` passed after clarifying legacy research/eval tables as optional non-critical-path artifacts.
- 2026-05-30: `git diff --check` passed after simplifying risk configuration into risk appetite presets and generated effective risk configs.
- 2026-05-30: `git diff --check` passed after resolving initial design questions for universe filters, long-only common stock, strategy-defined horizons, immediate learning activation, and manual request dismissal.
- 2026-05-30: `git diff --check` passed after restricting the initial paper options whitelist to long call/put, call/put credit spreads, long straddles, and long strangles.
- 2026-05-31: `git diff --check` passed after adding PIT/no-lookahead constraints, historical replay evaluator, safer learning-factor lifecycle, LLM validation/fallback, provider resilience, smaller PR slices, portfolio intents, relationship graph, and deterministic testing policy.
- 2026-05-31: `git diff --check` passed after splitting PR 1 into PR 1a/1b, clarifying PR 4 `PortfolioContext` sequencing, and limiting PR 3 replay v0 to PR 2 deterministic signal families.
- 2026-05-31: `git diff --check` passed after expanding PR 2/PR 3 planning to three MVP signal families: technical, fundamental, and events/news.
- 2026-06-01: `git diff --check` passed after modularizing the design and implementation plan. Custom checks confirmed the split design body and all implementation PR sections preserve the original text exactly, all 68 original design headings and all 25 original implementation headings exist in the modules, and all new relative Markdown links resolve.
- 2026-06-01: `git diff --check` passed after adding the PR reading guide. A custom Markdown link check confirmed all relative links in the trading-agent refactor planning docs resolve.
- 2026-06-01: `git diff --check` passed after `documents/` and `plan/` directory cleanup. Custom checks confirmed Markdown links under `documents/` and `plan/` resolve, stale moved-path references are gone, and no `.DS_Store` files remain under those directories.
- 2026-06-01: `git diff --check` passed after aggressive trading-agent plan entrypoint cleanup. Custom checks confirmed Markdown links under `documents/` and `plan/` resolve, stale root trading-agent index/tracker references are gone, and the old root trading-agent doc/index files no longer exist.
- 2026-06-01: PR 1a baseline before implementation: `source ~/.venv/bin/activate && pytest -q` passed with 235 tests.
- 2026-06-01: PR 1a RED checks failed for expected missing modules/models:
  - `pytest tests/trading/test_strategy_catalog.py -q`
  - `pytest tests/trading/test_trade_taxonomy.py -q`
  - `pytest tests/agents/test_prompt_registry.py -q`
  - `pytest tests/db/test_trading_models.py -q`
- 2026-06-01: PR 1a targeted verification passed: `source ~/.venv/bin/activate && pytest tests/agents/test_prompt_registry.py tests/trading/test_strategy_catalog.py tests/trading/test_trade_taxonomy.py tests/db/test_trading_models.py -q` passed with 13 tests.
- 2026-06-01: PR 1a broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/agents/test_prompt_registry.py tests/db tests/trading -q` passed with 13 tests.
- 2026-06-01: PR 1a full verification passed after adding package markers for new test directories: `source ~/.venv/bin/activate && pytest -q` passed with 248 tests.
- 2026-06-01: PR 1a Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 1a diff whitespace checks passed for tracked changes and new files with `git diff --check` plus no-index checks over untracked files.
- 2026-06-01: PR 1b baseline before implementation: `source ~/.venv/bin/activate && pytest tests/db tests/trading -q` passed with 11 tests.
- 2026-06-01: PR 1b RED checks failed for expected missing modules/models:
  - `pytest tests/trading/test_portfolio_intents.py -q`
  - `pytest tests/trading/test_relationships.py -q`
  - `pytest tests/db/test_trading_models.py -q`
- 2026-06-01: PR 1b targeted verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_intents.py tests/trading/test_relationships.py tests/db/test_trading_models.py -q` passed with 13 tests.
- 2026-06-01: PR 1b broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/db tests/trading -q` passed with 20 tests.
- 2026-06-01: PR 1b full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 257 tests.
- 2026-06-01: PR 1b Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 1b diff whitespace checks passed with `git diff --check`.
- 2026-06-01: PR 2 baseline before implementation: `source ~/.venv/bin/activate && pytest tests/db tests/trading -q` passed with 20 tests.
- 2026-06-01: PR 2 RED checks failed for expected missing modules/models:
  - `pytest tests/trading/test_universe.py tests/trading/test_provider_resilience.py tests/trading/test_point_in_time.py tests/trading/test_manual_requests.py tests/trading/test_signal_sources.py tests/trading/test_fundamental_signals.py tests/trading/test_event_news_signals.py tests/trading/test_relative_strength.py tests/trading/test_signals.py tests/trading/test_pipeline.py tests/db/test_trading_models.py -q`
- 2026-06-01: PR 2 targeted verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_universe.py tests/trading/test_provider_resilience.py tests/trading/test_point_in_time.py tests/trading/test_manual_requests.py tests/trading/test_signal_sources.py tests/trading/test_fundamental_signals.py tests/trading/test_event_news_signals.py tests/trading/test_relative_strength.py tests/trading/test_signals.py tests/trading/test_pipeline.py tests/db/test_trading_models.py -q` passed with 25 tests.
- 2026-06-01: PR 2 broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/db tests/trading tests/tools/test_market_data.py -q` passed with 55 tests.
- 2026-06-01: PR 2 full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 276 tests.
- 2026-06-01: PR 2 Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 2 diff whitespace checks passed for tracked changes with `git diff --check`; untracked file no-index whitespace check emitted no whitespace errors.
- 2026-06-01: PR 2 follow-up extracted explicit technical signal module after review feedback. Focused verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_technical_signals.py tests/trading/test_signals.py tests/trading/test_relative_strength.py -q` passed with 5 tests.
- 2026-06-01: PR 2 follow-up full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 278 tests.
- 2026-06-01: PR 2 follow-up RED checks failed for the missing provider-backed source ingestion adapter:
  - `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py tests/trading/test_pipeline.py -q`
- 2026-06-01: PR 2 provider-backed source ingestion adapter targeted verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py tests/trading/test_pipeline.py -q` passed with 4 tests.
- 2026-06-01: PR 2 provider-backed source ingestion adapter broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/trading tests/db -q` passed with 43 tests.
- 2026-06-01: PR 2 provider-backed source ingestion adapter full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 280 tests.
- 2026-06-01: PR 2 source-ingestion smoke script RED check failed for expected missing script: `source ~/.venv/bin/activate && pytest tests/test_run_trading_source_ingestion_smoke.py -q`.
- 2026-06-01: PR 2 source-ingestion smoke script unit verification passed: `source ~/.venv/bin/activate && pytest tests/test_run_trading_source_ingestion_smoke.py -q` passed with 1 test.
- 2026-06-01: PR 2 live API smoke passed with the documented command `LOG_LEVEL=WARNING python scripts/run_trading_source_ingestion_smoke.py --env-file /Users/shuxinxu/repos/equity_research_agent/.env --ticker AAPL --families technical fundamental events_news --json`; source records were `technical=1`, `fundamental=1`, `events_news=5`; provider request statuses were `succeeded` for `market_bars`, `market_context`, and `news`.
- 2026-06-01: PR 2 source-ingestion smoke script full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 281 tests.
- 2026-06-01: PR 2 source-ingestion smoke detail output now supports `--include-records`; RED/green verification passed with `source ~/.venv/bin/activate && pytest tests/test_run_trading_source_ingestion_smoke.py -q`, and live SNDK events/news smoke returned 5 normalized `event_news_items` plus provider timing fields.
- 2026-06-01: PR 2 source-ingestion smoke detail output full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 282 tests.
- 2026-06-01: PR 3 baseline in isolated worktree: `source ~/.venv/bin/activate && pytest -q` passed with 282 tests.
- 2026-06-01: PR 3 RED checks failed for expected missing modules/models:
  - `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py tests/trading/test_primary_strategy_selector.py tests/trading/test_trade_classifier.py tests/trading/test_confidence_calibration.py tests/trading/test_outcome_evaluator.py tests/trading/test_historical_replay.py tests/trading/test_candidate_repository.py tests/db/test_trading_models.py -q`
- 2026-06-01: PR 3 targeted verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py tests/trading/test_primary_strategy_selector.py tests/trading/test_trade_classifier.py tests/trading/test_confidence_calibration.py tests/trading/test_outcome_evaluator.py tests/trading/test_historical_replay.py tests/trading/test_candidate_repository.py tests/db/test_trading_models.py -q` passed with 22 tests.
- 2026-06-01: PR 3 broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/trading tests/db -q` passed with 57 tests.
- 2026-06-01: PR 3 full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 296 tests.
- 2026-06-01: PR 3 Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 3 diff whitespace checks passed with `git diff --check` and an untracked-file trailing-whitespace scan using `git ls-files --others --exclude-standard` plus `rg -n "[ \t]$"`.
- 2026-06-01: PR 4 baseline before implementation: `source ~/.venv/bin/activate && pytest tests/db tests/trading -q` passed with 72 tests.
- 2026-06-01: PR 4 RED checks failed for expected missing modules/models:
  - `source ~/.venv/bin/activate && pytest tests/trading/test_risk_context.py tests/trading/test_position_sizing.py tests/trading/test_risk_manager.py tests/trading/test_candidate_repository.py tests/trading/test_navigation_imports.py tests/db/test_trading_models.py -q`
- 2026-06-01: PR 4 implemented deterministic risk modules under `src/trading/risk/`, extended `src/trading/repositories/in_memory.py`, added ORM models in `src/db/models/trading.py`, added Alembic revision `009_position_sizing_risk_manager_tables.py`, and updated `documents/repo_overview.md`.
- 2026-06-01: PR 4 targeted verification passed: `source ~/.venv/bin/activate && pytest tests/trading/test_risk_context.py tests/trading/test_position_sizing.py tests/trading/test_risk_manager.py tests/trading/test_candidate_repository.py tests/trading/test_navigation_imports.py tests/db/test_trading_models.py -q` passed with 26 tests.
- 2026-06-01: PR 4 broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/db tests/trading -q` passed with 72 tests.
- 2026-06-01: PR 4 full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 317 tests.
- 2026-06-01: PR 4 Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 4 diff whitespace checks passed with `git diff --check`.
- 2026-06-01: PR 5 baseline before implementation: `source ~/.venv/bin/activate && pytest tests/agents/test_trading_schemas.py tests/agents/test_trading_agent.py tests/trading/test_trading_decision_repository.py tests/trading/test_navigation_imports.py -q` failed during collection for expected missing modules `src.agents.trading_schemas`, `src.agents.trading`, and `src.trading.workflows.trading_decision`.
- 2026-06-01: PR 5 implemented bounded trading-agent guardrails in `src/agents/trading.py`, `src/agents/trading_schemas.py`, `src/trading/workflows/trading_decision.py`, prompt template `src/agents/prompts/trading/trading_decision_v1.yaml`, extended `src/trading/repositories/in_memory.py`, added ORM model `TradingDecision` in `src/db/models/trading.py`, added Alembic revision `010_trading_decision_guardrails.py`, and updated `documents/repo_overview.md`.
- 2026-06-01: PR 5 targeted verification passed: `source ~/.venv/bin/activate && pytest tests/agents/test_trading_schemas.py tests/agents/test_trading_agent.py tests/trading/test_trading_decision_repository.py tests/trading/test_navigation_imports.py tests/db/test_trading_models.py -q` passed with 26 tests.
- 2026-06-01: PR 5 broader relevant verification passed: `source ~/.venv/bin/activate && pytest tests/agents tests/trading tests/db -q` passed with 82 tests.
- 2026-06-01: PR 5 full verification passed: `source ~/.venv/bin/activate && pytest -q` passed with 325 tests.
- 2026-06-01: PR 5 Alembic offline SQL generation passed: `source ~/.venv/bin/activate && alembic upgrade head --sql`.
- 2026-06-01: PR 5 diff whitespace checks passed with `git diff --check`.
