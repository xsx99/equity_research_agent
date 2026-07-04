# PR 43 Post-Close Phases + `_shell`, Retire `runtime/` Implementation Plan

> Slice 4 (final) of the trading workflow/component topology refactor. Steps use checkbox (`- [ ]`)
> syntax. **Depends on PR 40 + 41 + 42 having landed.** After this slice, `runtime/` holds no real
> code — only its stable public `__init__.py` surface plus compatibility shims — and the `phases/`
> layer is complete.

**Goal:** Move the post-close workflows (`reflection`, `strategy_evolution`, `replay`) into
`phases/`, move the cross-phase scheduler shell (`facade`, `dispatch`, `support`, `smoke*`) into
`phases/_shell/`, and reduce `runtime/` to a thin compatibility surface. Also relocate the one
remaining stranded shared util (`post_close/strategy_policy.py`) into a capability package.

**Architecture:** Move-and-reexport, same mechanics as PR 40–42. Each moved module gets a canonical
home; old paths stay as shims. `runtime/__init__.py` is kept as the stable public facade
(`TRADING_JOB_PHASES`, `run_job_phase`, `AVAILABLE_SMOKE_MODES`, `run_smoke_mode`) — re-exporting from
`phases/_shell/` — because scheduler jobs and tests import those names from `src.trading.runtime`.

**Tech Stack:** Python, pytest. No dependency, schema, or behavior changes.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/design/2026-06-26-trading-workflow-component-topology.md` (PR 43 is the final slice; note the
   findings on reflection→evolution being a one-way data dependency and replay being smoke-only)
3. `src/trading/runtime/README.md` (phase map; `dispatch.py`/`facade.py`/`smoke*` roles)
4. `plan/implementation/pr_42_morning_phases_and_trade_day.md` (same mechanics; `phases/` already
   exists from PR 42)
5. `plan/progress_tracker.md` Recent section only

## Guardrails

- **Pure structural refactor.** Verbatim moves; only import statements change.
- **Preserve `src.trading.runtime`'s public surface.** `from src.trading.runtime import run_job_phase, run_smoke_mode, TRADING_JOB_PHASES, AVAILABLE_SMOKE_MODES` must keep working — scheduler jobs and many tests depend on it. Keep `runtime/__init__.py`; only change where it imports *from*.
- **Do not migrate caller import paths** (scheduler jobs, repositories, `learning/`, `risk/`,
  `strategies/`, smoke scripts keep their `runtime.*` / `post_close.*` / `replay.*` imports, resolving
  through shims).
- **The record-type shims are load-bearing and permanent.** `post_close/reflection.py`
  (`DailyReflectionRecord`, `LearningFactorRecord`, `derive_learning_factor_status`) and
  `replay/outcomes.py` (`CandidateOutcomeEvaluationRecord`, `OutcomeEvaluator`, `PricePoint`) are
  imported by the repository layer (`_base.py`, `_base_records.py`, `in_memory.py`,
  `mixins/reflection.py`), `learning/apply.py`, and `strategies/calibration.py`. Their shims must
  re-export the full surface those callers use. Full caller migration is **out of scope** (a later
  cleanup); the shims stay.
- **Preserve monkeypatch seams.** Run `grep -rn 'monkeypatch.setattr("src.trading.runtime' tests`
  (smoke/post-close/reflection live tests) and ensure patched attributes still exist on shims.
- **`import *` drops underscore helpers; no `globals()` pattern.** Explicit re-export lists in shims.

## Moves

| Phase subpackage | Source files |
|---|---|
| `phases/reflection/` | `runtime/reflection.py` + `post_close/reflection.py` |
| `phases/strategy_evolution/` | `runtime/strategy_evolution.py` + `post_close/strategy_evolution.py` |
| `phases/replay/` | `replay/{historical,outcomes}.py` (smoke-only — note in `__init__` docstring) |
| `phases/_shell/` | `runtime/{facade,dispatch,support,smoke,smoke_entrypoints,smoke_fixture_modes,smoke_post_close_modes,smoke_support}.py` |

**Capability move (not a phase):** `post_close/strategy_policy.py` → `strategies/policy.py`.
Rationale: `experimental_strategy_weight_cap` is imported by `risk/sizing.py`, so it is a shared
policy util, not strategy-evolution-only. Putting it under `phases/strategy_evolution/` would create a
`risk → phases` dependency — the same layering smell PR 42 fixed for `trade_day`. Leave a shim at
`post_close/strategy_policy.py`.

Inside each phase subpackage, drop redundant prefixes (e.g. `reflection/__init__.py` as the runtime
facade re-exporting the pipeline; `replay/historical.py`, `replay/outcomes.py`). `phases/_shell/`
keeps `facade.py`, `dispatch.py`, `support.py`, and the smoke modules.

## Caller surface (keep resolving via shims — re-grep at implementation time, do NOT edit)

- `runtime.reflection` / `runtime.strategy_evolution`: `scheduler/jobs/{trading_reflection_job,strategy_evolution_job}.py`, `runtime/dispatch.py`, + `test_runtime_{reflection,strategy_evolution}_live.py`.
- `post_close.reflection`: `learning/apply.py`, `repositories/{_base,_base_records,in_memory}.py`, `repositories/mixins/reflection.py`, + 6 tests.
- `post_close.strategy_evolution`: `repositories/in_memory.py`, + 4 tests.
- `replay.historical`: `repositories/in_memory.py`, + `test_historical_replay.py`.
- `replay.outcomes`: `strategies/calibration.py`, `repositories/{_base,_base_records,in_memory}.py`, `post_close/strategy_evolution.py`, + 6 tests.
- `runtime.facade` / `runtime.__init__` surface: scheduler jobs (via `run_job_phase`), `test_scheduler_jobs.py`, `scripts/run_trading_*` , `test_run_trading_smoke_test.py`.
- `runtime.support` / `runtime.smoke*`: most runtime files + smoke scripts/tests.

## File Map

Create canonical: `phases/{reflection,strategy_evolution,replay}/` modules; `phases/_shell/` modules;
`strategies/policy.py`. Rewrite as shims: every old `runtime/<name>.py`, `post_close/<name>.py`,
`replay/<name>.py`. Modify `runtime/__init__.py` (repoint imports to `phases/_shell/`; remove
`__getattr__` if the cycle is gone — see Task 4). Create `tests/trading/test_pr43_structural_splits.py`.
Modify `plan/progress_tracker.md`.

---

## Task 1: Lock the post-move surface + relocate `strategy_policy`

**Files:** Create `tests/trading/test_pr43_structural_splits.py`, `strategies/policy.py`; shim
`post_close/strategy_policy.py`.

- [x] Step 1: Write a failing test asserting the new canonical paths resolve
  (`phases.reflection`, `phases.strategy_evolution`, `phases.replay`, `phases._shell.facade`,
  `phases._shell.dispatch`, `strategies.policy`) and that the old `runtime.*` / `post_close.*` /
  `replay.*` paths still resolve to the same objects. Include an assertion that
  `from src.trading.runtime import run_job_phase, run_smoke_mode, TRADING_JOB_PHASES, AVAILABLE_SMOKE_MODES`
  still works.
- [x] Step 2: `git mv src/trading/post_close/strategy_policy.py src/trading/strategies/policy.py`;
  repoint `risk/sizing.py` to `from src.trading.strategies.policy import experimental_strategy_weight_cap`;
  write a shim at `post_close/strategy_policy.py`.
- [x] Step 3: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr43_structural_splits.py tests/trading/test_navigation_imports.py -q`
  — expect failure only on the not-yet-created phase/_shell paths.

