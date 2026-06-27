# Manual Review Execution And Audit Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve `paper_trade_eligible` as a real paper-execution path for manual review while making every active request auditable end-to-end from request creation through signal snapshot, decision, intraday follow-up, and paper-order state.

**Architecture:** Keep manual review on the same signal, strategy, risk, and paper-execution stack as preopen, but close the contract gaps around request identity, execution reachability, intraday carry-forward, and `/today` audit loaders. Enforce one active request per ticker, keep scheduler defaults dry-run, expose explicit operator execution entrypoints, and provide a backend request-audit read model that the UI plan can consume without template-side joins.

**Tech Stack:** Python, pytest, SQLAlchemy ORM, Alembic, FastAPI route loaders, existing trading runtimes, existing smoke fixtures.

---

## Required Pre-Read

- `documents/general_instructions.md`
- `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- `plan/research_app/trading_agent_refactor/design/06_paper_trading_and_risk.md`
- `plan/research_app/trading_agent_refactor/design/09_ui_error_testing_delivery.md`
- `docs/superpowers/specs/2026-06-14-live-option-execution-wiring-design.md`
- `docs/superpowers/plans/2026-06-15-today-dashboard-operator-ui.md`
- `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Scope Guardrails

- Preserve `review_only`: never execute.
- Preserve `paper_trade_eligible`: may execute paper stock orders only after the normal strategy, trading-decision, sizing, and risk gates pass.
- Keep manual-review option execution out of scope. The option design still marks that as future work.
- Keep scheduler-facing defaults dry-run unless an explicit execution surface is invoked.
- Do not redesign `/today` layout here; this plan only provides the backend request-audit contract the UI plan will render.

## Current Gap

- `manual_review` runtime has an internal `execute_paper_orders` switch but no public manual-review-specific CLI/operator path, so `paper_trade_eligible` is not practically reachable.
- Active manual requests are not unique by ticker. The current signal pipeline collapses requests into a `ticker -> request` map, so duplicate active requests silently lose evaluation updates.
- Intraday refresh includes active manual-review tickers in scope, but the request identity and mode are not carried through to intraday trading decisions or execution guardrails.
- `/today` only shows `latest_result_status` for manual requests. It does not expose `last_evaluated_at`, `latest_signal_snapshot_id`, latest linked trading decision, or latest order/execution state.
- `/today` cannot clearly distinguish model intent from execution path, so an operator cannot tell whether a request is still pending, risk-blocked, eligible but not submitted, submitted with no fill, or actually executed.
- Dismiss/create logic is route-local and not enforcing the same lifecycle contract as the runtime-side manual-review services.

## File Map

- `src/db/models/trading.py`
  - Add any DB-level lifecycle/index support needed for one-active-request-per-ticker and richer request audit fields.
- `alembic/versions/023_manual_review_execution_audit_contract.py`
  - Add partial uniqueness or cleanup migration steps if the DB contract needs tightening.
- `src/trading/manual_review/requests.py`
  - Keep the in-memory request contract aligned with the DB-backed semantics.
- `src/trading/manual_review/sqlalchemy.py`
  - Add DB-backed create/replace, dismiss/cancel, active-request uniqueness, and request-audit loading helpers.
- `src/trading/workflows/signal_snapshot.py`
  - Stop silently dropping duplicate active requests; keep request identity deterministic.
- `src/trading/runtime/manual_review.py`
  - Tighten runtime reporting and explicit execution policy for manual-review runs.
- `src/trading/runtime/dispatch.py`
  - Keep scheduler/default dispatch stable while allowing an explicit operator-facing manual-review runtime path.
- `scripts/run_trading_once.py`
  - Expose a manual-review live mode with explicit execution opt-in.
- `src/trading/repositories/sqlalchemy.py`
  - Add a manual-review request audit loader for `/today`, including operator-facing decision/execution-path state fields.
- `src/trading/runtime/intraday_refresh_dependencies.py`
  - Carry manual-request audit identity into intraday request contexts.
- `src/trading/intraday/rebalance.py`
  - Preserve `manual_request_id` and `manual_request_mode` in intraday decisions and apply the same `review_only` / `paper_trade_eligible` execution guardrails.
- `src/web/routers/today.py`
  - Load the backend manual-review audit contract without redesigning the template here.
- `src/trading/runtime/smoke_fixture_modes.py`
  - Add a fixture-backed executable manual-review smoke path.
