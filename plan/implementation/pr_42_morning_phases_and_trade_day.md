# PR 42 Morning Phases + Trade-Day Relocation Implementation Plan

> Slice 3 of the trading workflow/component topology refactor. Steps use checkbox (`- [ ]`) syntax.
> **Depends on PR 40 + PR 41 having landed.** This is the highest-blast-radius slice — it touches the
> scheduler entry surface and the dependency container that manual-review reuses by reference. Move
> in small steps and run verification after each task.

**Goal:** Stand up the `phases/` orchestration layer for the three workflows that share the
universe→signal→strategy→risk→decision→execution backbone — `preopen`, `manual_review`, `intraday` —
and first pull the two *shared* utilities currently stranded in `runtime/` (`trade_day`,
`lookahead_risk`) down into their capability homes. After this slice, `runtime/` holds only the
post-close phase shells and the cross-phase `_shell` (both retired in PR 43).

**Architecture:** Move-and-reexport, same mechanics as PR 40/41. Each moved module gets a canonical
home; the old `runtime/<name>.py` path stays as a shim re-exporting the public surface. Callers
(scheduler jobs, `dispatch.py`, smoke) are **not** migrated — they keep importing the `runtime.*`
paths, which resolve through shims.

**Tech Stack:** Python, pytest. No dependency, schema, or behavior changes.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/design/2026-06-26-trading-workflow-component-topology.md` (PR 42 is slice 3; read the
   findings on manual_review reusing preopen's dependency container, and the scope refinement on
   `trade_day`)
3. `src/trading/runtime/README.md` (the existing phase map — this slice makes the folders match it)
4. `plan/implementation/pr_41_dissolve_workflows_package.md` (same mechanics)
5. `plan/progress_tracker.md` Recent section only

## Guardrails

- **Pure structural refactor.** Verbatim moves; only import statements change.
- **Do not migrate caller import paths** (scheduler jobs, `dispatch.py`, `facade.py`, smoke modules
  keep importing `src.trading.runtime.*`, resolving through shims).
- **Preserve monkeypatch seams.** Before editing, run
  `grep -rn 'monkeypatch.setattr("src.trading.runtime' tests` and ensure every patched attribute
  still exists on its shim after the move (e.g. preopen/intraday runtime patches in
  `test_runtime_live.py` / `test_runtime_intraday_live.py`). This is the #1 risk in this slice.
- **The preopen↔manual_review reuse must stay intact.** `build_live_manual_review_dependencies()`
  calls `build_live_preopen_dependencies()`. Both files move in this slice — repoint the call to the
  new canonical preopen path, do not let it dangle on a shim→shim hop.
- **`import *` drops underscore helpers; no `globals()` pattern.** Explicit re-export lists in shims.
- Do **not** touch the post-close phases (`reflection`, `strategy_evolution`, `replay`), `facade.py`,
  `dispatch.py`, `support.py`, or `smoke*` — those are PR 43.

## Moves

### Shared utilities out of `runtime/` (Task 1 — do these first)

| Source | Canonical home | Importers to repoint |
|---|---|---|
| `runtime/trade_day.py` | `src/trading/trade_day.py` (package root — neutral, no heavy imports) | `repositories/mixins/{signals,strategy,intraday,risk}.py`, `runtime/reflection.py` |
| `runtime/lookahead_risk.py` | `src/trading/risk/lookahead_risk.py` | `runtime/preopen*.py`, `runtime/intraday_refresh*.py` (whichever import it) |

`trade_day` at the package root removes the `repositories → runtime` dependency that forced the
`runtime/__init__.py` `__getattr__` hack. Leave a shim at `runtime/trade_day.py`. After the repointing,
**attempt** to restore eager imports in `runtime/__init__.py` and remove `__getattr__`; if any import
cycle remains (verify with the import smoke), leave the lazy form and note it — its full cleanup lands
in PR 43 when `_shell` moves. (`risk/` already has a `lookahead.py`; name the moved file
`lookahead_risk.py` to avoid collision.)

### Morning phase subpackages (Tasks 2–4)

| Phase subpackage | Source files |
|---|---|
| `phases/preopen/` | `runtime/{preopen,preopen_runner,preopen_dependencies,preopen_risk}.py` |
| `phases/manual_review/` | `runtime/manual_review.py` + `manual_review/{requests,sqlalchemy}.py` (the feature folder) |
| `phases/intraday/` | `runtime/{intraday_refresh,intraday_refresh_runner,intraday_refresh_dependencies,intraday_refresh_helpers}.py` + `intraday/{rebalance,news_alerts,signals}.py` |

Inside each subpackage, drop the redundant prefix (e.g. `preopen/runner.py`, `preopen/dependencies.py`,
`preopen/risk.py`, `preopen/__init__.py` as the facade; `intraday/refresh.py`, `intraday/runner.py`,
`intraday/rebalance.py`, …). Keep `phases/__init__.py` minimal. Leave a shim at every old
`runtime/<name>.py` and `intraday/<name>.py` / `manual_review/<name>.py` path.

## Caller surface (keep resolving via shims — re-grep at implementation time, do NOT edit)

Re-derive precisely with:
`grep -rn --include="*.py" "runtime.preopen\|runtime.manual_review\|runtime.intraday_refresh\|trading.intraday\|trading.manual_review\|runtime.lookahead_risk" src tests scripts`.
Known key importers: `src/scheduler/jobs/{trading_preopen_job,manual_ticker_review_job,intraday_signal_refresh_job}.py`,
`src/trading/runtime/dispatch.py`, `src/trading/runtime/smoke_fixture_modes.py`,
`src/trading/runtime/smoke_support.py`, and the `test_runtime_*_live.py` suites.

## File Map

Create: `src/trading/trade_day.py`; `src/trading/risk/lookahead_risk.py`; the `phases/` package with
`__init__.py`, and `phases/{preopen,manual_review,intraday}/` subpackages with their moved modules.
Rewrite as shims: every old `runtime/<name>.py`, `intraday/<name>.py`, `manual_review/<name>.py`
listed above. Possibly modify `runtime/__init__.py` (remove `__getattr__` if cycle-free).
Create: `tests/trading/test_pr42_structural_splits.py`. Modify `plan/progress_tracker.md`.

---

## Task 1: Relocate `trade_day` and `lookahead_risk` out of `runtime/`

**Files:** Create `src/trading/trade_day.py`, `src/trading/risk/lookahead_risk.py`; shims at the old
paths; repoint importers.
**Test:** `test_pr36_trade_day_window.py`, `test_pr42_structural_splits.py` (new), `test_runtime_reflection_live.py`

- [ ] Step 1: Write a failing `test_pr42_structural_splits.py` asserting
  `from src.trading.trade_day import trade_date_for, local_day_bounds_utc` and
  `from src.trading.risk.lookahead_risk import <public surface>` resolve, and that the old
  `runtime.trade_day` / `runtime.lookahead_risk` paths still resolve to the same objects.
- [ ] Step 2: `git mv src/trading/runtime/trade_day.py src/trading/trade_day.py`. Repoint the four
  repository mixins (`signals,strategy,intraday,risk`) and `runtime/reflection.py` to
  `from src.trading.trade_day import …`. Write a shim at `runtime/trade_day.py`.
- [ ] Step 3: `git mv src/trading/runtime/lookahead_risk.py src/trading/risk/lookahead_risk.py`;
  repoint its importers; write a shim at `runtime/lookahead_risk.py`.
- [ ] Step 4: Try removing `__getattr__` from `runtime/__init__.py` (restore eager
  `from .facade import …` / `from .smoke import …`). Run the import smoke
  (`python -c "import src.trading.repositories.sqlalchemy, src.trading.runtime, src.trading.runtime.reflection"`).
  If it raises a circular import, revert to the lazy `__getattr__` and leave a comment that PR 43
  finishes the cleanup.
- [ ] Step 5: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr42_structural_splits.py tests/trading/test_pr36_trade_day_window.py tests/trading/test_runtime_reflection_live.py tests/trading/test_navigation_imports.py -q`.

