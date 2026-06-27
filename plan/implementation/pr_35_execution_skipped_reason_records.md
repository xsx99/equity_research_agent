# PR 35 Execution Skipped-Reason Records + JSON→Column Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop orders from being silently dropped. Every trading decision that reaches an execution path must produce a persisted, reasoned outcome record — `submitted`, `skipped(reason)`, or `failed(error)` — across the pre-open, intraday, and manual-review phases. As part of the same pass, cut the `paper_trade_authorized` control-flow gate off untyped `metadata_json` and onto the real typed column/field, and make the option broker fail-fast (or fall back to local sim) instead of raising a 401 mid-submit.

**Architecture:** Introduce one new audit table, `execution_attempts`, written by the execution workflows. The stock gate in `PaperExecutionWorkflow._execute_stock_decision`, the option gate in `_handle_option_decision`, and the intraday gate in `IntradayRebalancePipeline._should_execute_decision` each emit an attempt record on every decision instead of taking a bare `return`. The runtime execution report (`build_execution_report`) is extended to surface `skipped`/`failed` counts and reason breakdowns so "0 orders submitted" can no longer read as success. `TradingDecisionRecord` gains a first-class `paper_trade_authorized: bool` field so the workflow and the persisted column stay in lockstep.

**Tech Stack:** Python, SQLAlchemy, Alembic, Postgres JSONB, pytest, existing trading workflow + repository mixins.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md` — execution + decision contracts
3. `plan/implementation/README.md` — Execution Rules + Reading Discipline
4. `plan/design/06_paper_trading_and_risk.md`
5. `plan/design/05_workflows_and_decision_contracts.md`
6. `plan/progress_tracker.md` — **Recent** section only
7. `plan/review_backlog.md` — items #1 and #3 (this PR implements both)

## Context: what is broken today (verified file:line)

**Silent stock gate** — `src/trading/workflows/paper_execution.py:341-350`:
```python
def _execute_stock_decision(self, *, trading_decision, risk_decision, trade_date, orders, snapshots) -> None:
    if trading_decision.instrument_type != "stock":
        return                                                              # (a) instrument mismatch
    if trading_decision.decision not in {"enter_long", "reduce", "exit", "enter_short"}:
        return                                                              # (b) non-executable action
    if not bool(trading_decision.metadata_json.get("paper_trade_authorized", False)) and trading_decision.manual_request_id is None:
        return                                                              # (c) not authorized — reads JSON, not the column (#3)
    if risk_decision is None:
        return                                                              # (d) risk missing
    if risk_decision.status not in {"approved", "reduced"}:
        return                                                              # (e) risk rejected
    ...
    execution = self.broker.find_execution_by_order_id(order.paper_order_id)
    if execution is None:
        return                                                              # (f) no fill returned
