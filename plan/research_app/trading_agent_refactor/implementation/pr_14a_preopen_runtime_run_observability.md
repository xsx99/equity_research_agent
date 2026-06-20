# Preopen Runtime Run Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist normalized live preopen runtime reports and surface the latest preopen funnel directly in `/today` `Overview` so operators can see whether the morning run executed and where it stopped.

**Architecture:** Add one thin persisted runtime-run contract in Postgres, save preopen runtime reports from the session-owning live entrypoint, and read the latest same-trade-date preopen row through the existing `/today` route -> presenter -> Jinja pipeline. Keep `LivePreopenRuntime.run()` focused on orchestration and report generation; do not make the `Overview` page re-derive preopen funnel state from `TradingDecision`, `CandidateScore`, or other downstream artifact tables.

**Tech Stack:** Python, SQLAlchemy ORM, Alembic, Postgres JSONB, FastAPI, Jinja2, pytest, existing live preopen runtime/report helpers.

---

## Scope

This slice is intentionally narrow:

1. Add a generic persisted trading-runtime run table that can store normalized phase reports.
2. Wire only the scheduler-facing live `preopen` path to write that table.
3. Read only the latest `preopen` row into `/today` `Overview`.
4. Render a compact operator-facing `Latest Preopen Run` block with status, execution mode, timestamps, and funnel counts.

Out of scope for this slice:

- wiring `manual_review`, `intraday_refresh`, `reflection`, or `strategy_evolution` to the new table
- redesigning scheduler job logging semantics
- replacing the existing `Current Session Summary`, `Needs Review`, or `System Issues` blocks
- reconstructing funnel state by querying `candidate_scores`, `risk_decisions`, or `trading_decisions`
- backfilling historical runtime runs

## Problem This Plan Fixes

Real live smoke showed that the preopen runtime can complete and still produce no decisions, but `/today` `Overview` cannot currently show that distinction. Today only reads result tables such as `PortfolioSnapshot`, `PortfolioRiskSnapshot`, `TradingDecision`, and `CandidateScore`, so it loses the runtime-level funnel summary:

- `manual_request_count`
- `signal_snapshot_count`
- `candidate_count`
- `classification_count`
- `risk_decision_count`
- `trading_decision_count`
- `execution.mode`
- `orders_submitted`

Without a persisted runtime-run record, operators can only infer what happened from partial downstream artifacts, which is unreliable when the run stops before risk approval or trading decision generation.

## Key Decisions To Preserve

- Persist normalized runtime reports at the session-owning live preopen entrypoint in `src/trading/runtime/preopen.py`, not inside `LivePreopenRuntime.run()`.
- Keep the new table phase-agnostic (`phase`, `status`, `summary_json`, `execution_json`) so later phases can reuse it, but do not wire those phases in this slice.
- `/today` `Overview` must treat the persisted runtime row as the source of truth for preopen funnel state. Do not reconstruct the funnel from downstream artifact tables.
- If no persisted preopen row exists for the current trade date, `Overview` must show an explicit unavailable/empty state rather than optimistic placeholder copy.
- Persist both successful returned reports and a minimal `failed` row when the session-owning live preopen entrypoint raises before returning a normalized report.

## File Plan

### Create

- `alembic/versions/027_trading_runtime_runs.py`
  Add the new persisted runtime-run table and indexes.

### Modify

- `src/db/models/trading.py`
  Add the `TradingRuntimeRun` ORM model.
- `src/trading/repositories/sqlalchemy.py`
  Add `save_runtime_run(...)` and `load_latest_runtime_run(...)`.
- `src/trading/runtime/preopen.py`
  Persist successful and failed preopen runtime reports from the session-owning live entrypoint.
- `src/web/routers/today.py`
  Load the latest persisted `preopen` runtime row and pass it into the overview presenter.
- `src/web/presenters/today_overview.py`
  Build a compact `latest_preopen_run` read model for the operator surface.
- `src/templates/today.html`
  Render the `Latest Preopen Run` block in `Overview`.
- `tests/db/test_trading_models.py`
  Add ORM/index coverage for the new runtime-run model.
