# Runtime Structure And Live Phase Roadmap Implementation Plan

> **Current path note:** the canonical runtime implementation now lives under `src/trading/runtime/`. Historical references in this slice to root-level files such as `src/trading/runtime_live.py` or `src/trading/runtime_dispatch.py` map to `src/trading/runtime/preopen.py` and `src/trading/runtime/dispatch.py`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mixed scheduler/fixture runtime shell with a phase-oriented trading runtime structure, keep the public scheduler/CLI surface stable, and migrate every scheduler-facing trading phase onto explicit live runtime modules.

**Architecture:** Treat `src/trading/runtime.py` as a thin facade only. Move scheduler-facing business logic into dedicated phase modules with explicit dependency builders, keep fixture behavior in smoke-only modules, and normalize every phase report to the same runtime contract. Preserve APScheduler job boundaries and the existing `run_job_phase(...)` / `scripts/run_trading_once.py --phase ...` operator surface while changing the internals underneath it.

**Tech Stack:** Python, SQLAlchemy ORM, Postgres JSONB, APScheduler, pytest, existing trading pipelines/workflows, Alpaca paper account sync, versioned prompt registry.

---

## Scope

This PR intentionally combines structural refactor and live-runtime migration for the trading scheduler layer. It does not redesign trading logic contracts, strategy catalogs, UI tabs, or deployment infrastructure. It is limited to runtime structure, phase assembly, public runtime semantics, and the request-loading/wiring needed to make every scheduler-facing phase stop relying on fixture paths.

Target end state for this PR:

1. `src/trading/runtime.py` is a dispatch-only facade for scheduler phases and smoke modes.
2. `preopen`, `manual_review`, `intraday_refresh`, `reflection`, and `strategy_evolution` each have their own live runtime module and entrypoint.
3. Fixture and smoke helpers live outside the scheduler-facing runtime path.
4. `run_job_phase(...)` and `scripts/run_trading_once.py --phase ...` stay backward compatible.
5. Post-close phases that lack prerequisites return `status="skipped"` with explicit reasons instead of fabricating fixture success.

Out of scope for this PR:

- changing phase names exposed to scheduler jobs or operators
- changing current prompt contracts or strategy-evolution logic semantics
- broad UI work
- new provider families beyond what current pipelines already consume
- replacing Docker Compose or deployment conventions

## Key Design Decisions To Preserve

- Keep `src/trading/runtime_live.py` as the `preopen` module name to avoid unnecessary churn in existing callers and tests.
- Do not turn `src/trading/runtime.py` into a package in this PR. Use sibling modules such as `runtime_intraday_live.py` and `runtime_smoke.py` instead.
- Scheduler-facing phases always call live runtimes. Fixture data is valid only for smoke/test helpers.
- `manual_review` is a scoped live-evaluation runtime, not an alias for the full preopen universe path.
- `intraday_refresh` includes both hourly signal refresh and the rebalance decision chain in one runtime path.
- `reflection` and `strategy_evolution` may return `status="skipped"` when same-day inputs are insufficient. Missing inputs are visible operational states, not hard failures by default.

## File Plan

### Create

- `src/trading/runtime_dispatch.py`
  Shared typed dispatcher helpers/constants if a facade split keeps `runtime.py` cleaner.
- `src/trading/runtime_smoke.py`
  Fixture-only smoke-mode handlers and fixture data builders moved out of `runtime.py`.
- `src/trading/runtime_manual_review_live.py`
  Live runtime assembly for the active manual-review phase.
- `src/trading/runtime_intraday_live.py`
  Live runtime assembly for hourly intraday refresh plus rebalance.
- `src/trading/runtime_reflection_live.py`
  Live request assembly and runtime orchestration for post-close reflection.
- `src/trading/runtime_strategy_evolution_live.py`
  Live request assembly and runtime orchestration for strategy evolution.
