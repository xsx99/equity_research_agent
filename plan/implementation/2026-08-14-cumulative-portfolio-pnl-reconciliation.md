# Cumulative Portfolio P&L Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and display cumulative stock realized P&L and point-in-time unrealized P&L since the latest clean $1,000,000 paper-account reset, repair sell cash-flow signs, and safely backfill the active lifecycle's historical snapshots.

**Architecture:** Add a pure weighted-average stock-fill ledger and narrow repository read models, then enrich every broker portfolio snapshot before persistence. Keep the mutation path in a standalone dry-run-by-default repair script that reuses the same ledger and validates the active lifecycle, Postgres storage, and transaction boundary. Make `/today` header KPIs snapshot-only so selected-tab lazy loading cannot change account-level values.

**Tech Stack:** Python 3.13, dataclasses, SQLAlchemy/PostgreSQL, pytest, FastAPI/Jinja read models.

**Design:** `plan/design/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`

---

## File Structure

- Create `src/trading/portfolio/pnl.py`: pure fill/event contracts, clean-reset boundary selection, weighted-average replay, live snapshot enrichment, quantity/cost validation, and reconciliation metadata.
- Modify `src/core/config.py`: one `PAPER_ACCOUNT_STARTING_EQUITY` setting with a `$1,000,000` default.
- Modify `src/trading/repositories/in_memory.py`: normalized filled-stock event and portfolio-snapshot history loaders for tests/offline paths.
- Modify `src/trading/repositories/mixins/execution.py`: SQLAlchemy equivalents joined to `paper_orders.action`.
- Modify `src/trading/brokers/paper_stock.py`: action-aware stock fill cash-effect sign.
- Modify `src/trading/portfolio/sync.py`: enrich broker snapshots from replayed fills before any persistence.
- Modify `src/web/routers/loaders/header_system.py`: use persisted snapshot realized/unrealized values only.
- Modify `src/web/routers/today.py`: remove header dependence on tab-scoped position loading.
- Create `scripts/repair_portfolio_pnl.py`: dry-run/default and explicit `--apply` historical repair entrypoint.
- Create `tests/trading/test_portfolio_pnl.py`: pure domain and boundary behavior.
- Modify `tests/trading/test_paper_stock_broker.py`: buy/sell cash-effect regression coverage.
- Modify `tests/trading/test_portfolio_sync.py`: live enrichment, validation failure, and no-persist coverage.
- Modify `tests/trading/test_sqlalchemy_repository.py`: normalized repository read-model round trip.
- Modify `tests/web/test_today.py`: snapshot-only header and all-tab consistency coverage.
- Create `tests/scripts/test_repair_portfolio_pnl.py`: dry-run/apply, idempotency, lifecycle isolation, and storage guard coverage.
- Modify `documents/research_app/deploy.md`: operator commands for storage verification, dry-run review, apply, and post-apply validation.
- Modify `plan/progress_tracker.md` and the task progress tracker created after this plan is approved.

## Shared Calculation Contract

Use these focused contracts in `src/trading/portfolio/pnl.py`:

```python
@dataclass(frozen=True)
class StockFillEvent:
    execution_id: str
    ticker: str
    executed_at: datetime
    action: str
    quantity: float
    fill_price: float


@dataclass(frozen=True)
class PortfolioPnlPoint:
    snapshot_time: datetime
    account_equity: float
    stock_market_value: float
    option_market_value: float


@dataclass(frozen=True)
class OpenCostBasis:
    quantity: float
    average_cost: float


@dataclass(frozen=True)
class StockPnlReplay:
    realized_pnl: float
    open_cost_basis: dict[str, OpenCostBasis]
    fill_count: int


class PortfolioPnlValidationError(ValueError):
    pass
```

Public functions:

