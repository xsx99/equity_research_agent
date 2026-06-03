# Live Preopen Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the PR 12 fixture-backed trading preopen runtime into a real live preopen pipeline that loads production configuration from Postgres, uses real providers/broker state, persists trading artifacts to Postgres, and can safely drive the morning decision path end-to-end.

**Architecture:** Keep Python orchestration as the source of truth and keep APScheduler job boundaries unchanged. Replace fixture-only runtime assembly with production adapters in layers: configuration/data loading, source ingestion and point-in-time signal persistence, strategy/risk/decision orchestration, and operational verification. Preserve the existing fixture smoke modes as a cheap CI path while adding explicit live wiring for the scheduler-facing `preopen` phase.

**Tech Stack:** Python, SQLAlchemy ORM, Alembic, Postgres JSONB, APScheduler, pytest, existing market/news/global-context providers, Alpaca paper account sync, versioned prompt registry.

---

## Scope

This PR is intentionally limited to the morning live path. It should not expand the feature surface of intraday refresh, reflection, or strategy evolution beyond what is required to keep their current scheduler hooks intact.

Target live chain for this PR:

1. Load active universe filter config from Postgres.
2. Load active manual ticker requests from Postgres.
3. Build the morning universe from a real `UniverseProvider`.
4. Ingest real source families through provider guardrails into Postgres-backed source tables.
5. Rebuild point-in-time signal snapshots from Postgres-backed source repositories.
6. Run strategy matching and classification with persisted outputs.
7. Build live `PortfolioContext` from Alpaca-backed portfolio sync.
8. Run deterministic sizing and risk approval.
9. Run trading decision generation through a real configured LLM runner.
10. Optionally stage or execute paper trades only if the current operator policy already allows it.

Out of scope for this PR:

- new UI tabs or UI workflow changes
- new strategy definitions
- new option strategy types
- replacing the existing fixture smoke modes
- broad intraday/reflection runtime redesign

## Production Gaps To Close

Current PR 12 runtime remains fixture-backed because:

- `src/trading/runtime.py` hardcodes `_fixed_now()` and fixture providers.
- preopen uses `InMemoryTradingRepository` and `InMemorySignalSourceRepository`.
- active universe filters are not loaded from Postgres.
- manual ticker requests are not loaded from `manual_ticker_requests`.
- `SourceIngestionService` has no SQLAlchemy artifact repository adapter for production writes.
- `SignalPipeline` has no SQL-backed source repository adapter for PIT reads.
- `SQLAlchemyTradingRepository` does not yet persist/load the preopen artifacts used by PR 2/3/5.
- `TradingAgent` has no default live `agent_runner`.
- runtime does not yet connect `PositionSizer`, `RiskManager`, `TradingDecisionPipeline`, and `PaperExecutionWorkflow` into one morning chain.

## File Plan

### Create

- `src/trading/runtime_live.py`
  Production-only runtime assembly for the live preopen path.
- `src/trading/repositories/source_sqlalchemy.py`
  SQL-backed source repository for `SignalPipeline` PIT reads and source persistence helpers if a clean split is needed.
- `src/trading/manual_review/sqlalchemy.py`
  DB-backed manual ticker request service/adapter.
- `src/trading/data_sources/live_universe.py`
  Real `UniverseProvider` implementation backed by the chosen production provider.
- `tests/trading/test_runtime_live.py`
  Focused orchestration tests for the live preopen path using fake providers and fake DB adapters.
- `tests/trading/test_manual_request_sqlalchemy.py`
  Focused tests for DB-backed active manual request loading and evaluation updates.
- `tests/trading/test_signal_source_sqlalchemy.py`
  Focused tests for PIT reads from Postgres-backed source tables.

### Modify

- `src/trading/runtime.py`
  Keep fixture smoke modes, but route scheduler-facing live preopen execution into the new runtime module.
- `src/trading/repositories/sqlalchemy.py`
  Add missing PR 2/3/5 persistence and load methods for universe, signals, candidates, classifications, prompt telemetry, and trading decisions.
- `src/trading/workflows/signal_snapshot.py`
  Generalize source repository typing away from the in-memory concrete class.
- `src/trading/workflows/strategy_scoring.py`
  Ensure repository protocol assumptions match the SQL implementation.
- `src/trading/workflows/trading_decision.py`
  Wire to a real configured `agent_runner`, and ensure DB persistence methods are present.
- `src/trading/signals/source_ingestion.py`
  Ensure the artifact repository protocol matches the SQL production repository.
- `src/trading/workflows/universe_scan.py`
  Ensure real provider + persisted config loading fit cleanly.
