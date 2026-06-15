# Risk Macro Event Backend Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote macro regime, event calendar, and portfolio event-risk assessments into first-class persisted backend contracts so trading decisions, RiskManager, and `/today` all consume the same point-in-time risk context instead of missing fields or duplicated summary strings.

**Architecture:** Add canonical ORM tables and repository records for macro snapshots, macro read-through events, normalized calendar events, and portfolio event-risk assessments. Build deterministic pre-open/intraday pipelines that populate those records, wire them into `PortfolioHedgePlanner` / `RiskManager`, then expose a compact `/today` backend read model for the frontend plan to render.

**Tech Stack:** Python, pytest, SQLAlchemy ORM, Alembic, FastAPI read models, existing trading runtime workflows, existing provider resilience telemetry.

---

## Required Pre-Read

- `documents/general_instructions.md`
- `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- `plan/research_app/trading_agent_refactor/design/06_paper_trading_and_risk.md`
- `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- `plan/research_app/trading_agent_refactor/design/09_ui_error_testing_delivery.md`
- `docs/superpowers/plans/2026-06-13-risk-manager-lookahead-hedge.md`

## Current Gap

- `PortfolioRiskSnapshot`, `PortfolioRiskIntent`, `RiskFactorExposure`, and `RiskDecision` exist.
- `PortfolioHedgePlanner` exists, but its event assessments are built opportunistically from signal snapshots/news, not persisted as canonical event-risk rows.
- `macro_snapshots`, `macro_readthrough_events`, `calendar_events`, and `portfolio_event_risk_assessments` are described in design docs but are not implemented as ORM/repository/runtime contracts.
- `/today` currently derives `header.macro_regime` from `latest_risk.metadata_json["macro_regime"]`, so missing backend data becomes `unavailable`.

## File Map

- `src/db/models/trading.py`
  - Add ORM models and constraints for macro/event/risk-context persistence.
- `src/db/models/__init__.py`
  - Export new ORM models if the package export list requires it.
- `alembic/versions/022_risk_macro_event_contract.py`
  - Add the new tables, indexes, uniqueness rules, and JSON defaults.
- `src/trading/macro/context.py`
  - New pure dataclass records for macro snapshots and macro read-through events.
- `src/trading/macro/pipeline.py`
  - New deterministic macro snapshot builder over provider/fallback inputs.
- `src/trading/macro/__init__.py`
  - Package exports for macro records and pipeline.
- `src/trading/events/calendar.py`
  - New normalized calendar event records and calendar assembly pipeline.
- `src/trading/events/risk.py`
  - New portfolio-aware event-risk assessment builder.
- `src/trading/events/__init__.py`
  - Package exports for event calendar and event-risk records.
- `src/trading/risk/lookahead.py`
  - Reconcile existing `PortfolioEventRiskAssessmentRecord` with the new persisted event-risk contract.
- `src/trading/runtime/lookahead_risk.py`
  - Consume persisted/current event-risk assessments instead of rebuilding all risk context from summary strings.
- `src/trading/runtime/preopen_dependencies.py`
  - Wire macro/event pipelines into live pre-open dependencies.
- `src/trading/runtime/preopen_runner.py`
  - Run macro/event refresh before signal scoring and risk approval.
- `src/trading/runtime/preopen_risk.py`
  - Pass canonical macro/event context into risk planning and final approvals.
- `src/trading/runtime/intraday_refresh_dependencies.py`
  - Wire scoped intraday event/macro refresh dependencies.
- `src/trading/runtime/intraday_refresh_runner.py`
  - Refresh only stale/material context and persist deltas during market hours.
- `src/trading/repositories/in_memory.py`
  - Add test repository support for macro/event records.
- `src/trading/repositories/sqlalchemy.py`
  - Add save/load methods for macro snapshots, calendar events, event-risk assessments, and the `/today` risk macro read inputs.
- `src/web/presenters/today_risk_macro.py`
  - New backend presenter that converts persisted macro/event/risk rows into a stable UI read model.
- `src/web/routers/today.py`
  - Replace ad hoc risk/macro assembly with the presenter output.
- `scripts/run_trading_macro_event_db_smoke.py`
  - New DB smoke that upserts/loads macro snapshot, calendar events, event-risk assessments, and `/today` read model inputs.
- `tests/db/test_trading_models.py`
  - Schema and constraint coverage.
- `tests/trading/test_macro_context.py`
  - Pure macro contract tests.
- `tests/trading/test_macro_pipeline.py`
  - Macro pipeline behavior tests.
- `tests/trading/test_event_calendar.py`
  - Calendar normalization and event-risk scoring tests.
