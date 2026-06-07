# Trading Runtime And Post-Close Boundary Refactor Design

## Context

The `src/trading` package has already been partially decomposed into focused subpackages such as `signals/`, `risk/`, `intraday/`, `workflows/`, and `repositories/`. Two areas still remain structurally inconsistent with that direction:

- scheduler-facing runtime modules still live flat at the `src/trading` package root
- post-close domain logic (`reflection_pipeline.py` and `strategy_evolution.py`) still lives flat at the same root level

That shape creates two concrete problems:

1. package layout no longer reflects responsibility boundaries
2. unrelated concerns leak across domains, such as `risk/sizing.py` importing `experimental_strategy_weight_cap` from `strategy_evolution.py`

The current layout is workable, but it makes future runtime-phase work and post-close lifecycle work harder to navigate, test, and extend.

## Goals

- Make runtime orchestration a clearly named package-level concern instead of a collection of flat root modules.
- Make reflection and strategy-evolution logic a clearly named post-close domain.
- Remove obvious cross-boundary leaks where non-post-close code depends on post-close pipeline modules for reusable policy helpers.
- Preserve current scheduler, CLI, and test behavior while introducing cleaner canonical import paths.
- Prefer a structure that can support future cleanup without forcing an all-at-once import migration.

## Non-Goals

- This refactor does not change scheduler phase names, CLI flags, or runtime report semantics.
- This refactor does not redesign reflection, learning-factor, or strategy-evolution business logic.
- This refactor does not restructure `signals/`, `risk/`, `intraday/`, `workflows/`, or repository contracts beyond imports needed for the boundary cleanup.
- This refactor does not remove backward-compatible root import shims in the same pass.
- This refactor does not add behavior changes except where needed to preserve existing behavior after module moves.

## Approaches Considered

### Approach 1: Runtime-only package cleanup

Move only `runtime_*` modules into a `runtime/` package and leave post-close modules flat.

Pros:

- lowest immediate change surface
- cleans up the most obvious scheduler-facing clutter

Cons:

- leaves the post-close domain inconsistent with the rest of the package
- does not address the cross-boundary leak from `risk/sizing.py`
- solves only half of the current structural problem

### Approach 2: Runtime plus post-close package split with compatibility shims

Create a `runtime/` package for scheduler/runtime orchestration and a `post_close/` package for reflection/evolution logic. Keep thin compatibility shims where module/package naming allows it, and use `runtime/__init__.py` as the compatibility facade for `src.trading.runtime`.

Pros:

- cleanest responsibility boundaries without breaking current callers
- establishes better canonical import paths immediately
- supports gradual follow-up cleanup without forcing an atomic migration

Cons:

- introduces a short-lived compatibility layer
- requires disciplined import cleanup so new code uses the canonical packages

### Approach 3: Full hard migration with no compatibility layer

Move modules and update every import in one pass, deleting the old root modules immediately.

Pros:

- cleanest final package surface in one pass

Cons:

- highest risk
- broader blast radius across scripts, tests, and scheduler entrypoints
- unnecessary when boundary clarity can be achieved with lower operational risk

## Chosen Approach

Use Approach 2.

This matches the agreed priority order:

1. cleaner responsibility boundaries
2. clearer import and directory semantics
3. lower risk only after the first two concerns are satisfied

The compatibility layer is an implementation device, not a permanent design goal.

## Target Structure

```text
src/trading/
  runtime/
    __init__.py
    facade.py
    dispatch.py
    support.py
    smoke.py
    preopen.py
    manual_review.py
    intraday_refresh.py
    reflection.py
    strategy_evolution.py
  post_close/
    __init__.py
    reflection.py
    strategy_evolution.py
    strategy_policy.py
```

## Boundary Rules

### Runtime package

`src/trading/runtime/` owns:

- scheduler-facing phase entrypoints
- smoke-mode entrypoints
- runtime dependency assembly
- runtime report helpers and execution summaries
- phase dispatch tables and public runtime facade helpers

It does not own reflection or strategy-evolution domain logic. It may depend on the post-close package when running those phases.

### Post-close package

`src/trading/post_close/` owns:

- reflection request/result dataclasses
- reflection pipeline execution
- learning-factor lifecycle helpers
- strategy evolution request/result dataclasses
- strategy proposal and lifecycle logic
- post-close-specific policy helpers

It does not own scheduler dispatch or runtime bootstrap concerns.

### Shared policy helper rule

Reusable rules that are needed outside the post-close pipeline body must not remain buried inside a pipeline module with broader responsibilities.

For this refactor, `experimental_strategy_weight_cap(...)` moves out of `strategy_evolution.py` into `post_close/strategy_policy.py`, and `risk/sizing.py` imports from that focused policy module instead of a pipeline module.

## Canonical Naming

Inside the new runtime package, module names do not use a `live` suffix:

- `runtime.preopen`
- `runtime.manual_review`
- `runtime.intraday_refresh`
- `runtime.reflection`
- `runtime.strategy_evolution`

Rationale:

- the `runtime/` package already establishes the runtime context
- scheduler-facing phase modules are live by default
- `smoke.py` is the actual special case and should remain explicitly named

Function naming should follow the same rule for new canonical APIs:

- `run_preopen_once(...)`
- `run_manual_review_once(...)`
- `run_intraday_refresh_once(...)`
- `run_reflection_once(...)`
- `run_strategy_evolution_once(...)`