- `tests/trading/test_sqlalchemy_repository.py`
  Add save/load coverage for persisted runtime runs.
- `tests/trading/test_runtime_live.py`
  Add live entrypoint persistence coverage for success and failure cases.
- `tests/web/test_today_overview.py`
  Add presenter coverage for the new `Latest Preopen Run` surface.
- `tests/web/test_today.py`
  Add route/template coverage for rendering the block and the empty state.
- `documents/repo_overview.md`
  Update after implementation to describe the persisted runtime-run contract and `Overview` dependency.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  Update after implementation with verification evidence.

## Runtime Run Contract

Persist one row per runtime invocation with this minimum shape:

```python
{
    "phase": "preopen",
    "status": "passed" | "failed" | "skipped",
    "trade_date": date(2026, 6, 20),
    "as_of": "2026-06-20T03:48:49.802518+00:00",
    "started_at": "2026-06-20T03:48:49.802518+00:00",
    "completed_at": "2026-06-20T03:49:26.130000+00:00",
    "summary_json": {
        "manual_request_count": 1,
        "signal_snapshot_count": 17,
        "candidate_count": 150,
        "classification_count": 0,
        "risk_decision_count": 0,
        "trading_decision_count": 0,
    },
    "execution_json": {
        "mode": "dry_run",
        "orders_submitted": 0,
        "option_orders_submitted": 0,
    },
    "metadata_json": {
        "source": "run_live_preopen_once",
        "report_version": "v1",
    },
}
```

For `failed` rows, keep `summary_json` intentionally small:

```python
{
    "reasons": ["paper_execution_workflow_not_configured"],
}
```

The table must support:

- latest row by `phase`
- latest row by `phase + trade_date`
- descending recency by `completed_at`

## Task 1: Add The Persisted Runtime-Run Contract

**Files:**

- Create: `alembic/versions/027_trading_runtime_runs.py`
- Modify: `src/db/models/trading.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`

- [ ] Step 1: Write failing ORM and repository tests for a `TradingRuntimeRun` model plus `save_runtime_run(...)` / `load_latest_runtime_run(...)`.
- [ ] Step 2: Run `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py -q` and confirm RED for the missing model/repository API.
- [ ] Step 3: Add the `TradingRuntimeRun` ORM model in `src/db/models/trading.py` with `phase`, `status`, `trade_date`, `as_of`, `started_at`, `completed_at`, `summary_json`, `execution_json`, and `metadata_json`.
- [ ] Step 4: Add Alembic revision `027_trading_runtime_runs.py` with indexes that support latest-by-phase and latest-by-phase-trade-date queries.
- [ ] Step 5: Implement `save_runtime_run(...)` and `load_latest_runtime_run(...)` in `src/trading/repositories/sqlalchemy.py`. Return a plain serialized dict from `load_latest_runtime_run(...)` to avoid introducing a new domain-record layer for this one read path.
- [ ] Step 6: Re-run `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py -q` and confirm GREEN.

Expected result: the codebase can durably store and reload normalized scheduler/runtime reports without involving `/today` yet.

## Task 2: Persist Successful And Failed Live Preopen Reports

**Files:**