## Task 2: `phases/reflection/` and `phases/strategy_evolution/`

**Files:** Create the two phase subpackages; shim `runtime/{reflection,strategy_evolution}.py` and
`post_close/{reflection,strategy_evolution}.py`.
**Test:** `test_pr43_structural_splits.py`, `test_reflection_pipeline.py`, `test_strategy_evolution.py`,
`test_runtime_reflection_live.py`, `test_runtime_strategy_evolution_live.py`

- [x] Step 1: `git mv runtime/reflection.py` + `post_close/reflection.py` into `phases/reflection/`;
  `git mv runtime/strategy_evolution.py` + `post_close/strategy_evolution.py` into
  `phases/strategy_evolution/`. Drop prefixes; the runtime facade lives in each subpackage `__init__`.
- [x] Step 2: Repoint intra-phase imports. `phases/strategy_evolution/` consumes reflection record
  types and `replay.outcomes` — point those at `phases/reflection/` (sibling) and the
  `replay.outcomes` shim (or the new `phases/replay/` if Task 3 done first); leave capability imports
  (`strategies`, `repositories`) canonical.
- [x] Step 3: Write shims at `post_close/reflection.py` and `post_close/strategy_evolution.py` with
  **explicit** re-export lists covering the full record-type surface the repository/learning callers
  import (see Guardrails). Write shims at `runtime/{reflection,strategy_evolution}.py`.