- `src/trading/workflows/portfolio_sync.py`
  Reuse for live morning `PortfolioContext` creation.
- `src/scheduler/jobs/trading_preopen_job.py`
  Point the job at the live runtime entrypoint while preserving logging/error semantics.
- `scripts/run_trading_once.py`
  Allow explicit live-preopen execution and clear mode/reporting.
- `scripts/run_trading_smoke_test.py`
  Preserve fixture defaults and add explicit opt-in live smoke where appropriate.
- `documents/research_app/runbook.md`
  Document live preopen trigger, failure modes, and safe smoke/test commands.
- `documents/research_app/deploy.md`
  Document production env requirements for the live preopen path.
- `documents/repo_overview.md`
  Update architecture summary once the live path exists.

### Likely Alembic / ORM Touches

- `src/db/models/trading.py`
  Only if existing tables are insufficient for runtime bookkeeping or active-config lookup.
- `alembic/versions/`
  Only if the live path requires schema additions beyond current PR 12/earlier contracts.

## Task 1: Define The Live Preopen Runtime Boundary

**Files:**
- Create: `src/trading/runtime_live.py`
- Modify: `src/trading/runtime.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Write the failing orchestration tests for a live preopen entrypoint that does not use fixture providers or fixed timestamps.
- [ ] Run the new focused runtime test file and confirm it fails for the expected missing module/API reasons.
- [ ] Implement a new live runtime entrypoint with explicit dependencies:
  - active universe filter loader
  - manual request loader
  - real universe provider
  - source ingestion artifact repository
  - source snapshot repository
  - trading artifact repository
  - broker portfolio sync
  - trading decision runner
- [ ] Keep the existing fixture smoke modes in `src/trading/runtime.py` unchanged except for delegating live preopen execution to the new module.
- [ ] Re-run the focused runtime tests and confirm they pass.

## Task 2: Add DB-Backed Universe Filter And Manual Request Loading

**Files:**
- Create: `src/trading/manual_review/sqlalchemy.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_manual_request_sqlalchemy.py`

- [ ] Write failing tests that load the active universe filter config and active manual ticker requests from Postgres-backed fixtures.
- [ ] Run the focused tests and confirm they fail because the SQL loaders do not exist yet.
- [ ] Add SQL-backed helpers for:
  - loading the active `UniverseFilterConfig`
  - loading active manual ticker requests
  - recording evaluation status/snapshot ids back to `manual_ticker_requests`
- [ ] Ensure the runtime can use these loaders without depending on the in-memory manual request service.
- [ ] Re-run the focused SQL manual-request tests and confirm they pass.

## Task 3: Add SQL-Backed Source Persistence And PIT Reads

**Files:**
- Create: `src/trading/repositories/source_sqlalchemy.py`
- Modify: `src/trading/signals/source_ingestion.py`
- Modify: `src/trading/workflows/signal_snapshot.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_signal_source_sqlalchemy.py`

- [ ] Write failing tests for:
  - persisting `SourceIngestionRunRecord`
  - persisting `ProviderRequestRunRecord`
  - persisting normalized `FundamentalSnapshotRecord`
  - persisting normalized `EventNewsItemRecord`
  - loading PIT source rows for one ticker/decision time
- [ ] Run the focused source repository tests and confirm they fail for missing persistence/load methods.
- [ ] Add the SQL-backed artifact methods required by `SourceIngestionService`.
- [ ] Add a SQL-backed source repository that can reconstruct `SourceRecord` rows from normalized Postgres tables under the `available_for_decision_at <= decision_time` contract.
- [ ] Generalize `SignalPipeline` so it depends on a repository protocol, not on `InMemorySignalSourceRepository`.
- [ ] Re-run the focused source repository tests and confirm they pass.

## Task 4: Persist Morning Universe, Signals, Candidates, And Classifications To Postgres

**Files:**
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/workflows/universe_scan.py`
- Modify: `src/trading/workflows/strategy_scoring.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Write failing tests for missing SQL persistence/load methods:
  - `save_universe_snapshot`
  - `save_signal_snapshot`
  - `load_signal_snapshots_for_decision`
  - `save_candidate_scores`
  - `save_trade_classifications`
- [ ] Run the focused repository/runtime tests and confirm failure.
- [ ] Implement the missing repository methods against existing ORM models.
- [ ] Ensure persisted rows preserve point-in-time metadata, manual request linkage, and source refs.
- [ ] Re-run focused repository/runtime tests and confirm they pass.

## Task 5: Wire Live Portfolio Sync, Position Sizing, And Risk Approval

**Files:**
- Modify: `src/trading/runtime_live.py`
- Modify: `src/trading/workflows/portfolio_sync.py`
- Modify: `src/trading/risk/sizing.py` only if interface gaps are discovered
- Modify: `src/trading/risk/manager.py` only if interface gaps are discovered
- Test: `tests/trading/test_runtime_live.py`

- [ ] Write failing orchestration tests that expect the live preopen runtime to:
  - call `BrokerPortfolioSyncWorkflow`
  - size morning candidates
  - produce risk decisions
- [ ] Run focused runtime tests and verify failure.
- [ ] Implement the runtime wiring from selected candidates/classifications into `TradeRiskRequest`, `PositionSizer`, and `RiskManager`.
- [ ] Persist generated sizing decisions, portfolio risk snapshots, factor exposures, and risk decisions through the SQL repository.
- [ ] Re-run focused runtime tests and confirm they pass.

## Task 6: Add A Real Trading Agent Runner And Live Decision Persistence

**Files:**
- Modify: `src/agents/trading.py`
- Modify: `src/trading/workflows/trading_decision.py`
- Modify: `src/trading/runtime_live.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/agents/test_trading_agent.py`
- Test: `tests/trading/test_trading_decision_repository.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Write failing tests that prove the live runtime can build a `TradingDecisionPipeline` with a configured non-stub runner.
- [ ] Run the focused decision/runtime tests and verify failure because `_default_agent_runner` is not configured for production use.
- [ ] Implement a real agent runner factory consistent with the repo’s existing LLM/provider patterns.
- [ ] Keep validation, retry, and safe fallback behavior unchanged.
- [ ] Add missing SQL persistence methods for prompt telemetry and trading decisions if they are still absent.
- [ ] Re-run the focused decision/runtime tests and confirm they pass.

