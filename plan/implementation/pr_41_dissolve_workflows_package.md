# PR 41 Dissolve the `workflows/` Package Implementation Plan

> Slice 2 of the trading workflow/component topology refactor. Steps use checkbox (`- [ ]`) syntax.
> Implement task-by-task; run the listed verification after each task. **Depends on PR 40 having
> landed** (the `decision/` package + the `workflows/trading_decision.py` and
> `workflows/option_strategy_builder.py` shims must already exist).

**Goal:** Move the five remaining real modules out of `src/trading/workflows/` into the capability
packages that own them, leaving `workflows/` as a shim-only package. After this slice, every file in
`workflows/` is a thin compatibility re-export; no business logic lives there.

**Architecture:** Move-and-reexport, identical mechanics to PR 40. Each moved module gets a canonical
home in its capability package; the old `workflows/<name>.py` path stays as a shim re-exporting the
public surface. Callers are **not** migrated. `brokers/` and `data_sources/` are **not** relocated
(they are coherent, heavily-imported packages — see the design doc's scope refinement).

**Tech Stack:** Python, pytest. No dependency, schema, or behavior changes.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/design/2026-06-26-trading-workflow-component-topology.md` (PR 41 is slice 2; read the scope
   refinement)
3. `plan/implementation/pr_40_decision_package_extraction.md` (same mechanics; this builds on it)
4. `plan/progress_tracker.md` Recent section only

## Guardrails

- **Pure structural refactor.** Move code verbatim; the only edits are import statements that must
  point at new module locations.
- **Do not migrate caller import paths.** Every `from src.trading.workflows.<x> import …` in
  production/tests/scripts stays as-is and resolves through the shim.
- **Preserve object identity across re-exports** and the `test_pr32` identity assertions for
  `paper_execution` ↔ `paper_execution_options` (see Task 4).
- **Preserve monkeypatch seams.** Before editing, run
  `grep -rn 'monkeypatch.setattr("src.trading.workflows' tests` and make sure every patched
  attribute still exists on its shim module after the move. (Known: `test_runtime_live.py` patches
  `…trading_decision.TradingDecisionPipeline` — that is PR 40's shim, untouched here.)
- **`import *` drops underscore helpers.** Use explicit re-export lists in shims; no `globals()`
  pattern (PR 35's `test_pr34` enforces this for the option builder, and it is the house rule now).
- Do **not** touch `brokers/`, `data_sources/`, `decision/`, or any `runtime/`/`phases/` file. Those
  are other slices.
- Do not rename `strategies/` to `strategy/`.

## Moves (canonical home ← source)

| Source (`src/trading/workflows/`) | Canonical home | Public surface to preserve |
|---|---|---|
| `paper_execution.py` | `src/trading/execution/paper_execution.py` | `PaperExecutionWorkflow`, `PaperExecutionWorkflowResult`, `_build_option_order_request` |
| `paper_execution_options.py` | `src/trading/execution/paper_execution_options.py` | `_build_option_order_request`, `_hedge_trading_decision_from_generated_action`, `_option_decision_from_trading_decision` (+ its public surface) |
| `signal_snapshot.py` | `src/trading/signals/pipeline.py` | `SignalPipeline`, `SourceIngestionServiceProtocol` |
| `strategy_scoring.py` | `src/trading/strategies/scoring.py` | `StrategyPipeline`, `StrategyPipelineResult` |
| `portfolio_sync.py` | `src/trading/portfolio/sync.py` | `BrokerPortfolioSyncWorkflow`, `BrokerPortfolioSyncResult` |
| `universe_scan.py` | `src/trading/data_sources/universe_scan.py` | `UniverseScanPipeline` |

`execution/` already exists (PR 35: `__init__.py` + `attempts.py`) — the two `paper_execution*`
modules join it; do not clobber `attempts.py` or the package docstring.

## Caller inventory (must keep resolving through shims — do NOT edit)

- `workflows.paper_execution`: `intraday/rebalance.py`, `runtime/preopen_dependencies.py`,
  `runtime/smoke_fixture_modes.py`, `workflows/__init__.py`, + tests
  (`test_sqlalchemy_repository`, `test_pr32_structural_splits`, `test_navigation_imports`,
  `test_paper_stock_broker`, `test_pr35_execution_attempts`, `test_runtime_live`) + scripts
  (`run_trading_option_paper_execution`, `run_trading_paper_execution`).
- `workflows.paper_execution_options`: `workflows/paper_execution.py`, `test_pr32_structural_splits`.
- `workflows.portfolio_sync`: `runtime/preopen_dependencies.py`,
  `runtime/intraday_refresh_dependencies.py`, `workflows/__init__.py`, `workflows/paper_execution.py`,
  + tests (`test_portfolio_sync`, `test_runtime_intraday_live`, `test_runtime_live`).
- `workflows.signal_snapshot`: `runtime/preopen_dependencies.py`, `runtime/smoke_support.py`,
  `workflows/__init__.py`, + tests.
- `workflows.strategy_scoring`: `runtime/preopen_dependencies.py`, `runtime/smoke_support.py`,
  `workflows/__init__.py`, + tests + `scripts/run_trading_live_preopen_order_smoke.py`.
- `workflows.universe_scan`: `runtime/preopen_dependencies.py`, `runtime/smoke_support.py`,
  `workflows/__init__.py`, + tests.

`src/trading/workflows/__init__.py` re-exports all of these public classes; it imports from the
`workflows.<x>` paths, which are now shims, so it keeps working unchanged.

## Internal cross-imports to repoint (between moved files only)

`workflows/paper_execution.py` imports from `paper_execution_options` and `portfolio_sync`. After the
move, repoint those two to the new canonical paths:
`from src.trading.execution.paper_execution_options import …` and
`from src.trading.portfolio.sync import …`. Leave its other imports (e.g.
`from src.trading.workflows.trading_decision import TradingDecisionRecord`, which resolves via the
PR 40 shim; `from src.trading.execution.attempts import …`, already canonical) unchanged — repoint
only paths broken by *this* slice's moves.

## File Map

Create (canonical): `execution/paper_execution.py`, `execution/paper_execution_options.py`,
`signals/pipeline.py`, `strategies/scoring.py`, `portfolio/sync.py`,
`data_sources/universe_scan.py`.

Rewrite as shims (keep old paths): all six `src/trading/workflows/<name>.py`.

Create: `tests/trading/test_pr41_structural_splits.py`.

Modify: `plan/progress_tracker.md`. Unchanged on purpose: `workflows/__init__.py`,
`test_pr32_structural_splits.py` (must still pass), all callers above.

---

## Task 1: Lock the post-move surface with a failing test

**Files:** Create `tests/trading/test_pr41_structural_splits.py`

- [x] Step 1: Assert the new canonical paths exist and export their public surface (one import block
  per moved module, per the Moves table).
- [x] Step 2: Assert the old shim paths still resolve and preserve identity, including the
  `paper_execution._build_option_order_request is paper_execution_options._build_option_order_request`
  contract that `test_pr32` relies on, and
  `workflows.paper_execution.PaperExecutionWorkflow is execution.paper_execution.PaperExecutionWorkflow`.
- [x] Step 3: Import-smoke `runtime/preopen_dependencies.py`,
  `runtime/intraday_refresh_dependencies.py`, `intraday/rebalance.py`, and `workflows.__init__`.
- [x] Step 4: Run `source ~/.venv/bin/activate && pytest tests/trading/test_pr41_structural_splits.py -q`
  — expect failure only because the canonical modules don't exist yet.

## Task 2: Move `paper_execution*` into `execution/`

**Files:** Create `execution/paper_execution.py`, `execution/paper_execution_options.py`; rewrite the
two `workflows/` files as shims.
**Test:** `test_pr41_structural_splits.py`, `test_pr32_structural_splits.py`, `test_pr35_execution_attempts.py`

- [x] Step 1: `git mv src/trading/workflows/paper_execution_options.py src/trading/execution/paper_execution_options.py`
  and `git mv src/trading/workflows/paper_execution.py src/trading/execution/paper_execution.py`.
- [x] Step 2: In `execution/paper_execution.py`, repoint the `paper_execution_options` import to
  `src.trading.execution.paper_execution_options` and the `portfolio_sync` import to
  `src.trading.portfolio.sync` (the latter lands in Task 4 — if doing tasks strictly in order,
  temporarily point at the `workflows.portfolio_sync` shim and fix in Task 4, or do Task 4's move
  first; note the ordering in your commit).
- [x] Step 3: Write `workflows/paper_execution.py` and `workflows/paper_execution_options.py` as
  shims with explicit re-export lists + explicit `__all__` (preserve the surface in the Moves table
  and the `test_pr32` identity helpers). No `import *`, no `globals()`.
- [x] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr41_structural_splits.py tests/trading/test_pr32_structural_splits.py tests/trading/test_pr35_execution_attempts.py -q`.

## Task 3: Move the three pipeline adapters into their capability packages

**Files:** Create `signals/pipeline.py`, `strategies/scoring.py`, `portfolio/sync.py`; rewrite the
three `workflows/` files as shims.
**Test:** `test_pr41_structural_splits.py`, `test_pipeline.py`, `test_portfolio_sync.py`

- [x] Step 1: `git mv` each: `signal_snapshot.py` → `signals/pipeline.py`,
  `strategy_scoring.py` → `strategies/scoring.py`, `portfolio_sync.py` → `portfolio/sync.py`.
- [x] Step 2: Fix any now-relative import each moved file makes (e.g. if `signal_snapshot.py`
  imported a `signals/` sibling via the absolute `src.trading.signals.*` path, that still resolves;
  only repoint imports of *other moved files*). Repoint `data_sources` imports as needed — those
  files stay, so `src.trading.data_sources.*` keeps resolving.
- [x] Step 3: Write the three `workflows/` shims (explicit re-export + `__all__`).
- [x] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr41_structural_splits.py tests/trading/test_pipeline.py tests/trading/test_portfolio_sync.py -q`.

## Task 4: Move `universe_scan` into `data_sources/`, then full verification

**Files:** Create `data_sources/universe_scan.py`; rewrite `workflows/universe_scan.py` as a shim.
Modify `plan/progress_tracker.md`.

- [x] Step 1: `git mv src/trading/workflows/universe_scan.py src/trading/data_sources/universe_scan.py`;
  fix any sibling import; write the `workflows/universe_scan.py` shim.
- [x] Step 2: Confirm `execution/paper_execution.py`'s `portfolio_sync` import points at
  `src.trading.portfolio.sync` (resolve the Task 2 Step 2 ordering note).
- [x] Step 3: `source ~/.venv/bin/activate && python -m compileall -q src`.
- [x] Step 4: Import smoke (one line importing all six new canonical modules + the six shims +
  `runtime.preopen_dependencies`, `runtime.intraday_refresh_dependencies`, `workflows`).
- [x] Step 5: Focused regression suite:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr41_structural_splits.py tests/trading/test_pr40_structural_splits.py tests/trading/test_pr35_execution_attempts.py tests/trading/test_pr32_structural_splits.py tests/trading/test_navigation_imports.py tests/trading/test_pipeline.py tests/trading/test_portfolio_sync.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py -q`.
- [x] Step 6: `grep -rn --include="*.py" "def \|class " src/trading/workflows/` — confirm only shim
  re-exports remain (no class/function bodies left in `workflows/`).
- [x] Step 7: `git diff --check`; prepend a dated `plan/progress_tracker.md` entry.

Expected result: `workflows/` contains only shims; `execution/` now owns the paper-execution
workflow next to `attempts.py`; the pipeline adapters live in their capability packages; all old
paths and seams work; prior structural suites pass.

## Out of scope / follow-ups

- Migrating callers off the `workflows.*` shims (optional later cleanup).
- Retiring `workflows/__init__.py` (needs callers migrated first).
- Splitting the large `execution/paper_execution_options.py` (~865 lines) — separate follow-up.
- PR 42 (morning phases + trade-day relocation), PR 43 (post-close phases + retire `runtime/`).