- `src/trading/runtime_support.py`
  Shared runtime bootstrap helpers for repositories, providers, prompt registries, paper-execution policy, and common report utilities.
- `tests/trading/test_runtime_dispatch.py`
  Focused coverage for facade dispatch and stable public runtime entrypoints.
- `tests/trading/test_runtime_manual_review_live.py`
  Focused orchestration tests for the manual-review live runtime.
- `tests/trading/test_runtime_intraday_live.py`
  Focused orchestration tests for the intraday live runtime.
- `tests/trading/test_runtime_reflection_live.py`
  Focused request-assembly/orchestration tests for the reflection live runtime.
- `tests/trading/test_runtime_strategy_evolution_live.py`
  Focused request-assembly/orchestration tests for the strategy-evolution live runtime.

### Modify

- `src/trading/runtime.py`
  Strip it down to exported constants plus stable `run_job_phase(...)` / `run_smoke_mode(...)` facade functions.
- `src/trading/runtime_live.py`
  Keep the preopen runtime but extract reusable bootstrap/report helpers into `runtime_support.py` as needed.
- `scripts/run_trading_once.py`
  Preserve the current `--phase` operator surface while delegating to the new runtime structure.
- `scripts/run_trading_smoke_test.py`
  Point smoke-mode execution at the new smoke-only module.
- `src/scheduler/jobs/*.py`
  Only if imports or log expectations need tiny adjustments after the facade split.
- `src/trading/manual_review/sqlalchemy.py`
  Extend DB-backed request updates if the manual-review live runtime needs explicit evaluation status writes.
- `src/trading/repositories/sqlalchemy.py`
  Add any repository load/save helpers needed for phase request assembly or normalized status reporting.
- `src/trading/workflows/paper_execution.py`
  Only if runtime execution policy reveals missing interfaces for intraday/manual-review paths.
- `documents/research_app/runbook.md`
  Document the stable operator commands plus new live/skipped runtime semantics.
- `documents/repo_overview.md`
  Update the architecture summary once the runtime split lands.

## Runtime Contract Changes

Public runtime surface stays stable:

- `TRADING_JOB_PHASES`
- `AVAILABLE_SMOKE_MODES`
- `run_job_phase(phase: str) -> dict[str, Any]`
- `run_smoke_mode(mode: str) -> dict[str, Any]`
- `python scripts/run_trading_once.py --phase <phase>`

New live entrypoints are added but not required for operators:

- `run_live_manual_review_once(...)`
- `run_live_intraday_refresh_once(...)`
- `run_live_reflection_once(...)`
- `run_live_strategy_evolution_once(...)`

Every scheduler-facing phase report should normalize onto:

- `status`: `passed`, `failed`, or `skipped`
- `phase`
- `as_of`
- `summary`
- `execution` only when paper-order execution is relevant

## Task 1: Split Facade From Runtime Logic

**Files:**
- Create: `src/trading/runtime_smoke.py`
- Create: `tests/trading/test_runtime_dispatch.py`
- Modify: `src/trading/runtime.py`
- Modify: `scripts/run_trading_smoke_test.py`

- [x] Write failing dispatch tests that prove `run_job_phase(...)` and `run_smoke_mode(...)` still expose the same public contract while delegating to external handlers.
- [x] Run the new focused dispatch tests and confirm they fail because the runtime facade still contains inline logic.
- [x] Move smoke-only fixture handlers, fixture builders, and fake helper data out of `src/trading/runtime.py` into `src/trading/runtime_smoke.py`.
- [x] Reduce `src/trading/runtime.py` to exported constants and stable dispatch functions only.
- [x] Keep all current smoke-mode names unchanged.
- [x] Re-run the focused dispatch tests and confirm they pass.

## Task 2: Extract Shared Live Runtime Support

**Files:**
- Create: `src/trading/runtime_support.py`
- Modify: `src/trading/runtime_live.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_runtime_dispatch.py`