- `tests/trading/test_sqlalchemy_repository.py`
  - Persistence round-trip tests.
- `tests/trading/test_lookahead_risk.py`
  - Runtime helper consumption of canonical event-risk rows.
- `tests/trading/test_runtime_live.py`
  - Pre-open wiring coverage.
- `tests/trading/test_runtime_intraday_live.py`
  - Intraday wiring coverage.
- `tests/web/test_today_risk_macro.py`
  - `/today` read model tests.
- `documents/repo_overview.md`
  - Architecture summary update after implementation.
- `documents/research_app/runbook.md`
  - Operator smoke command and degraded-mode notes.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Implementation progress and verification evidence.

## Backend Contract

Implement these persisted contracts with point-in-time fields on every source-derived record:

```python
@dataclass(frozen=True)
class MacroSnapshotRecord:
    macro_snapshot_id: str
    snapshot_time: datetime
    trade_date: date
    regime: str
    risk_budget_multiplier: float
    volatility_state: str | None
    rates_state: str | None
    liquidity_state: str | None
    blocked_strategy_tags: tuple[str, ...]
    invalidators: tuple[str, ...]
    source_freshness: dict[str, Any]
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class CalendarEventRecord:
    calendar_event_id: str
    event_key: str
    event_type: str
    ticker: str | None
    event_time: datetime
    published_at: datetime | None
    available_for_decision_at: datetime
    title: str
    severity_hint: str
    source: str
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class PortfolioEventRiskAssessmentRecord:
    portfolio_event_risk_assessment_id: str
    calendar_event_id: str | None
    portfolio_risk_snapshot_id: str | None
    ticker: str
    risk_source: str
    severity: str
    days_until_event: int | None
    affects_existing_position: bool
    affects_pending_trade: bool
    recommended_action: str
    rationale: str
    metadata_json: dict[str, Any]
```

Rules:

- `MacroSnapshotRecord` is one canonical snapshot per `trade_date` / `snapshot_time` / `source_set`.
- `CalendarEventRecord.event_key` is idempotent and source-stable, e.g. `earnings:AAPL:2026-07-24` or `macro:fomc:2026-06-17`.
- `PortfolioEventRiskAssessmentRecord` is portfolio-specific and decision-time-specific; it can point to a calendar event or represent a synthetic cluster/macro risk.
- All read methods must filter by `available_for_decision_at <= decision_time` to preserve point-in-time behavior.

## Task 1: Add The Schema And Pure Records

**Files:**

- Create: `src/trading/macro/context.py`
- Create: `src/trading/macro/__init__.py`
- Create: `src/trading/events/calendar.py`
- Create: `src/trading/events/risk.py`
- Create: `src/trading/events/__init__.py`
- Modify: `src/trading/risk/lookahead.py`
- Modify: `src/trading/risk/__init__.py`
- Modify: `src/db/models/trading.py`
- Modify: `src/db/models/__init__.py`
- Create: `alembic/versions/022_risk_macro_event_contract.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_macro_context.py`
- Test: `tests/trading/test_event_calendar.py`

- [ ] Step 1: Write failing schema tests for `macro_snapshots`, `macro_readthrough_events`, `calendar_events`, and `portfolio_event_risk_assessments`.
- [ ] Step 2: Write failing pure-contract tests for record validation and point-in-time fields.
- [ ] Step 3: Run `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_macro_context.py tests/trading/test_event_calendar.py -q`.
- [ ] Step 4: Add dataclasses and normalize the existing lookahead event assessment record so there is one shared representation.
- [ ] Step 5: Add ORM models with indexes on `trade_date`, `snapshot_time`, `ticker`, `event_time`, `available_for_decision_at`, `severity`, and `risk_source`.
- [ ] Step 6: Add the Alembic migration and verify SQL rendering with `source ~/.venv/bin/activate && alembic upgrade head --sql > /tmp/risk_macro_event_contract.sql`.
- [ ] Step 7: Run `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_macro_context.py tests/trading/test_event_calendar.py -q`.

Expected result: the DB can persist macro snapshots, event calendar rows, and portfolio event-risk assessments without relying on risk snapshot metadata blobs.

## Task 2: Add Repository Save/Load Methods

**Files:**

- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/trading/test_signal_source_sqlalchemy.py`

- [ ] Step 1: Write failing repository tests for `save_macro_snapshot`, `load_latest_macro_snapshot`, `save_calendar_events`, `load_calendar_events`, `save_portfolio_event_risk_assessments`, and `load_portfolio_event_risk_assessments`.
- [ ] Step 2: Implement in-memory repository methods for deterministic runtime tests.
- [ ] Step 3: Implement SQLAlchemy round-trips, preserving idempotency by natural keys.
- [ ] Step 4: Add a read helper that returns the latest decision-available macro/event/risk context for a `trade_date`.
- [ ] Step 5: Run `source ~/.venv/bin/activate && pytest tests/trading/test_sqlalchemy_repository.py tests/trading/test_signal_source_sqlalchemy.py -q`.

Expected result: runtimes and web routes can load current macro/event context from one repository boundary.

## Task 3: Implement Macro Snapshot Pipeline

**Files:**

- Create: `src/trading/macro/pipeline.py`
- Modify: `src/providers/global_context/types.py`
- Modify: `src/trading/signals/source_ingestion.py`
- Test: `tests/trading/test_macro_pipeline.py`
- Test: `tests/trading/test_provider_resilience.py`

- [ ] Step 1: Write failing tests for balanced, risk-off, degraded, and stale-source macro outputs.
- [ ] Step 2: Build `MacroSnapshotPipeline` using existing provider resilience, request telemetry, and `MacroIndicatorProvider`.
- [ ] Step 3: Implement deterministic fallback behavior when a provider is unavailable: persist a degraded snapshot with `regime="unavailable"` and explicit availability issues, not silent nulls.
- [ ] Step 4: Derive `risk_budget_multiplier`, `blocked_strategy_tags`, and `invalidators` from volatility/rates/liquidity inputs.
- [ ] Step 5: Persist provider freshness in `source_freshness`.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_macro_pipeline.py tests/trading/test_provider_resilience.py -q`.

Expected result: `/today` can show whether macro is genuinely neutral/risk-off/degraded, and RiskManager can size from the same snapshot.

## Task 4: Implement Event Calendar And Portfolio Event-Risk Pipeline

**Files:**

- Modify: `src/trading/events/calendar.py`
- Modify: `src/trading/events/risk.py`
- Modify: `src/trading/signals/event_news.py`
- Modify: `src/trading/signals/source_ingestion.py`
- Test: `tests/trading/test_event_calendar.py`
- Test: `tests/trading/test_event_news_signals.py`

- [ ] Step 1: Write failing tests that normalize earnings, Fed/macro, option-expiry, company-specific, and sector/theme read-through events.
- [ ] Step 2: Implement idempotent calendar event keys and dedupe by source, event type, ticker, and event time.
- [ ] Step 3: Build portfolio-aware risk assessments from open positions, pending candidates, option expiries, event severity, and days to event.
- [ ] Step 4: Include relevance metadata: `position_notional`, `candidate_score_id`, `option_strategy_id`, `relationship_context`, and `why_visible`.
- [ ] Step 5: Make low-relevance events persist but not appear in the default `/today` risk/macro read model.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_event_calendar.py tests/trading/test_event_news_signals.py -q`.

Expected result: event rows explain exactly why they matter to the current portfolio/candidate set.

## Task 5: Wire Pre-Open Runtime

**Files:**

- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/runtime/preopen_runner.py`
- Modify: `src/trading/runtime/preopen_risk.py`
- Modify: `src/trading/workflows/signal_snapshot.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_pipeline.py`

- [ ] Step 1: Write failing tests that pre-open stores a macro snapshot and event-risk assessments before final risk approval.
- [ ] Step 2: Add dependencies for `MacroSnapshotPipeline`, `EventCalendarPipeline`, and `PortfolioEventRiskAssessmentPipeline`.
- [ ] Step 3: Run macro/event refresh before building final signal snapshots so downstream summaries can reference canonical calendar rows.
- [ ] Step 4: Pass `MacroSnapshotRecord` and portfolio event-risk assessments into `LookaheadRiskWorkflowHelper`.
- [ ] Step 5: Persist linkage IDs in `PortfolioRiskIntent.metadata_json` and `RiskDecision.risk_context_json`.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_pipeline.py -q`.

Expected result: pre-open runs produce one auditable macro/event/risk context instead of per-ticker repeated summaries.

## Task 6: Wire Intraday Runtime

**Files:**

- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Modify: `src/trading/intraday/news_alerts.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_signals.py`
- Test: `tests/trading/test_news_alerts.py`

- [ ] Step 1: Write failing tests for scoped intraday refresh when a new high-severity event appears.
- [ ] Step 2: Reuse the latest pre-open macro snapshot unless freshness gates require refresh.
- [ ] Step 3: Persist intraday calendar deltas and event-risk assessment changes with `available_for_decision_at`.
- [ ] Step 4: Emit material change markers only when severity/action/relevance changes, not when the same event text repeats.
- [ ] Step 5: Pass updated macro/event context into intraday risk intent planning and rebalance approval.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_signals.py tests/trading/test_news_alerts.py -q`.