Backward-compatible `run_live_*` exports may remain temporarily through the root-level shims and, if useful, through re-exports in the new modules during the transition.

## Compatibility Strategy

Existing root modules remain in place for this refactor but become thin re-export shims, except for `src/trading/runtime.py`:

- `src/trading/runtime_dispatch.py`
- `src/trading/runtime_smoke.py`
- `src/trading/runtime_support.py`
- `src/trading/runtime_live.py`
- `src/trading/runtime_manual_review_live.py`
- `src/trading/runtime_intraday_live.py`
- `src/trading/runtime_reflection_live.py`
- `src/trading/runtime_strategy_evolution_live.py`
- `src/trading/reflection_pipeline.py`
- `src/trading/strategy_evolution.py`

`src/trading/runtime.py` is the exception. Once `src/trading/runtime/` exists, Python resolves `src.trading.runtime` through the package, so the compatibility/public facade must move into `src/trading/runtime/__init__.py` instead of staying as a root module.

Shim rules:

- no business logic
- no independent helper implementations
- only imports and re-exports from the canonical package modules
- comments/docstrings should make their compatibility purpose explicit

New or edited internal imports in this refactor should prefer canonical package paths instead of the shims.

## Migration Plan

### Phase 1: Create canonical packages

- add `src/trading/runtime/`
- add `src/trading/post_close/`
- move the public `run_job_phase(...)`, `run_smoke_mode(...)`, `TRADING_JOB_PHASES`, and `AVAILABLE_SMOKE_MODES` surface into `src/trading/runtime/__init__.py`
- move runtime implementations into canonical runtime modules
- move reflection/evolution implementations into canonical post-close modules

### Phase 2: Extract the cross-boundary helper

- move `experimental_strategy_weight_cap(...)` into `src/trading/post_close/strategy_policy.py`
- update `risk/sizing.py` and any other callers to import from the focused policy module

### Phase 3: Flip internal imports

- update runtime, repository, script, and test imports to use canonical package paths where practical
- leave external compatibility paths working

### Phase 4: Convert root modules into shims

- replace moved root modules with thin re-export compatibility wrappers
- delete `src/trading/runtime.py` after its public facade is recreated in `src/trading/runtime/__init__.py`
- keep current public import paths working for scheduler jobs, scripts, and existing tests

### Phase 5: Verify behavior and docs

- run focused runtime/post-close/risk tests
- run broader trading and script tests
- update repo overview and progress tracker to describe the new package boundaries

## Files Expected To Move Or Be Introduced

### New canonical modules

- `src/trading/runtime/__init__.py`
- `src/trading/runtime/facade.py`
- `src/trading/runtime/dispatch.py`
- `src/trading/runtime/support.py`
- `src/trading/runtime/smoke.py`
- `src/trading/runtime/preopen.py`
- `src/trading/runtime/manual_review.py`
- `src/trading/runtime/intraday_refresh.py`
- `src/trading/runtime/reflection.py`
- `src/trading/runtime/strategy_evolution.py`
- `src/trading/post_close/__init__.py`
- `src/trading/post_close/reflection.py`
- `src/trading/post_close/strategy_evolution.py`
- `src/trading/post_close/strategy_policy.py`

### Existing root modules reduced to shims

- `src/trading/runtime_dispatch.py`
- `src/trading/runtime_support.py`
- `src/trading/runtime_smoke.py`
- `src/trading/runtime_live.py`
- `src/trading/runtime_manual_review_live.py`
- `src/trading/runtime_intraday_live.py`
- `src/trading/runtime_reflection_live.py`
- `src/trading/runtime_strategy_evolution_live.py`
- `src/trading/reflection_pipeline.py`
- `src/trading/strategy_evolution.py`

### Existing root module removed because of package-name collision

- `src/trading/runtime.py`

## Testing Strategy

Focused verification should cover:

- runtime facade and dispatch behavior
- preopen/manual-review/intraday/reflection/strategy-evolution runtime tests
- reflection and strategy-evolution pipeline tests
- risk sizing tests that cover experimental strategy weight handling
- script tests for runtime CLI and smoke entrypoints
- navigation/import tests that ensure both canonical and compatibility paths remain valid where expected

Broader verification should include at least:

- `tests/trading`
- runtime-related script tests
- `git diff --check`

## Risks And Mitigations

### Risk: import churn breaks scheduler/scripts/tests

Mitigation:

- keep root shims
- keep scheduler/CLI public APIs unchanged
- run targeted runtime and script tests first

### Risk: canonical runtime package collides with the existing `runtime.py` module

Mitigation:

- move the public facade into `src/trading/runtime/__init__.py`
- keep `facade.py` as an internal organization module if needed, but treat the package entrypoint as the stable public import path

### Risk: boundary cleanup accidentally changes behavior

Mitigation:

- do not change runtime report schemas or phase names
- keep moves mechanical where possible
- isolate the one explicit boundary fix: `experimental_strategy_weight_cap(...)`

## Success Criteria

- `src/trading/runtime/` is the canonical home for runtime orchestration modules.
- `src/trading/post_close/` is the canonical home for reflection and strategy-evolution domain logic.
- `risk/sizing.py` no longer imports a policy helper from a post-close pipeline module.
- internal imports favor canonical package paths.
- root-level compatibility imports still work.
- scheduler, CLI, and test behavior remain unchanged after the refactor.