```python
def select_active_lifecycle_boundary(
    points: Sequence[PortfolioPnlPoint],
    fills: Sequence[StockFillEvent],
    *,
    starting_equity: float,
    currency_tolerance: float = 0.01,
) -> datetime: ...


def replay_stock_fills(
    fills: Sequence[StockFillEvent],
    *,
    started_at: datetime,
    through: datetime,
) -> StockPnlReplay: ...


def enrich_snapshot_with_stock_pnl(
    snapshot: PortfolioSnapshot,
    *,
    positions: Sequence[StockPosition],
    points: Sequence[PortfolioPnlPoint],
    fills: Sequence[StockFillEvent],
    starting_equity: float,
) -> PortfolioSnapshot: ...
```

The implementation sorts by `(executed_at, execution_id)`, rejects duplicate ids and invalid numeric values, treats `enter_long` as a weighted-average buy and `reduce`/`exit` as a sell, rejects oversells, uses replayed cost basis for unrealized P&L, validates latest replay quantities against broker positions, and merges `weighted_average_stock_fills_v1` metadata into a new immutable `PortfolioSnapshot`.

Define and reuse these constants in the domain module and import them in live sync/backfill tests; do not duplicate numeric literals:

```python
QUANTITY_TOLERANCE = 1e-6
CURRENCY_TOLERANCE = 0.01
AVERAGE_COST_TOLERANCE = 0.01
RECONCILIATION_RESIDUAL_TOLERANCE = 0.01
```

- Per-ticker replay/broker quantity difference greater than `QUANTITY_TOLERANCE` is fatal.
- Any nonzero average-cost difference up to and including `AVERAGE_COST_TOLERANCE` is accepted and recorded in `pnl_cost_basis_diagnostics`; a larger difference is fatal.
- `pnl_reconciled` is true only when the absolute residual is no greater than `RECONCILIATION_RESIDUAL_TOLERANCE`.
- Every enriched snapshot records `pnl_excluded_pre_boundary_fill_count` and `pnl_excluded_pre_boundary_snapshot_count`, along with the calculation method, starting equity, boundary, residual, reconciled flag, fill count, tolerances, and cost-basis diagnostics.

### Task 1: Build the pure weighted-average P&L ledger

**Files:**
- Create: `src/trading/portfolio/pnl.py`
- Create: `tests/trading/test_portfolio_pnl.py`

- [ ] **Step 1: Write failing validation and ordering tests**

Add tests for a profitable round trip, losing round trip, two buys plus partial reduction, equal-timestamp stable-id ordering, duplicate execution ids, non-positive quantity/price, unsupported action, and oversell. Use timezone-aware datetimes and `pytest.approx`.

Representative assertion:

```python
replay = replay_stock_fills(
    (
        fill("buy-1", "AAPL", "enter_long", 10, 100),
        fill("buy-2", "AAPL", "enter_long", 10, 120),
        fill("sell-1", "AAPL", "reduce", 5, 130),
    ),
    started_at=START,
    through=END,
)
assert replay.realized_pnl == pytest.approx(100.0)
assert replay.open_cost_basis["AAPL"].quantity == pytest.approx(15.0)
assert replay.open_cost_basis["AAPL"].average_cost == pytest.approx(110.0)
```

- [ ] **Step 2: Run the ledger tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_pnl.py -q`

Expected: collection/import failure because `src.trading.portfolio.pnl` does not exist.

- [ ] **Step 3: Implement the minimal pure replay**

Create the dataclasses and `PortfolioPnlValidationError`; normalize tickers, validate unique ids/values/actions, sort deterministically, update weighted-average cost on buys, and realize P&L on reductions/exits. Exclude events before `started_at` and after `through`.

- [ ] **Step 4: Run the ledger tests and verify GREEN**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_pnl.py -q`