- [x] Write failing tests that lock the preopen live runtime public behavior before extracting shared helpers.
- [x] Run the preopen runtime tests and confirm the expected RED state for any new helper boundaries.
- [x] Extract shared bootstrap utilities only where multiple live phase modules will reuse them:
  - session-scoped repository/provider construction
  - prompt-registry/model bootstrap
  - standardized runtime report helpers
  - optional paper-execution policy helpers
- [x] Keep `run_live_preopen_once(...)` and `build_live_preopen_dependencies(...)` externally compatible.
- [x] Re-run the focused preopen and dispatch tests and confirm they pass.

## Task 3: Add The Live Manual Review Runtime

**Files:**
- Create: `src/trading/runtime_manual_review_live.py`
- Modify: `src/trading/manual_review/sqlalchemy.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime.py`
- Test: `tests/trading/test_runtime_manual_review_live.py`

- [x] Write failing orchestration tests for a live manual-review runtime that:
  - loads active manual requests from Postgres
  - evaluates only requested tickers
  - respects `review_only` vs `paper_trade_eligible`
  - records evaluation metadata/status back to `manual_ticker_requests`
- [x] Run the focused manual-review runtime tests and confirm failure for the expected missing module/API reasons.
- [x] Implement a dedicated live manual-review runtime that reuses the same signal, strategy, trading-decision, sizing, and risk path as preopen, but with request-scoped ticker loading instead of a full universe scan.
- [x] Keep scheduler-facing `run_job_phase("manual_review")` stable while routing it to the new runtime.
- [x] Re-run the focused manual-review runtime tests and confirm they pass.

## Task 4: Add The Live Intraday Refresh And Rebalance Runtime