- `tests/db/test_trading_models.py`
  - Constraint/index coverage if the DB contract changes.
- `tests/trading/test_manual_requests.py`
  - In-memory lifecycle semantics.
- `tests/trading/test_manual_request_sqlalchemy.py`
  - DB-backed create/replace/dismiss/audit semantics.
- `tests/trading/test_runtime_manual_review_live.py`
  - Manual-review execution reachability and reporting.
- `tests/trading/test_runtime_intraday_live.py`
  - Intraday request-context carry-through.
- `tests/trading/test_intraday_rebalance.py`
  - Intraday execution guardrail coverage for manual-review requests.
- `tests/scripts/test_run_trading_once.py`
  - CLI execution-policy surface.
- `tests/web/test_today.py`
  - Backend request-audit loader contract coverage.
- `tests/scripts/test_run_trading_smoke_test.py`
  - Fixture-backed smoke registration/contract.
- `documents/research_app/runbook.md`
  - Operator execution and verification commands.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Planning and implementation status.

## Backend Contract

Manual review should expose one stable audit row per active request with enough linkage for the UI to render either a live drill-down path or an explicit degraded state:

```python
@dataclass(frozen=True)
class ManualReviewAuditRow:
    manual_ticker_request_id: str
    ticker: str
    reason: str
    mode: str
    status: str
    created_at: datetime
    last_evaluated_at: datetime | None
    latest_result_status: str | None
    latest_signal_snapshot_id: str | None
    latest_trading_decision_id: str | None
    latest_decision_action: str | None
    latest_risk_outcome: str | None
    latest_order_status: str | None
    latest_execution_status: str | None
    latest_execution_time: datetime | None
    execution_path_state: str
    latest_block_reason: str | None
    linkage_state: str
```

Rules:

- There must be at most one `active` manual request per normalized ticker.
- Re-pinning the same ticker replaces the active request deterministically instead of creating a second active row that the pipeline silently ignores.
- `review_only` requests may generate signal snapshots and trading decisions, but never paper orders.
- `paper_trade_eligible` requests may create paper stock orders only through the normal decision/risk pipeline.
- Intraday follow-up decisions for active manual-review tickers must preserve `manual_request_id` and `manual_request_mode`.
- If a request has not yet reached snapshot/decision/order linkage, the backend should expose `linkage_state` explicitly rather than relying on UI inference.
- The backend must distinguish model intent from execution outcome, e.g. `enter_long + risk_blocked`, `enter_long + eligible_no_order`, or `enter_long + order_submitted`, without asking the template to infer it from missing joins.
- If no order exists, `execution_path_state` and `latest_block_reason` must explain whether the request is still pending evaluation, blocked by risk, dry-run only, or eligible but not yet submitted.

## Task 1: Enforce One Active Manual Request Per Ticker

**Files:**

- Modify: `src/trading/manual_review/requests.py`
- Modify: `src/trading/manual_review/sqlalchemy.py`
- Modify: `src/trading/workflows/signal_snapshot.py`
- Modify: `src/web/routers/today.py`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/023_manual_review_execution_audit_contract.py`
- Test: `tests/trading/test_manual_requests.py`
- Test: `tests/trading/test_manual_request_sqlalchemy.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/web/test_today.py`

- [x] Step 1: Write failing tests for duplicate active requests on the same ticker and for the current signal pipeline dropping one request silently.
- [x] Step 2: Choose and codify one replacement rule: when the user re-pins the same ticker, cancel the previous active request and create a fresh active request with the new reason/mode.
- [x] Step 3: If the DB contract changes, add a migration path that cancels older duplicate active rows before adding a one-active-request-per-ticker constraint or partial unique index.
- [x] Step 4: Move DB-backed create/replace and dismiss semantics behind `SQLAlchemyManualTickerRequestService` so the route is not hand-rolling lifecycle transitions.
- [x] Step 5: Update `SignalPipeline` so manual-request identity remains deterministic and no active request is silently ignored.
- [x] Step 6: Run `source ~/.venv/bin/activate && pytest tests/trading/test_manual_requests.py tests/trading/test_manual_request_sqlalchemy.py tests/db/test_trading_models.py tests/web/test_today.py -q`.

Expected result: each ticker has at most one active request, and every active request receives deterministic evaluation updates.

## Task 2: Expose An Explicit Manual-Review Execution Surface

**Files:**

- Modify: `src/trading/runtime/manual_review.py`
- Modify: `src/trading/runtime/dispatch.py`
- Modify: `scripts/run_trading_once.py`
- Test: `tests/trading/test_runtime_manual_review_live.py`
- Test: `tests/scripts/test_run_trading_once.py`

- [x] Step 1: Write failing tests for a dedicated manual-review live mode that can run in dry-run or `--execute-paper-orders` mode without changing scheduler defaults.
- [x] Step 2: Keep `run_job_phase("manual_review")` dry-run by default, but expose an explicit operator path such as `--mode live-manual-review --phase manual_review`.
- [x] Step 3: Extend the runtime report so manual-review execution shows counts that matter operationally, such as request counts, risk-blocked requests, eligible-no-order requests, orders submitted, and request-mode breakdown.
- [x] Step 4: Keep manual-review option execution out of scope and report zero option-order submissions explicitly if a unified execution report shape is needed.
- [x] Step 5: Run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_manual_review_live.py tests/scripts/test_run_trading_once.py -q`.