```
Every one of these is a bare `return` with no persisted record. The runtime only counts `len(result.paper_orders)` (`src/trading/runtime/preopen_runner.py:98-104`), so a fully-dropped batch reports `orders_submitted: 0` and the run still shows `status: passed`.

**Silent option gate** — `src/trading/workflows/paper_execution.py:223-262`: `_handle_option_decision` returns early (no record) when `option_decision is None`, `status == "rejected"`, `option_broker is None`, `active_risk_decision is None`, `status not in {approved, reduced}`, `order_request is None`, or `order.status == "rejected"`.

**Silent intraday gate** — `src/trading/intraday/rebalance.py:477-491`: `_should_execute_decision` returns a bool; when it is `False` the decision is dropped from execution with no skip record, and `execution_summary` (`rebalance.py:239-256`) only carries `orders_submitted` / `option_orders_submitted` counts.

**Option broker crash risk** — `src/trading/brokers/paper_option.py:198-261`: the broker enters live mode whenever ANY of `api_key / secret_key / client / trading_base_url` is set (line 198-206). In live mode `submit_order` calls `response.raise_for_status()` (line 249) and `_auth_headers()` raises `RuntimeError("missing_alpaca_credentials")` (line 342) — with a `trading_base_url` set but creds missing, this raises mid-submit and propagates out of `PaperExecutionWorkflow.run`, crashing the whole phase.

**#3 — column vs JSON:**
- `paper_trade_authorized` IS a real typed column (`src/db/models/trading/execution.py:78`), persisted at write time from `metadata_json` (`src/trading/repositories/mixins/runtime_misc.py:155`). But the in-memory `TradingDecisionRecord` dataclass (`src/trading/workflows/trading_decision.py:42-74`) has **no** `paper_trade_authorized` field — only `metadata_json` — and the workflow reads `trading_decision.metadata_json.get(...)`. So the column and the JSON are derived from the same source but the *control flow* reads the untyped path.
- **Correction to the backlog:** there is **no** `strategy_lifecycle_status` column on `trading_decisions` (verified: `grep -rn strategy_lifecycle_status src/db/` returns nothing). Lifecycle status is a property of the *strategy* (`src/db/models/trading/strategy.py:46 lifecycle_status`) and is carried on the candidate (`src/trading/strategies/matching.py:274`). The metadata reads at `paper_execution_options.py:671,796` reconstruct a `candidate` SimpleNamespace from `metadata_json` to re-run option-strategy building. Treat `strategy_lifecycle_status` cutover as **out of scope for a column migration** — see Task 6 for the bounded action.

## Guardrails

- Behavior-preserving for the *happy path*: a decision that is authorized + risk-approved + executable must still submit exactly as today and still append to `orders` / `option_orders` / `snapshots`. The only new side effect on the happy path is one `submitted` attempt record.
- Do not change broker submit semantics for the local/sim path. Only the live-mode credential handling changes (Task 5).
- Do not invent new reason codes beyond the enumerated set without adding them to the `CheckConstraint` and the tests.
- New table must ship with an Alembic migration; follow the existing migration style in `migrations/` (inspect the latest revision for `down_revision` chaining and naming).
- Keep `historical_replay_runs` and all existing tables intact (see memory: do not drop replay tables).
- Unit tests use the in-memory repository / fakes; do not require a live Alpaca connection.

## Reason-code vocabulary (use these exact strings)

| reason_code | When |
| --- | --- |
| `submitted` | order submitted and a fill record persisted |
| `not_executable_action` | decision not in the executable set for its instrument |
| `instrument_mismatch` | decision routed to the wrong instrument handler |
| `not_authorized` | `paper_trade_authorized` false and no manual request |
| `risk_missing` | no risk decision attached |
| `risk_rejected` | risk decision status not in `{approved, reduced}` |
| `dry_run` | execution disabled for the phase (`execute_paper_orders` false) |
| `broker_unavailable` | option broker not configured |
| `order_rejected` | broker returned `status == "rejected"` |
| `no_fill` | order submitted but no execution/fill returned |
| `missing_credentials` | live broker selected but Alpaca creds absent |
| `broker_error` | broker raised during submit (caught, recorded, not re-raised) |

## File Map

- Create: `src/db/models/trading/execution_attempt.py` (or add `ExecutionAttempt` to `execution.py` — match how sibling models are grouped; prefer a new file + re-export through the models `__init__`)
- Modify: `src/db/models/trading/__init__.py` (export `ExecutionAttempt`)
- Create: `migrations/versions/<rev>_add_execution_attempts.py`
- Create: `src/trading/execution/attempts.py` — `ExecutionAttemptRecord` dataclass + `reason_code` constants + a small builder helper
- Modify: `src/trading/repositories/mixins/runtime_misc.py` — add `save_execution_attempt`, persist `paper_trade_authorized` from the new field (see Task 6)
- Modify: `src/trading/repositories/_inmemory.py` (or wherever `InMemoryTradingRepository` lives — confirm path) — add `save_execution_attempt` + list accessor for tests
- Modify: `src/trading/workflows/trading_decision.py` — add `paper_trade_authorized` field to `TradingDecisionRecord`; set it where the record is constructed (lines ~215 and ~544)
- Modify: `src/trading/workflows/paper_execution.py` — `_execute_stock_decision`, `_handle_option_decision` emit attempt records; accept/thread a `phase` + an `attempts` sink
- Modify: `src/trading/workflows/paper_execution_options.py` — option order-request / rejection paths emit records
- Modify: `src/trading/intraday/rebalance.py` — `_should_execute_decision` → reasoned decision; record skips; extend `execution_summary`
- Modify: `src/trading/brokers/paper_option.py` — fail-fast / fallback on missing creds (Task 5)
- Modify: `src/trading/runtime/support.py` — extend `build_execution_report` with `orders_skipped`, `orders_failed`, `skip_reasons`
- Modify: `src/trading/runtime/preopen_runner.py`, `src/trading/runtime/intraday_refresh_runner.py`, `src/trading/runtime/manual_review.py` — pass through new counts
- Create: `tests/trading/test_pr35_execution_attempts.py`
- Modify: `plan/progress_tracker.md`
- Modify: `plan/review_backlog.md` — strike items #1 and #3 when done

## Task 1: Define the `execution_attempts` table + migration

**Files:** model file, `__init__.py`, migration.

- [ ] Step 1: Add the `ExecutionAttempt` ORM model. Columns:
  - `execution_attempt_id` UUID PK default `uuid4`
  - `trading_decision_id` UUID FK → `trading_decisions.trading_decision_id` `ondelete="SET NULL"`, nullable, index
  - `paper_order_id` UUID FK → `paper_orders.paper_order_id` `ondelete="SET NULL"`, nullable
  - `paper_option_order_id` UUID FK → `paper_option_orders.paper_option_order_id` `ondelete="SET NULL"`, nullable
  - `ticker` String(16) not null, index
  - `instrument_type` String(32) not null
  - `phase` String(32) not null, index — `'preopen' | 'intraday' | 'manual_review'`
  - `outcome` String(16) not null, index — `'submitted' | 'skipped' | 'failed'`
  - `reason_code` String(64) not null, index
  - `detail` Text nullable
  - `metadata_json` JSONB not null default `dict`
  - `created_at` DateTime(timezone=True) not null `server_default=func.now()`, index
  - `__table_args__`: `CheckConstraint("outcome IN ('submitted','skipped','failed')", ...)`, `CheckConstraint` enumerating the reason codes from the table above, `CheckConstraint("phase IN ('preopen','intraday','manual_review')", ...)`, and a composite `Index("ix_execution_attempts_phase_created", "phase", "created_at")`.
- [ ] Step 2: Export `ExecutionAttempt` from `src/db/models/trading/__init__.py` (match sibling export style).
- [ ] Step 3: Generate the Alembic migration. Inspect the current head revision (`alembic heads` or read the latest file under `migrations/versions/`) and set `down_revision` accordingly. Write explicit `op.create_table(...)` + indexes + check constraints in `upgrade()` and `op.drop_table("execution_attempts")` in `downgrade()`. Do NOT autogenerate blindly — hand-write to match repo style.
- [ ] Step 4 (verify): The executing agent runs the migration against a scratch DB or confirms the revision chains cleanly (`alembic upgrade head` then `downgrade -1`). Per repo policy this is a code-only handoff if no DB is available — note that in the PR description.

## Task 2: `ExecutionAttemptRecord` dataclass + reason constants

**Files:** `src/trading/execution/attempts.py`.

- [ ] Step 1: Define a frozen `ExecutionAttemptRecord` dataclass mirroring the columns (string ids). Add a `create(...)` classmethod that defaults `execution_attempt_id = str(uuid4())` and `metadata_json = {}`.
- [ ] Step 2: Define module-level reason-code constants (e.g. `REASON_NOT_AUTHORIZED = "not_authorized"`, …) and an `ALL_REASON_CODES` frozenset used by both the model `CheckConstraint` doc and the tests.
- [ ] Step 3: Add a helper `skipped(*, trading_decision, phase, reason_code, detail=None)` and `submitted(...)` / `failed(...)` factory functions so call sites stay one-liners.

## Task 3: Repository `save_execution_attempt`

**Files:** `runtime_misc.py` (SQLAlchemy), in-memory repo.

- [ ] Step 1: Add `save_execution_attempt(self, attempt: ExecutionAttemptRecord) -> None` to the SQLAlchemy mixin — upsert by `execution_attempt_id`, set all columns, `self.session.flush()`. Mirror the existing `save_*` patterns in `runtime_misc.py`.
- [ ] Step 2: Add the same method to `InMemoryTradingRepository`, appending to a list, plus a read accessor (e.g. `list_execution_attempts()`) for tests.
- [ ] Step 3 (verify): targeted test that both repos round-trip an attempt record.

## Task 4: Emit attempt records in the execution workflows

**Files:** `paper_execution.py`, `paper_execution_options.py`, `intraday/rebalance.py`, `trading_decision.py`.

- [ ] Step 1: Add `paper_trade_authorized: bool = False` to `TradingDecisionRecord` (`trading_decision.py:42-74`). Populate it at both construction sites from the SAME expression currently written into `metadata_json["paper_trade_authorized"]` (`trading_decision.py:216-221` and `:545`). Keep writing the metadata key for now (display/back-compat); the field is the authority.
- [ ] Step 2: In `_execute_stock_decision` (`paper_execution.py:341`), replace each bare `return` with: build a `skipped` `ExecutionAttemptRecord` with the matching reason code, `self.repository.save_execution_attempt(...)`, structured log, then `return`. Specifically:
  - instrument check → `instrument_mismatch`
  - action check → `not_executable_action`
  - authorization check → read `trading_decision.paper_trade_authorized` (NOT metadata) → `not_authorized`
  - `risk_decision is None` → `risk_missing`
  - status check → `risk_rejected`
  - `execution is None` after submit → `no_fill`
  On the success path (after `save_paper_execution`), emit a `submitted` attempt linked to `order.paper_order_id`.
- [ ] Step 3: Thread a `phase: str` into `PaperExecutionWorkflow.run(...)` (default `"preopen"`; intraday/manual callers pass their phase) so attempt records are attributable. Pass it down to `_execute_stock_decision` / `_handle_option_decision`.
- [ ] Step 4: In `_handle_option_decision` (`paper_execution.py:211-262`) emit `skipped`/`order_rejected`/`broker_unavailable`/`risk_*`/`no_fill` records at each early return, and a `submitted` record after `save_paper_option_execution`. Reuse the helpers from Task 2.
- [ ] Step 5: In `IntradayRebalancePipeline` (`rebalance.py:477-491`): change `_should_execute_decision` (or its caller) so that when execution is declined it records a `skipped` attempt with the precise reason (`broker_unavailable`, `risk_missing`, `risk_rejected` for `status != "approved"`, `not_executable_action` when `_requires_execution_risk_decision` is false). Extend `execution_summary` (`rebalance.py:239-256`) to include `orders_skipped` and a `skip_reasons: dict[str,int]`.
- [ ] Step 6 (verify): tests in `test_pr35_execution_attempts.py` driving each branch and asserting exactly one attempt record with the expected `(outcome, reason_code)` per decision.

## Task 5: Option broker fail-fast / fallback

**Files:** `src/trading/brokers/paper_option.py`.

- [ ] Step 1: Decide live-mode selection deliberately. Today ANY of `{api_key, secret_key, client, trading_base_url}` flips live mode (line 198-206), but `trading_base_url` defaults from env / a constant, so a bare base URL with no creds triggers live mode with no auth. Change the `use_broker` predicate so live mode requires **both** `api_key` and `secret_key` to be resolvable (an injected `client` may still force live mode for tests). Otherwise fall back to `LocalPaperOptionBroker`.
- [ ] Step 2: In `submit_order`'s live branch, wrap the credential resolution + `self._client.post(...)` + `raise_for_status()` so a missing-credential / auth failure does NOT propagate as an uncaught `RuntimeError`. Instead return a `rejected` `PaperOptionOrderRecord` with `rejection_reason="missing_credentials"` (or `broker_error`) via the existing `_store_local_order(...)` path. The caller (`_handle_option_decision`) already records `order_rejected`; map this rejection_reason into an attempt `reason_code` of `missing_credentials` / `broker_error`.
- [ ] Step 3 (verify): test that constructing the broker with `trading_base_url` set but no creds yields local-sim mode (no network), and that a forced-live broker with a client that raises 401 returns a `rejected` order rather than propagating.

## Task 6: `paper_trade_authorized` column cutover + `strategy_lifecycle_status` bounded fix

**Files:** `runtime_misc.py`, `paper_execution.py` (already in Task 4), `paper_execution_options.py`.

- [ ] Step 1: In `runtime_misc.py:155`, persist the column from the new record field: `row.paper_trade_authorized = bool(decision.paper_trade_authorized)` (fall back to the metadata key only if the field is absent, for transitional safety). The workflow read is already on the field (Task 4 Step 2).
- [ ] Step 2: `strategy_lifecycle_status` — there is no column to cut over to. Bounded action: at `paper_execution_options.py:671,796`, the value is only used to rebuild a candidate for re-running option strategy building. Leave the metadata read in place BUT add a single source-of-truth note + a guard: if `metadata_json` lacks the key, resolve from the strategy definition via the existing catalog/matching path rather than silently defaulting to `"active"`. Do NOT add a migration. Capture the "should there be a column?" question as a follow-up note in the progress tracker — do not expand scope here.
- [ ] Step 3: Add a `config_json` pydantic validation model — **defer to a separate slice**; it is listed in backlog #3 but is independent of the live order-drop bug. Note it in the tracker as not-done so it is not lost.

## Task 7: Surface counts in the runtime report

**Files:** `runtime/support.py`, `preopen_runner.py`, `intraday_refresh_runner.py`, `manual_review.py`.

- [ ] Step 1: Extend `build_execution_report` (`support.py:85-96`) signature with `orders_skipped: int = 0`, `orders_failed: int = 0`, `skip_reasons: dict[str, int] | None = None`; include them in the returned dict.
- [ ] Step 2: In each runner's `_run_execution`, compute these from the attempt records produced this run (or from the extended `execution_summary` for intraday). Keep `orders_submitted` semantics unchanged.
- [ ] Step 3: Ensure a run where everything was skipped reports `status` truthfully — at minimum the report must let the `/today` health bar (PR for backlog #5) read `submitted=0, skipped=N(reasons)`. Do not change phase `status` to `failed` for an all-skipped run unless a `failed` attempt exists; an all-`skipped` run is `passed` but visibly non-empty.

## Task 8: Tests, tracker, backlog

- [ ] Step 1: `tests/trading/test_pr35_execution_attempts.py` covering: each stock-gate branch, each option-gate branch, intraday skip recording + `execution_summary`, broker fail-fast, `paper_trade_authorized` field→column persistence, and `build_execution_report` count math.
- [ ] Step 2: Run the targeted suite, then the broader `tests/trading/` execution + runtime suites (per repo TDD rules). Record results in the PR description.
- [ ] Step 3: Prepend a dated entry to the **Recent** section of `plan/progress_tracker.md` summarizing the new audit surface and the column cutover, and note the two deferred follow-ups (config_json pydantic validation; strategy_lifecycle_status column question).
- [ ] Step 4: In `plan/review_backlog.md`, mark #1 resolved and #3 partially resolved (note the two deferred sub-items).

## Done when

- Every decision through pre-open, intraday, and manual-review execution produces exactly one `execution_attempts` row with a correct `(outcome, reason_code)`.
- The stock authorization gate reads the typed field/column, not `metadata_json`.
- A live option broker with missing creds returns a rejected order (recorded), never crashes the phase.
- The runtime execution report distinguishes submitted / skipped(reason) / failed(error).
- Targeted + relevant broader tests pass; tracker + backlog updated.