Expected: all new ledger tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/trading/portfolio/pnl.py tests/trading/test_portfolio_pnl.py
git commit -m "feat: add cumulative stock pnl ledger"
```

### Task 2: Add active-lifecycle boundary selection and snapshot enrichment

**Files:**
- Modify: `src/trading/portfolio/pnl.py`
- Modify: `src/core/config.py`
- Modify: `tests/trading/test_portfolio_pnl.py`

- [ ] **Step 1: Write failing lifecycle and enrichment tests**

Cover:

- latest of two qualifying `$1,000,000` flat snapshots wins;
- a candidate sharing an exact execution timestamp is skipped;
- pre-boundary fills are excluded;
- no clean reset raises `PortfolioPnlValidationError`;
- latest position quantity mismatch raises;
- material broker/replay average-cost mismatch raises;
- small cost mismatch is metadata only;
- realized, unrealized, total reconciliation residual, boundary, and fill count are written to a copied snapshot;
- exact tolerance boundaries and the `pnl_reconciled` flag are deterministic;
- excluded pre-boundary fill/snapshot counts and all tolerance values are written to metadata;
- pre-existing metadata is preserved.

Use a snapshot with `equity=988_482.96`, `stock_market_value=64_813.47`, replayed open cost `65_258.572198`, and assert approximately `realized=-11_065.49`, `unrealized=-445.10`, and residual near `-6.45`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_pnl.py -q`

Expected: failures for missing boundary selection/enrichment APIs.

- [ ] **Step 3: Implement boundary selection, config, and enrichment**

Add `PAPER_ACCOUNT_STARTING_EQUITY = float(os.getenv("PAPER_ACCOUNT_STARTING_EQUITY", "1000000"))` in `src/core/config.py`. Implement latest-clean-reset selection and immutable snapshot enrichment with explicit quantity/currency tolerances and metadata keys from the design.

Do not force the residual into realized P&L. Do not include option market value in stock unrealized P&L.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_pnl.py -q`

Expected: all P&L domain tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/core/config.py src/trading/portfolio/pnl.py tests/trading/test_portfolio_pnl.py
git commit -m "feat: reconcile portfolio snapshots from stock fills"
```

### Task 3: Add normalized repository P&L inputs

**Files:**
- Modify: `src/trading/repositories/in_memory.py:608-677`
- Modify: `src/trading/repositories/mixins/execution.py:56-181`
- Modify: `tests/trading/test_sqlalchemy_repository.py`
- Modify: `tests/trading/test_portfolio_sync.py`

- [ ] **Step 1: Write failing repository tests**

Add SQLAlchemy and in-memory assertions for:

```python
events = repository.load_filled_stock_events()
points = repository.load_portfolio_pnl_points()
```

Require `load_filled_stock_events()` to inner-join `PaperExecution` to `PaperOrder`, include only `PaperOrder.status == "filled"`, map `paper_execution_id` to `execution_id`, preserve `action`, and order by `(executed_at, paper_execution_id)`. Require `load_portfolio_pnl_points()` to order snapshots ascending.

- [ ] **Step 2: Run repository tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_sqlalchemy_repository.py -k 'filled_stock_events or portfolio_pnl_points' -q`

Expected: failures because the loaders do not exist.

- [ ] **Step 3: Implement both loaders in SQL and in-memory repositories**

Use the pure `StockFillEvent` and `PortfolioPnlPoint` contracts. In-memory joining must look up the saved `PaperOrderRecord` by `paper_order_id`, reject orphan filled executions by letting the later domain validation fail with a useful message, and return deterministic tuples.

- [ ] **Step 4: Run focused repository tests and verify GREEN**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_sqlalchemy_repository.py -k 'filled_stock_events or portfolio_pnl_points' -q`

Then run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_sync.py -q`

Expected: focused repository tests pass; existing sync tests identify any fixtures that now need an explicit clean baseline and fill history before live enrichment is wired.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/trading/repositories/in_memory.py src/trading/repositories/mixins/execution.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_portfolio_sync.py
git commit -m "feat: load normalized portfolio pnl history"
```

### Task 4: Correct future stock execution cash effects

**Files:**
- Modify: `src/trading/brokers/paper_stock.py:293-309`
- Modify: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write a failing filled-sell regression**

Submit/refresh a `reduce` order with a filled broker response and assert:

```python
assert execution.net_cash_effect == pytest.approx(quantity * fill_price)
```

Retain the existing buy assertion as negative and add direct coverage for `exit`.