**Files:**
- Create: `src/trading/runtime_intraday_live.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/workflows/paper_execution.py` only if interface gaps are discovered
- Modify: `src/trading/runtime.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [x] Write failing orchestration tests for a live intraday runtime that:
  - loads the intraday ticker scope from open positions, same-day trades/open orders, top morning candidates, active manual requests, and relevant option positions/exposures
  - loads each ticker’s preopen baseline and prior intraday snapshot
  - persists `intraday_signal_scans`, `intraday_signal_snapshots`, and `news_alerts`
  - runs `IntradayRebalancePipeline`
  - flows rebalance outputs through sizing/risk and optional paper execution
- [x] Run the focused intraday runtime tests and confirm failure for the expected missing assembly logic.
- [x] Implement the live intraday runtime with dry-run execution by default.
- [x] Remove fixture-based scheduler behavior so `run_job_phase("intraday_refresh")` always uses the live path.
- [x] Preserve `intraday_refresh_fixture` as a smoke mode only.
- [x] Re-run the focused intraday runtime tests and confirm they pass.

## Task 5: Add The Live Reflection Runtime

**Files:**
- Create: `src/trading/runtime_reflection_live.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime.py`
- Test: `tests/trading/test_runtime_reflection_live.py`

- [x] Write failing tests for reflection request assembly from persisted same-trade-date artifacts:
  - portfolio outcome and portfolio snapshots
  - morning macro snapshot
  - strategy candidates and trading decisions
  - manual requests
  - intraday alerts and rebalance decisions
  - paper orders/executions
  - risk snapshots/exposures
  - candidate outcome evaluations
  - option artifacts and learning factors used
- [x] Run the focused reflection runtime tests and confirm failure because no live request-assembly layer exists yet.
- [x] Implement the live reflection runtime and request builder.
- [x] Return `status="skipped"` with explicit reasons when minimum required post-close inputs are unavailable.
- [x] Keep scheduler-facing `run_job_phase("reflection")` stable while routing it to the new live runtime.
- [x] Re-run the focused reflection runtime tests and confirm they pass.

## Task 6: Add The Live Strategy Evolution Runtime

**Files:**
- Create: `src/trading/runtime_strategy_evolution_live.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime.py`
- Test: `tests/trading/test_runtime_strategy_evolution_live.py`

- [x] Write failing tests for strategy-evolution request assembly from persisted reflection outputs, learning factors, rejected candidates, and outcome evaluations.
- [x] Run the focused strategy-evolution runtime tests and confirm failure because no live request builder exists yet.
- [x] Implement the live strategy-evolution runtime and request builder.
- [x] Return `status="skipped"` when same-day reflection or other minimum prerequisites are absent.
- [x] Keep scheduler-facing `run_job_phase("strategy_evolution")` stable while routing it to the new live runtime.
- [x] Re-run the focused strategy-evolution runtime tests and confirm they pass.

## Task 7: Normalize CLI, Scheduler, And Reporting Semantics

**Files:**
- Modify: `scripts/run_trading_once.py`
- Modify: `src/scheduler/jobs/trading_preopen_job.py`
- Modify: `src/scheduler/jobs/manual_ticker_review_job.py`
- Modify: `src/scheduler/jobs/intraday_signal_refresh_job.py`
- Modify: `src/scheduler/jobs/trading_reflection_job.py`
- Modify: `src/scheduler/jobs/strategy_evolution_job.py`
- Test: `tests/scripts/test_run_trading_once.py`
- Test: `tests/test_scheduler_jobs.py`

- [x] Write failing tests that lock the existing public CLI/scheduler contract while allowing `skipped` runtime results.
- [x] Run the focused CLI/scheduler tests and confirm the expected RED state if result semantics changed.
- [x] Ensure every scheduler job still calls `run_job_phase(...)` with the same phase strings.
- [x] Make `scripts/run_trading_once.py` continue to accept the existing `--phase` surface, with only minimal additions if a phase needs an explicit execution flag.
- [x] Make sure `status="skipped"` is surfaced clearly in JSON output and logs without pretending the phase passed.
- [x] Re-run the focused CLI/scheduler tests and confirm they pass.

## Task 8: Update Operational Docs And Final Verification

**Files:**
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [x] Update the runbook to clarify that scheduler-facing trading phases now use live runtimes, fixture paths are smoke-only, and post-close phases can return `skipped` when prerequisites are absent.
- [x] Update `documents/repo_overview.md` to reflect the new phase-oriented runtime structure.
- [x] Append the implementation results and verification commands to the progress tracker after the code lands.
- [x] Run the focused runtime test files, the scheduler/CLI tests, the relevant broader trading suites, and `git diff --check`.
- [ ] Run at least one opt-in live smoke for `preopen` and one for `intraday_refresh`, and record exact commands/results in the tracker.

## Verification Expectations

Targeted verification should include at least:

- `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_dispatch.py tests/trading/test_runtime_live.py tests/trading/test_runtime_manual_review_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_runtime_reflection_live.py tests/trading/test_runtime_strategy_evolution_live.py -q`
- `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_once.py tests/test_scheduler_jobs.py tests/scripts/test_run_trading_smoke_test.py -q`

Broader relevant verification should include at least:

- `source ~/.venv/bin/activate && pytest tests/trading tests/db/test_trading_models.py -q`

Operational verification should include:

- `source ~/.venv/bin/activate && python scripts/run_trading_once.py --phase preopen --mode live-preopen --json`
- `source ~/.venv/bin/activate && python scripts/run_trading_once.py --phase intraday_refresh --json`
- `source ~/.venv/bin/activate && python scripts/run_trading_smoke_test.py --mode intraday_refresh_fixture --json`
- `git diff --check`

## Acceptance Criteria

- Scheduler-facing trading phases no longer depend on fixture-only runtime paths.
- `src/trading/runtime.py` is small and dispatch-only.
- Every phase has an explicit live runtime entrypoint and dependency builder.
- CLI and scheduler public phase names remain unchanged.
- Missing same-day prerequisites for reflection/strategy-evolution surface as `skipped`, not fake fixture success.
- Smoke modes still work and remain fixture-safe.