- [x] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr43_structural_splits.py tests/trading/test_reflection_pipeline.py tests/trading/test_strategy_evolution.py tests/trading/test_runtime_reflection_live.py tests/trading/test_runtime_strategy_evolution_live.py tests/trading/test_learning_apply.py tests/trading/test_learning_factors.py -q`.

## Task 3: `phases/replay/`

**Files:** Create `phases/replay/{__init__,historical,outcomes}.py`; shim `replay/{historical,outcomes}.py`.
**Test:** `test_pr43_structural_splits.py`, `test_historical_replay.py`, `test_outcome_evaluator.py`,
`test_confidence_calibration.py`, `test_candidate_repository.py`

- [x] Step 1: `git mv replay/historical.py replay/outcomes.py` into `phases/replay/`. Add a docstring
  in `phases/replay/__init__.py` stating it is smoke-only / not scheduler-wired (backlog #6).
- [x] Step 2: Write shims at `replay/historical.py` and `replay/outcomes.py` with explicit re-export
  lists covering `CandidateOutcomeEvaluationRecord`, `OutcomeEvaluator`, `PricePoint`, the replay
  runner/result types, and any helper the repository/calibration callers use.
- [x] Step 3: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr43_structural_splits.py tests/trading/test_historical_replay.py tests/trading/test_outcome_evaluator.py tests/trading/test_confidence_calibration.py tests/trading/test_candidate_repository.py -q`.

## Task 4: `phases/_shell/`, reduce `runtime/` to a compatibility surface, full verification

**Files:** Create `phases/_shell/` modules; shim the old `runtime/{facade,dispatch,support,smoke*}.py`;
rewrite `runtime/__init__.py`. Modify `plan/progress_tracker.md`.
**Test:** `test_scheduler_jobs.py`, `test_run_trading_smoke_test.py`, full structural suite

- [x] Step 1: `git mv` the eight shell files into `phases/_shell/`. In `phases/_shell/dispatch.py`,
  repoint the phase-handler imports to the canonical `phases/{preopen,manual_review,intraday,reflection,strategy_evolution}/`
  paths (and `phases/replay/` for the smoke handler). In `phases/_shell/smoke_fixture_modes.py` /
  `smoke_post_close_modes.py` / `smoke_support.py`, repoint phase/dependency imports to canonical
  `phases/*` paths.
- [x] Step 2: Write shims at `runtime/{facade,dispatch,support,smoke,smoke_entrypoints,smoke_fixture_modes,smoke_post_close_modes,smoke_support}.py`.
- [x] Step 3: Rewrite `runtime/__init__.py` to re-export the stable surface from `phases/_shell/`
  (`from src.trading.phases._shell.facade import TRADING_JOB_PHASES, run_job_phase, run_smoke_mode`,
  `from src.trading.phases._shell.smoke import AVAILABLE_SMOKE_MODES`). Since PR 42 relocated
  `trade_day` (so repositories no longer import `runtime`), the `repositories → runtime` cycle is
  gone — **attempt eager imports and remove the `__getattr__` hack**. Verify with import smoke; if a
  cycle still appears, keep the lazy form and document why.
- [x] Step 4: `source ~/.venv/bin/activate && python -m compileall -q src`.
- [x] Step 5: Import smoke: import the three scheduler jobs, `src.trading.runtime` (assert the four
  public names), every `phases/_shell/*` and phase module, and the repository layer.
- [x] Step 6: Full focused regression suite:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr43_structural_splits.py tests/trading/test_pr42_structural_splits.py tests/trading/test_pr41_structural_splits.py tests/trading/test_pr40_structural_splits.py tests/trading/test_navigation_imports.py tests/test_scheduler_jobs.py tests/scripts/test_run_trading_smoke_test.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_runtime_reflection_live.py tests/trading/test_runtime_strategy_evolution_live.py tests/trading/test_runtime_manual_review_live.py -q`,
  then a full `source ~/.venv/bin/activate && pytest -q` (note any external-DB tests blocked by the
  sandbox, consistent with prior slices).
- [x] Step 7: `grep -rn --include="*.py" "def \|class " src/trading/runtime/` and
  `… src/trading/post_close/ src/trading/replay/` — confirm only shim re-exports remain (no bodies).
- [x] Step 8: `git diff --check`; prepend a dated `plan/progress_tracker.md` entry noting the topology
  refactor (PR 40–43) is structurally complete.

Expected result: all six workflows read top-down under `phases/`; `_shell` owns the scheduler
dispatch; `runtime/` is a compatibility surface only; the public facade, smoke modes, scheduler jobs,
record-type shims, and monkeypatch seams all still work.

## Out of scope / follow-ups

- **Caller migration off the shims.** `runtime/`, `post_close/`, `replay/`, and `workflows/` remain as
  shim packages. Migrating callers onto the canonical `phases.*` / capability paths (and then deleting
  the shim packages) is a separate, optional mechanical cleanup — worth a single sweeping PR once the
  structure has settled.
- **Extracting shared record types** (`DailyReflectionRecord`, `LearningFactorRecord`,
  `CandidateOutcomeEvaluationRecord`) into a dedicated contracts package, if the wide repository
  dependency on phase modules later proves awkward. Not needed now — the shims absorb it.
- Large-file splits (`paper_execution_options.py`, `smoke_fixture_modes.py` ~791, etc.) per the
  topology doc's non-goals.