- [ ] **Step 2: Run the cash-effect test and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py -k 'cash_effect' -q`

Expected: sell case fails because `_store_local_order` always negates notional.

- [ ] **Step 3: Implement one action-aware helper**

```python
def _stock_fill_cash_effect(*, action: str, quantity: float, fill_price: float) -> float:
    notional = quantity * fill_price
    if action in {"reduce", "exit"}:
        return notional
    return -notional
```

Use it only when constructing `PaperExecutionRecord`; do not change order-side mapping.

- [ ] **Step 4: Run broker tests and verify GREEN**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py -q`

Expected: broker suite passes.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/trading/brokers/paper_stock.py tests/trading/test_paper_stock_broker.py
git commit -m "fix: preserve stock sell cash inflows"
```

### Task 5: Enrich every live broker snapshot before persistence

**Files:**
- Modify: `src/trading/portfolio/sync.py:34-106`
- Modify: `tests/trading/test_portfolio_sync.py`
- Modify: `tests/trading/test_runtime_live.py`
- Modify: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write failing live-sync tests**

Seed an in-memory clean baseline snapshot, matching filled buy/sell events, and current broker positions. Assert that the returned and persisted snapshot has calculated realized/unrealized P&L and reconciliation metadata.

Add a separate test with an oversell or quantity mismatch and assert:

- `PortfolioPnlValidationError` is raised;
- `replace_paper_positions` is not called;
- `save_portfolio_snapshot` is not called.

- [ ] **Step 2: Run focused sync tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_sync.py -k 'pnl or invalid_execution_history' -q`

Expected: snapshot still contains broker-default zero P&L or missing validation.

- [ ] **Step 3: Wire enrichment before the persistence block**

After broker positions are normalized and the account snapshot is built, call repository history loaders and `enrich_snapshot_with_stock_pnl(...)`. Ensure enrichment occurs even when `persist=False` so risk context and dry-run callers see correct P&L; ensure all validation happens before any local option/position/snapshot writes.

Update existing sync/runtime fixtures to include a clean baseline and matching fill inputs. Do not weaken validation with `getattr(..., fallback)` in production repositories.

- [ ] **Step 4: Run sync and runtime regression suites**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_sync.py -q
source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py -q
```

Expected: all affected live workflow tests pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/trading/portfolio/sync.py tests/trading/test_portfolio_sync.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py
git commit -m "feat: persist reconciled live portfolio pnl"
```

### Task 6: Make Today header P&L snapshot-consistent across tabs

**Files:**
- Modify: `src/web/routers/loaders/header_system.py:39-86`
- Modify: `src/web/routers/today.py:316-369`
- Modify: `tests/web/test_today.py:882-912`
- Modify: `tests/web/test_today_portfolio_loader.py`

- [ ] **Step 1: Replace the old behavior test with failing snapshot-authority tests**

Change `test_build_header_uses_open_position_unrealized_pnl_when_available` to assert that a nonzero persisted snapshot unrealized value wins even if supplied position rows differ. Add a dashboard test iterating `overview`, `portfolio`, `trades`, `candidates`, `risk-macro`, and `system` and asserting identical realized/unrealized header values.

Retain a position-table test showing the per-position sum agrees with the snapshot within the documented currency tolerance.

- [ ] **Step 2: Run the web tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -k 'header and unrealized or pnl_consistent_across_tabs' -q`

Expected: current header prefers tab-loaded position sums and risk/system differ.

- [ ] **Step 3: Remove tab-scoped position dependence from `_build_header`**

Use only:

```python
"realized_pnl": latest_portfolio.realized_pnl if latest_portfolio else None,
"unrealized_pnl": latest_portfolio.unrealized_pnl if latest_portfolio else None,
```

Remove the `positions` parameter and its call-site argument. Do not change templates or formatting.

- [ ] **Step 4: Run web regression suites and verify GREEN**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_portfolio_loader.py -q
source ~/.venv/bin/activate && pytest tests/web -q
```