## Task 2: `phases/preopen/`

**Files:** Create `phases/__init__.py`, `phases/preopen/{__init__,runner,dependencies,risk}.py`;
shims at the four `runtime/preopen*.py` paths.
**Test:** `test_pr42_structural_splits.py`, `test_runtime_live.py`

- [ ] Step 1: `git mv` the four files into `phases/preopen/` with prefixes dropped; the public facade
  (`run_preopen_once`, `run_live_preopen_once`, `build_live_preopen_dependencies`) lives in
  `phases/preopen/__init__.py` (or `phases/preopen/facade.py` re-exported by `__init__`).
- [ ] Step 2: Repoint intra-preopen imports to the new subpackage paths. Leave imports of capability
  packages (`signals`, `strategies`, `risk`, `execution`, `portfolio`, `decision`, `risk.lookahead_risk`)
  on their canonical paths.
- [ ] Step 3: Write shims at `runtime/{preopen,preopen_runner,preopen_dependencies,preopen_risk}.py`
  with explicit re-export lists + `__all__`. These preserve the `dispatch.py` and scheduler-job
  import paths and any `test_runtime_live.py` monkeypatch targets.
- [ ] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr42_structural_splits.py tests/trading/test_runtime_live.py -q`.

## Task 3: `phases/manual_review/`

**Files:** Create `phases/manual_review/{__init__,requests,sqlalchemy}.py` (or similar); shims at
`runtime/manual_review.py` and `manual_review/{requests,sqlalchemy}.py`.
**Test:** `test_pr42_structural_splits.py`, `test_runtime_manual_review_live.py`

- [ ] Step 1: `git mv runtime/manual_review.py` and the `manual_review/` feature folder into
  `phases/manual_review/`.
- [ ] Step 2: Repoint `build_live_manual_review_dependencies()`'s call to
  `build_live_preopen_dependencies` to the new `phases/preopen/` canonical path (Task 2). This is the
  reuse seam — verify it binds the real function, not a shim attribute.
- [ ] Step 3: Write shims at the old `runtime/manual_review.py` and `manual_review/*.py` paths.
- [ ] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr42_structural_splits.py tests/trading/test_runtime_manual_review_live.py -q`.

## Task 4: `phases/intraday/`, then full verification

**Files:** Create `phases/intraday/{__init__,refresh,runner,dependencies,helpers,rebalance,news_alerts,signals}.py`;
shims at the `runtime/intraday_refresh*.py` and `intraday/*.py` paths. Modify `plan/progress_tracker.md`.
**Test:** `test_pr42_structural_splits.py`, `test_runtime_intraday_live.py`, `test_intraday_rebalance.py`

- [ ] Step 1: `git mv` the four `runtime/intraday_refresh*.py` files and the three `intraday/*.py`
  files into `phases/intraday/` with prefixes dropped; repoint intra-phase imports.
- [ ] Step 2: Write shims at all old `runtime/intraday_refresh*.py` and `intraday/{rebalance,news_alerts,signals}.py`
  paths (note: `intraday/rebalance.py` is imported by several callers and `test_pr35`/`test_intraday_rebalance`
  — preserve its surface incl. `IntradayRebalancePipeline` and the `execution.attempts` re-exports it uses).
- [ ] Step 3: `source ~/.venv/bin/activate && python -m compileall -q src`.
- [ ] Step 4: Import smoke importing every new `phases/` module + every shim + the three scheduler
  jobs + `runtime.dispatch`.
- [ ] Step 5: Focused regression suite:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr42_structural_splits.py tests/trading/test_pr41_structural_splits.py tests/trading/test_pr40_structural_splits.py tests/trading/test_navigation_imports.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_runtime_manual_review_live.py tests/trading/test_intraday_rebalance.py tests/trading/test_pr35_execution_attempts.py tests/test_scheduler_jobs.py -q`.
- [ ] Step 6: `git diff --check`; prepend a dated `plan/progress_tracker.md` entry.

Expected result: the three morning workflows read top-down under `phases/`; `trade_day` and
`lookahead_risk` are in neutral capability homes; the scheduler entry surface, the preopen↔manual
reuse, and all monkeypatch seams still work; `runtime/` now holds only the post-close shells + the
`_shell` files (PR 43's scope).

## Out of scope / follow-ups

- PR 43: `phases/{reflection,strategy_evolution,replay}/` + `phases/_shell/`, then retire `runtime/`
  and remove `__getattr__` if Task 1 left it.
- Migrating callers off the `runtime.*` shims.
- Splitting the large `phases/intraday/helpers.py` (~495 lines) / `preopen/risk.py` (~630) — separate
  follow-ups per the topology doc's non-goals.