Expected result: operators can explicitly execute `paper_trade_eligible` manual-review requests without changing the default scheduler behavior.

## Task 3: Preserve Manual-Request Identity Through Intraday Follow-Up

**Files:**

- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/intraday/rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_rebalance.py`

- [x] Step 1: Write failing tests showing that active manual-review tickers in intraday scope currently lose `manual_request_id` and `manual_request_mode`.
- [x] Step 2: Extend intraday request contexts to carry the active request ID, mode, and any latest snapshot/decision linkage needed for auditability.
- [x] Step 3: Make intraday-created `TradingDecisionRecord`s preserve `manual_request_id` when the ticker is being followed because of an active manual request.
- [x] Step 4: Apply the same execution policy intraday: `review_only` stays non-executable, `paper_trade_eligible` may execute only if the normal intraday gates pass.
- [x] Step 5: Run `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py -q`.

Expected result: intraday refresh no longer severs manual-review lineage or accidentally bypasses request-mode execution rules.

## Task 4: Add A Backend Manual-Review Audit Loader For `/today`

**Files:**

- Modify: `src/trading/manual_review/sqlalchemy.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/web/routers/today.py`
- Test: `tests/trading/test_manual_request_sqlalchemy.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/web/test_today.py`

- [x] Step 1: Write failing tests for a backend audit row that exposes `last_evaluated_at`, `latest_signal_snapshot_id`, latest linked trading decision ID, `latest_decision_action`, `latest_risk_outcome`, and latest order/execution state.
- [x] Step 2: Implement a repository/service loader that joins manual requests to their latest decision, risk, and order artifacts by `manual_request_id` instead of asking the template to infer linkage.
- [x] Step 3: Return explicit `linkage_state` and `execution_path_state` values such as `pending_evaluation`, `snapshot_only`, `risk_blocked`, `eligible_no_order`, `order_submitted`, or `filled` when the chain is incomplete or stopped.
- [x] Step 4: Wire `/today` to consume that backend loader while keeping template redesign in the UI plan.
- [x] Step 5: Run `source ~/.venv/bin/activate && pytest tests/trading/test_manual_request_sqlalchemy.py tests/trading/test_sqlalchemy_repository.py tests/web/test_today.py -q`.

Expected result: the UI plan gets one stable backend audit contract for manual-review cards and drill-down links, including a clear model-intent-vs-execution-path summary.

## Task 5: Add Standalone Smoke Coverage And Operator Docs

**Files:**

- Modify: `src/trading/runtime/smoke_fixture_modes.py`
- Modify: `src/trading/runtime/smoke.py`
- Modify: `tests/scripts/test_run_trading_smoke_test.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [x] Step 1: Write a failing smoke test for a fixture-backed `paper_trade_eligible` manual-review path that submits one paper stock order.
- [x] Step 2: Add a standalone smoke mode such as `manual_review_execution_fixture` so the executable path can be verified without live providers.
- [x] Step 3: Document the operator commands for dry-run and explicit execution, plus what to inspect in `/today` after the run.
- [x] Step 4: Update the progress tracker with implementation status and verification evidence after each completed task.
- [x] Step 5: Run `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_smoke_test.py tests/trading/test_runtime_manual_review_live.py tests/scripts/test_run_trading_once.py -q`.
- [x] Step 6: Run `git diff --check`.

Expected result: manual-review execution is verifiable through a tiny standalone smoke path and documented operator workflow.