## Task 7: Decide And Wire Paper Execution Policy For Morning Live Runs

**Files:**
- Modify: `src/trading/runtime_live.py`
- Modify: `scripts/run_trading_once.py`
- Modify: `documents/research_app/runbook.md`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Write failing tests for the morning execution policy:
  - dry-run only by default, or
  - execute approved paper trades only when an explicit flag/config is enabled
- [ ] Run focused runtime tests and confirm failure.
- [ ] Implement the chosen policy explicitly in the runtime and command-line surface so morning runs cannot silently submit paper orders without operator intent.
- [ ] Re-run focused runtime tests and confirm they pass.

## Task 8: Preserve Fixture Smoke Paths While Adding Opt-In Live Smoke

**Files:**
- Modify: `scripts/run_trading_smoke_test.py`
- Modify: `src/trading/runtime.py`
- Test: `tests/scripts/test_run_trading_smoke_test.py`

- [ ] Write failing tests for explicit live-smoke CLI behavior without breaking existing fixture modes.
- [ ] Run the focused smoke CLI tests and confirm failure.
- [ ] Add a clearly named opt-in live smoke mode for the preopen runtime using a tiny ticker set and strict request budget.
- [ ] Keep fixture modes as the default CI path.
- [ ] Re-run the focused smoke CLI tests and confirm they pass.

## Task 9: Update Runbook, Deploy Guide, And Architecture Summary

**Files:**
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/research_app/deploy.md`
- Modify: `documents/repo_overview.md`

- [ ] Document the live preopen path, required env vars, expected scheduler behavior, and how to manually trigger one run safely.
- [ ] Document how to distinguish fixture smoke from live preopen execution.
- [ ] Document how to verify Postgres persistence remains on disk using `SHOW data_directory;`.
- [ ] Update the architecture summary so the repository overview no longer describes preopen as fixture-only once the live path is complete.

## Task 10: Full Verification And Stop For Review

**Files:**
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_manual_request_sqlalchemy.py`
- Test: `tests/trading/test_signal_source_sqlalchemy.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/agents/test_trading_agent.py`
- Test: `tests/trading/test_trading_decision_repository.py`
- Test: `tests/scripts/test_run_trading_smoke_test.py`
- Test: `tests/test_scheduler_jobs.py`

- [ ] Run the focused live-preopen verification suite.
- [ ] Run the broader relevant suites for `tests/trading`, `tests/agents`, and `tests/db`.
- [ ] Run `pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Run one explicit fixture smoke command and one explicit live-preopen smoke command.
- [ ] Update `plan/research_app/trading_agent_refactor/progress_tracker.md` with files changed, commands run, results, and any live-smoke caveats.
- [ ] Stop after PR 13 for review/merge before any further live intraday or reflection productionization work.