Expected result: intraday timeline entries show real deltas, not repeated `pre_open` text.

## Task 7: Connect RiskManager To Canonical Macro/Event Context

**Files:**

- Modify: `src/trading/risk/config.py`
- Modify: `src/trading/risk/planner.py`
- Modify: `src/trading/risk/manager.py`
- Modify: `src/trading/runtime/lookahead_risk.py`
- Test: `tests/trading/test_portfolio_hedge_planner.py`
- Test: `tests/trading/test_lookahead_risk.py`
- Test: `tests/trading/test_risk_manager.py`

- [ ] Step 1: Write failing tests where macro risk reduces size, an upcoming own event blocks a tactical open, and a portfolio cluster event generates a hedge intent.
- [ ] Step 2: Extend planner requests with `macro_snapshot` and persisted `event_assessments`.
- [ ] Step 3: Apply macro `risk_budget_multiplier` before final approval, while hard safety rails remain invariant.
- [ ] Step 4: Preserve clear `binding_constraints`, `top_risk_sources`, and `data_availability_issues` in risk decision metadata.
- [ ] Step 5: Run `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_hedge_planner.py tests/trading/test_lookahead_risk.py tests/trading/test_risk_manager.py -q`.

Expected result: risk approvals explain what macro/event/risk source changed the decision.

## Task 8: Add `/today` Backend Risk/Macro Read Model

**Files:**

- Create: `src/web/presenters/today_risk_macro.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/web/routers/today.py`
- Test: `tests/web/test_today_risk_macro.py`
- Test: `tests/web/test_today.py`

- [ ] Step 1: Write failing web tests for macro regime, event calendar cards, event-risk assessments, risk budget, blocked tags, binding constraints, and degraded availability.
- [ ] Step 2: Build a presenter that accepts repository-loaded macro/event/risk rows and emits one stable read model.
- [ ] Step 3: Replace `_build_risk_macro_summary` ad hoc logic with the presenter.
- [ ] Step 4: Replace `header.macro_regime` fallback from `PortfolioRiskSnapshot.metadata_json` with latest `MacroSnapshotRecord`.
- [ ] Step 5: Include compact `summary`, `macro`, `events`, `risk_sources`, `exposures`, `binding_constraints`, and `availability` sections.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_risk_macro.py tests/web/test_today.py -q`.

Expected result: the frontend can render risk/macro without querying raw DB tables or inventing fallback text.

## Task 9: Add DB Smoke, Docs, And Tracker Updates

**Files:**

- Create: `scripts/run_trading_macro_event_db_smoke.py`
- Modify: `documents/repo_overview.md`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] Step 1: Add a smoke script that writes and reloads one macro snapshot, two calendar events, two event-risk assessments, and the `/today` read model inputs.
- [ ] Step 2: Document degraded-mode behavior and required provider environment variables.
- [ ] Step 3: Update the progress tracker with implementation status and verification evidence after each completed task.
- [ ] Step 4: Run `source ~/.venv/bin/activate && python scripts/run_trading_macro_event_db_smoke.py --json`.
- [ ] Step 5: Run `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_macro_context.py tests/trading/test_macro_pipeline.py tests/trading/test_event_calendar.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_portfolio_hedge_planner.py tests/trading/test_lookahead_risk.py tests/trading/test_risk_manager.py tests/web/test_today_risk_macro.py tests/web/test_today.py -q`.
- [ ] Step 6: Run `git diff --check`.

Expected result: a real DB-backed smoke proves the backend contract is not just unit-tested.

## Acceptance Criteria

- Macro regime no longer shows `unavailable` when a valid macro snapshot exists.
- `Risk & Macro` has persisted macro, event, risk source, exposure, and availability data.
- `PortfolioHedgePlanner` and `RiskManager` consume the same macro/event context shown in `/today`.
- Intraday event changes are delta-based and point-in-time safe.
- Missing provider data is explicit and auditable, not silently collapsed into empty UI sections.
- All new tables have Alembic coverage and repository round-trip tests.
- Progress tracker is updated after implementation with test and smoke evidence.

## Non-Goals

- Do not redesign the frontend layout in this backend plan.
- Do not add a broad third-party event calendar vendor integration unless needed for the smoke; use existing provider abstractions and deterministic fixtures first.
- Do not change broker execution behavior.
- Do not loosen RiskManager hard safety rails to make macro/event output easier to pass.