Expected: web suites pass and all tabs share snapshot values.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/web/routers/loaders/header_system.py src/web/routers/today.py tests/web/test_today.py tests/web/test_today_portfolio_loader.py
git commit -m "fix: keep today pnl consistent across tabs"
```

### Task 7: Add the safe historical repair command

**Files:**
- Create: `scripts/repair_portfolio_pnl.py`
- Create: `tests/scripts/test_repair_portfolio_pnl.py`

- [ ] **Step 1: Write failing dry-run, apply, and lifecycle-isolation tests**

Test the pure command function with a real SQLAlchemy session fixture or transaction-capable fake:

- default/dry-run rolls back all snapshot and cash-effect changes;
- `--apply` commits snapshot fields, merged metadata, and positive reduce/exit cash effects;
- second apply is idempotent;
- multiple qualifying reset snapshots select the latest, and all pre-boundary snapshots, fills, and cash-effect rows stay unchanged;
- ambiguous same-timestamp reset is skipped;
- latest open `PaperPosition` quantities are validated per ticker against the replay at the latest snapshot;
- latest local/broker-mirrored average cost within `AVERAGE_COST_TOLERANCE` is diagnostic, while a larger difference blocks all writes;
- latest-state quantity mismatch and material cost mismatch roll back all writes;
- validation failure rolls back everything;
- unsafe `SHOW data_directory` paths (`/tmp`, `/run`, `/dev/shm`) block apply;
- safe `/var/lib/postgresql/data` permits apply;
- `main(["--json"])` is dry-run by default, while `main(["--apply", "--json"])` is explicit.

- [ ] **Step 2: Run script tests and verify RED**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_repair_portfolio_pnl.py -q`

Expected: import failure because the repair script does not exist.

- [ ] **Step 3: Implement a thin CLI over the shared ledger**

Expose:

```python
def run_repair(*, session: Any, apply: bool, starting_equity: float) -> dict[str, object]: ...
def validate_persistent_postgres_storage(session: Any) -> str: ...
def main(argv: list[str] | None = None) -> int: ...
```

Query joined execution/order rows, all snapshots, and current open `PaperPosition` rows; use `with_for_update()` only in apply mode. Select the active boundary, walk snapshots ascending while replaying through each cutoff, then validate the latest replayed per-ticker quantities and average costs against the current mirrored positions before changing any ORM row. Update only post-boundary rows, repair only post-boundary reduce/exit `net_cash_effect`, merge the shared tolerance/excluded-count/reconciliation metadata, and make one final `commit()` or `rollback()`.

Return JSON fields required by the design: boundary, excluded counts, snapshot/fill counts, latest realized/unrealized/residual, maximum absolute residual, repair count, tolerances, mismatches, data directory, and applied/dry-run status.

- [ ] **Step 4: Run script tests and verify GREEN**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_repair_portfolio_pnl.py -q`

Expected: all script tests pass.

- [ ] **Step 5: Commit Task 7**

```bash
git add scripts/repair_portfolio_pnl.py tests/scripts/test_repair_portfolio_pnl.py
git commit -m "feat: add safe portfolio pnl history repair"
```

### Task 8: Document operations and update trackers

**Files:**
- Modify: `documents/research_app/deploy.md`
- Modify: `plan/progress_tracker.md`
- Modify: `plan/progress/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`

- [ ] **Step 1: Add operator documentation**

Document:

```bash
docker exec postgres_db psql -U postgres -d mono_db -c "SHOW data_directory;"
source ~/.venv/bin/activate
PYTHONPATH=. python scripts/repair_portfolio_pnl.py --json
PYTHONPATH=. python scripts/repair_portfolio_pnl.py --apply --json
```

State that dry-run output must be reviewed before apply, apply changes only the latest clean account lifecycle, the command is idempotent, and unsafe/temporary Postgres storage blocks apply.

- [ ] **Step 2: Update both progress trackers**

Mark implementation tasks complete only after their tests pass. Add the final calculated production values, dry-run/apply row counts, rendered UI evidence, and exact verification commands to `plan/progress_tracker.md`.

- [ ] **Step 3: Run documentation and structural checks**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/test_deploy_config.py -q
source ~/.venv/bin/activate && python -m compileall -q src scripts tests
git diff --check
```