- Modify: `src/trading/runtime/preopen.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Step 1: Write failing runtime tests that prove `run_live_preopen_once(...)` persists a `passed` row on success and a `failed` row with reasons on raised exceptions, while `LivePreopenRuntime.run()` itself stays unchanged.
- [ ] Step 2: Run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py -q` and confirm RED for the missing persistence behavior.
- [ ] Step 3: Keep `LivePreopenRuntime.run()` pure and unchanged; add persistence only in the session-owning `run_preopen_once(...)` / `run_live_preopen_once(...)` path in `src/trading/runtime/preopen.py`.
- [ ] Step 4: On success, save the normalized returned report plus execution payload and commit before returning.
- [ ] Step 5: On exception, roll back the active transaction, save a minimal `failed` runtime row with `reasons` and `exception_type`, commit that failure row, and then re-raise the original exception.
- [ ] Step 6: Re-run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py -q` and confirm GREEN.

Expected result: the real scheduler-facing preopen path leaves behind one durable runtime row whether the run finishes cleanly or dies before returning a report.

## Task 3: Load The Latest Persisted Preopen Run Into `/today`

**Files:**

- Modify: `src/web/routers/today.py`
- Test: `tests/web/test_today.py`

- [ ] Step 1: Write failing route tests for `/today` loading the latest persisted `preopen` runtime row for the current trade date and exposing an explicit empty state when no row exists.
- [ ] Step 2: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q` and confirm RED for the missing route data.
- [ ] Step 3: Add a small helper in `src/web/routers/today.py` that asks `SqlAlchemyTradingRepository.load_latest_runtime_run(phase="preopen", trade_date=<current trade date>)` for the current session when SQLAlchemy is available.
- [ ] Step 4: Pass that serialized row into `build_today_overview(...)` as a dedicated argument such as `latest_preopen_run`.
- [ ] Step 5: Keep the route fallback conservative: when no SQLAlchemy session or no row exists, pass `None` and let the presenter render the empty state.
- [ ] Step 6: Re-run `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q` and confirm GREEN.

Expected result: `/today` has direct access to the latest same-day preopen runtime report without reverse-engineering it from downstream trading artifacts.

## Task 4: Build And Render The `Latest Preopen Run` Overview Surface

**Files:**

- Modify: `src/web/presenters/today_overview.py`
- Modify: `src/templates/today.html`
- Test: `tests/web/test_today_overview.py`
- Test: `tests/web/test_today.py`

- [ ] Step 1: Write failing presenter and route/template tests for a new `Latest Preopen Run` block that shows `status`, `as_of`, `execution mode`, and the key funnel counts.
- [ ] Step 2: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_overview.py tests/web/test_today.py -q` and confirm RED for the missing surface.
- [ ] Step 3: Extend `build_today_overview(...)` so it emits a `latest_preopen_run` read model with:
  - `status_label`
  - `as_of_label`
  - `completed_at_label`
  - `execution_mode_label`
  - `headline`
  - `summary_tiles`
  - `empty_copy`
- [ ] Step 4: Derive `headline` from the persisted funnel counts instead of inventing optimistic prose. Example outcomes: “Signals built, but no candidates were selected.”, “Candidates scored, but none reached risk approval.”, “Trading decisions were generated in dry-run mode.”
- [ ] Step 5: Render the block in `src/templates/today.html` inside `Overview`, above the existing command-center tiles so operators see latest preopen status before `Needs Review` / `Open Positions` / `System Issues`.
- [ ] Step 6: Re-run `source ~/.venv/bin/activate && pytest tests/web/test_today_overview.py tests/web/test_today.py -q` and confirm GREEN.

Expected result: an operator can answer “did preopen run, and where did it stop?” from one compact `Overview` block.

## Task 5: Final Verification, Smoke, And Documentation

**Files:**

- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] Step 1: Run the focused verification suite:
  - `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_runtime_live.py tests/web/test_today_overview.py tests/web/test_today.py -q`
- [ ] Step 2: Run `source ~/.venv/bin/activate && git diff --check`.
- [ ] Step 3: Run the real live smoke path with a stable ticker, for example:
  - `source ~/.venv/bin/activate && python scripts/run_trading_live_preopen_order_smoke.py --ticker NVDA --dry-run --json`
- [ ] Step 4: Confirm the smoke created or updated a persisted `preopen` runtime row and that the returned JSON still reports the same funnel counts as the stored row.
- [ ] Step 5: Start the local app and verify `Overview` renders the new block from persisted data:
  - `source ~/.venv/bin/activate && uvicorn src.app:app --host 127.0.0.1 --port 8000`
  - `curl -s 'http://127.0.0.1:8000/today?tab=overview'`
- [ ] Step 6: Update `documents/repo_overview.md` and `plan/research_app/trading_agent_refactor/progress_tracker.md` with the new persisted runtime-run contract, `Overview` dependency, verification commands, and any remaining live-provider limitations discovered during smoke.

Expected result: the slice is verified both as a unit-tested code change and as a real operator-facing live smoke path.