Expected: deploy test, compilation, and whitespace checks pass.

- [ ] **Step 4: Commit Task 8**

```bash
git add documents/research_app/deploy.md plan/progress_tracker.md plan/progress/2026-08-14-cumulative-portfolio-pnl-reconciliation.md
git commit -m "docs: record portfolio pnl repair operations"
```

### Task 9: Verify, dry-run, apply, and render

**Files:**
- No code changes expected; update trackers only if verification evidence changes.

- [ ] **Step 1: Run focused suites**

```bash
source ~/.venv/bin/activate && pytest \
  tests/trading/test_portfolio_pnl.py \
  tests/trading/test_paper_stock_broker.py \
  tests/trading/test_portfolio_sync.py \
  tests/trading/test_sqlalchemy_repository.py \
  tests/scripts/test_repair_portfolio_pnl.py \
  tests/web/test_today.py \
  tests/web/test_today_portfolio_loader.py -q
```

- [ ] **Step 2: Run the full unit suite**

Run: `source ~/.venv/bin/activate && pytest -q`

Expected: all tests pass, or any pre-existing environment-only failures are reproduced on the unmodified base and documented precisely.

- [ ] **Step 3: Run compile and diff checks**

```bash
source ~/.venv/bin/activate && python -m compileall -q src scripts tests
git diff --check
```

- [ ] **Step 4: Verify persistent production Postgres and run dry-run**

Read `documents/raspberry_pi_service_checks.md`, verify `SHOW data_directory;` and the Docker host mount point are persistent disk, then run:

```bash
source ~/.venv/bin/activate && PYTHONPATH=. python scripts/repair_portfolio_pnl.py --json
```

Review expected latest realized near `-$11.07k`, nonzero unrealized, residual near the diagnosed small difference, boundary, excluded counts, tolerances, current-position validation, and every mismatch. Save the dry-run JSON as evidence.

- [ ] **Step 5: Stop and obtain explicit operator approval for the exact dry-run report**

Present the boundary, rows to update, cash-effect repair count, latest P&L, residual, storage path, and all diagnostics to the user. Do not execute `--apply` until the user explicitly approves that report. This checkpoint is required even though historical backfill was approved at design time.

- [ ] **Step 6: Apply the approved historical repair and rerun dry-run**

```bash
source ~/.venv/bin/activate && PYTHONPATH=. python scripts/repair_portfolio_pnl.py --apply --json
source ~/.venv/bin/activate && PYTHONPATH=. python scripts/repair_portfolio_pnl.py --json
```

Expected: apply succeeds atomically; the second dry-run reports no additional cash-effect repairs or snapshot changes.

- [ ] **Step 7: Render and inspect Today UI**

Start the existing app and inspect `/today?tab=overview`, `/today?tab=risk-macro`, and `/today?tab=system`. Confirm:

- Realized P&L is cumulative and nonzero;
- Unrealized P&L matches current open-position P&L within tolerance;
- all three tabs display identical values;
- currency formatting and negative tone remain correct;
- adjacent KPI cards still render cleanly.

Use the `ui-development` checklist and `browser:control-in-app-browser` skill. If the browser cannot be run, explicitly request screenshots rather than claiming visual completion.

- [ ] **Step 8: Request code review and record final evidence**

Use `superpowers:requesting-code-review`, address blocking feedback, update both trackers with final evidence, and commit tracker-only changes if any.

## Completion Conditions

- Every production-code behavior was preceded by a failing regression test.
- Latest and historical active-lifecycle snapshots contain cumulative realized and point-in-time unrealized stock P&L.
- Pre-boundary lifecycle rows are unchanged.
- Buy cash effects are negative and sell cash effects are positive.
- Every `/today` tab uses the same latest persisted P&L.
- Production apply is preceded by a reviewed dry-run and persistent-storage verification.
- Re-running repair is idempotent.
- Focused/full tests, compilation, `git diff --check`, rendered UI inspection, code review, and progress trackers are complete.
