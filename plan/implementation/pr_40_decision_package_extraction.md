# PR 40 Decision Package Extraction (Pilot) Implementation Plan

> **For agentic workers:** This is the pilot slice of the trading workflow/component topology
> refactor. Steps use checkbox (`- [ ]`) syntax for tracking. Implement task-by-task and run the
> listed verification after each task.

**Goal:** Extract the trade-decision components out of the `src/trading/workflows/` dumping ground
into a focused `src/trading/decision/` capability package, with the `option_strategy_builder` helper
family promoted from 5 flat prefix-named files into a nested subpackage — while preserving every
import path real callers use, with zero behavior change.

**Architecture:** Move-and-reexport. The moved code lives at new canonical paths under
`src/trading/decision/`. The two original `workflows/` paths that production code and identity tests
depend on (`trading_decision`, `option_strategy_builder`) stay as thin compatibility shims that
re-export from the new locations. Callers are **not** migrated in this slice — the shims are the
compatibility layer (same pattern as `src/web/routers/today_loaders.py` from PR 33).

**Tech Stack:** Python, pytest. No new dependencies. No SQLAlchemy, runtime, or workflow behavior
changes.

**Why this slice first:** It is the smallest, highest-clarity move; it is the example that motivated
the topology doc; and it validates the move-and-reexport mechanics (shims, identity preservation,
the monkeypatch seam) before PR 41/42 ride on the same pattern.

> **Update 2026-06-27 (after PR 35 landed):** PR 35 replaced the `option_strategy_builder.py` hub's
> dynamic `__all__ = [name for name in globals() …]` with an **explicit** name list, and added
> `tests/trading/test_pr34_structural_splits.py::test_compatibility_hub_all_lists_only_intended_exports`,
> which reads the hub's `__file__` and asserts `"globals()"` is **not** present and that specific
> names are in `__all__`. This plan has been amended accordingly: every hub/shim below uses an
> explicit `__all__`, never the `globals()` pattern. PR 35 also added a `paper_trade_authorized`
> field to `TradingDecisionRecord` (additive — does not affect the move) and did not add any new
> caller of these modules.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md` (G2, G5, G8 touch the decision path)
3. `plan/design/2026-06-26-trading-workflow-component-topology.md` (the parent design; PR 40 is slice 1)
4. `plan/implementation/pr_34_residual-helper-hub-split.md` (the prior split this builds on)
5. `plan/progress_tracker.md` Recent section only

## Guardrails

- **Pure structural refactor.** Move code verbatim; the only edits are import statements that must
  point at the new module locations.
- **Do not migrate caller import paths.** Every `from src.trading.workflows.trading_decision import …`
  and `from src.trading.workflows.option_strategy_builder import …` in production code, scripts, and
  tests stays exactly as-is and keeps resolving through the shim. Migrating callers is explicitly a
  later, optional cleanup — not this slice.
- **Preserve object identity across re-exports.** `test_pr32` asserts
  `trading_decision._build_option_strategy_payloads is option_strategy_builder._build_option_strategy_payloads`.
  Achieve this by importing each name from one canonical home and re-exporting it; never redefine a
  helper in two places.
- **`import *` will silently drop the helpers.** Every moved helper is underscore-prefixed, so
  `from … import *` will NOT re-export them unless an explicit `__all__` is present. Shims must use
  explicit `from … import (…)` name lists (or set/extend `__all__`). Verify with the structural
  tests, not by eyeballing.
- Do not combine this slice with large-file splitting, dead-code deletion, naming cleanup, or any
  `workflows/` move beyond the decision components (those are PR 41/42).
- Do not touch `paper_execution*.py`, `brokers/`, or any other `workflows/` file in this PR.

## Naming decisions (pinned for this slice)

- Package: `src/trading/decision/`
- Canonical pipeline module: `src/trading/decision/pipeline.py` (moved from
  `src/trading/workflows/trading_decision.py`)
- Builder subpackage: `src/trading/decision/option_strategy_builder/` with modules
  `__init__.py` (the hub), `policy.py`, `chain.py`, `payload.py`, `evidence.py`
  (moved from the four `option_strategy_builder_{policy,chain,payload,evidence}.py` files;
  the `option_strategy_builder_` prefix is dropped inside the subpackage).
- `src/trading/decision/__init__.py` re-exports the public pipeline surface
  (`TradingDecisionPipeline`, `TradingDecisionPipelineResult`, `TradingDecisionRecord`) and the
  builder hub, so `from src.trading.decision import TradingDecisionPipeline` works.

## Dependency direction (must stay one-directional, no cycle)

```
decision/option_strategy_builder/{policy,chain,payload,evidence}.py   (leaf; chain→policy, payload→{chain,policy})
        ▲
decision/pipeline.py            imports the builder subpackage
        ▲
decision/__init__.py            imports pipeline + builder hub
        ▲
workflows/trading_decision.py   shim → re-exports from decision.pipeline
workflows/option_strategy_builder.py  shim → re-exports from decision.option_strategy_builder
```

`pipeline.py` imports builder helpers **directly from `src.trading.decision.option_strategy_builder`**
(the canonical hub), not from the `workflows` shim — this avoids a shim→shim hop and keeps identity
clean.

## File Map

Create (canonical package):
- `src/trading/decision/__init__.py`
- `src/trading/decision/pipeline.py`
- `src/trading/decision/option_strategy_builder/__init__.py`
- `src/trading/decision/option_strategy_builder/policy.py`
- `src/trading/decision/option_strategy_builder/chain.py`
- `src/trading/decision/option_strategy_builder/payload.py`
- `src/trading/decision/option_strategy_builder/evidence.py`

Rewrite as shims (keep old paths working):
- `src/trading/workflows/trading_decision.py`
- `src/trading/workflows/option_strategy_builder.py`

Delete (no production caller; only `test_pr34` referenced these flat paths — repointed in Task 4):
- `src/trading/workflows/option_strategy_builder_policy.py`
- `src/trading/workflows/option_strategy_builder_chain.py`
- `src/trading/workflows/option_strategy_builder_payload.py`
- `src/trading/workflows/option_strategy_builder_evidence.py`

Modify:
- `tests/trading/test_pr34_structural_splits.py` (repoint the 3 flat-sibling imports only)
- `plan/progress_tracker.md`

Create:
- `tests/trading/test_pr40_structural_splits.py`

Unchanged on purpose (verify they still pass): `src/trading/workflows/__init__.py`,
`tests/trading/test_pr32_structural_splits.py`, all production callers listed in Task 1.

## Caller inventory (must all keep resolving through shims)

`workflows.trading_decision` is imported by (do **not** edit these):
`src/trading/brokers/paper_stock.py`, `src/trading/intraday/rebalance.py`,
`src/trading/runtime/preopen_dependencies.py` (line ~129, lazy — the monkeypatch seam),
`src/trading/runtime/smoke_fixture_modes.py`, `src/trading/workflows/__init__.py`,
`src/trading/workflows/paper_execution.py`, `src/trading/workflows/paper_execution_options.py`,
`src/trading/repositories/_base.py`, `src/trading/repositories/in_memory.py`,
plus tests (`test_sqlalchemy_repository`, `test_navigation_imports`, `test_strategy_lifecycle`,
`test_paper_stock_broker`, `test_trading_decision_repository`, `test_runtime_live` — the
`monkeypatch.setattr` at line ~527) and scripts (`run_trading_live_preopen_order_smoke`,
`run_trading_option_paper_execution`, `run_trading_paper_execution`).

`workflows.option_strategy_builder` (the hub) is imported by: `src/trading/runtime/preopen_risk.py`
(line ~510) and `src/trading/workflows/trading_decision.py` (line ~29). No production code imports
the flat `_policy/_chain/_payload/_evidence` paths.

---

## Task 1: Lock the post-move compatibility surface with a failing test

**Files:** Create `tests/trading/test_pr40_structural_splits.py`

- [ ] Step 1: Write a test asserting the new canonical paths exist and export the public pipeline
  surface:
  - `from src.trading.decision import TradingDecisionPipeline, TradingDecisionPipelineResult, TradingDecisionRecord`
  - `from src.trading.decision.pipeline import TradingDecisionPipeline`
  - `from src.trading.decision.option_strategy_builder import (_build_option_strategy_payload, _build_option_strategy_payloads, _decision_action_for_expression, _resolve_expression_fallback_plan, _classification_instrument_type, _select_option_chain_legs, _WINDOWED_EVENT_NEWS_FIELDS, _news_evidence_limit, _evidence_priority, _round_nested_floats)`
  - `from src.trading.decision.option_strategy_builder.policy import _decision_action_for_expression`
  - `from src.trading.decision.option_strategy_builder.chain import _select_option_chain_legs`
  - `from src.trading.decision.option_strategy_builder.payload import _build_option_strategy_payload`
  - `from src.trading.decision.option_strategy_builder.evidence import _WINDOWED_EVENT_NEWS_FIELDS, _news_evidence_limit`

- [ ] Step 2: Write a test asserting the **old shim paths still resolve and preserve identity**:
  - `from src.trading.workflows.trading_decision import TradingDecisionPipeline, TradingDecisionPipelineResult, TradingDecisionRecord, _build_option_strategy_payloads`
  - `from src.trading.workflows.option_strategy_builder import _build_option_strategy_payload, _build_option_strategy_payloads, _decision_action_for_expression`
  - assert `workflows.trading_decision._build_option_strategy_payloads is workflows.option_strategy_builder._build_option_strategy_payloads`
  - assert `workflows.trading_decision.TradingDecisionPipeline is decision.pipeline.TradingDecisionPipeline`

- [ ] Step 3: Add an import-smoke test importing `src.trading.runtime.preopen_risk`,
  `src.trading.workflows.paper_execution`, `src.trading.repositories.sqlalchemy`, and
  `src.trading.runtime.preopen_dependencies`.

- [ ] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr40_structural_splits.py -q`
  Expected: fails only because `src.trading.decision` does not exist yet.

## Task 2: Create the `option_strategy_builder/` subpackage at its canonical home

**Files:** Create the 5 `src/trading/decision/option_strategy_builder/*.py` files.
**Test:** `tests/trading/test_pr40_structural_splits.py`, `tests/trading/test_pr34_structural_splits.py`

- [ ] Step 1: `git mv` each flat file into the subpackage with the prefix dropped, to preserve
  history:
  - `option_strategy_builder_policy.py` → `decision/option_strategy_builder/policy.py`
  - `option_strategy_builder_chain.py` → `decision/option_strategy_builder/chain.py`
  - `option_strategy_builder_payload.py` → `decision/option_strategy_builder/payload.py`
  - `option_strategy_builder_evidence.py` → `decision/option_strategy_builder/evidence.py`
  (These leave the flat `workflows/` paths gone; the hub shim is rebuilt in Task 3, and the four
  flat paths are intentionally not re-created — see File Map.)

- [ ] Step 2: Rewrite the intra-family imports to the new subpackage paths:
  - in `chain.py`: `from src.trading.workflows.option_strategy_builder_policy import _expression_option_policy`
    → `from src.trading.decision.option_strategy_builder.policy import _expression_option_policy`
  - in `payload.py`: the `from src.trading.workflows.option_strategy_builder_chain import (…)` and
    `from src.trading.workflows.option_strategy_builder_policy import (…)` blocks → the corresponding
    `src.trading.decision.option_strategy_builder.{chain,policy}` paths.

- [ ] Step 3: Create `decision/option_strategy_builder/__init__.py` as the hub: import the same
  names from `.policy`, `.chain`, `.payload`, `.evidence` that the current
  `workflows/option_strategy_builder.py` re-exports, and declare an **explicit** `__all__` list
  (NOT the `globals()` pattern — PR 35 banned it and a test enforces the ban). Copy the exact
  `__all__` list verbatim from the current hub
  (`git show HEAD:src/trading/workflows/option_strategy_builder.py` — it is already an explicit,
  alphabetized list of 37 names after PR 35).

- [ ] Step 4: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr40_structural_splits.py::<the new-canonical test> -q`
  (the canonical-path test from Task 1 Step 1 should now pass; shim tests still fail until Task 3).

## Task 3: Move the pipeline and rebuild both shims

**Files:** Create `decision/pipeline.py`, `decision/__init__.py`; rewrite
`workflows/trading_decision.py` and `workflows/option_strategy_builder.py` as shims.
**Test:** `tests/trading/test_pr40_structural_splits.py`, `tests/trading/test_pr32_structural_splits.py`,
`tests/trading/test_runtime_live.py`

- [ ] Step 1: `git mv src/trading/workflows/trading_decision.py src/trading/decision/pipeline.py`.

- [ ] Step 2: In `pipeline.py`, repoint its builder import (was line ~29
  `from src.trading.workflows.option_strategy_builder import (…)`) to
  `from src.trading.decision.option_strategy_builder import (…)`. Keep the imported name list
  identical. No other edits to the file body.

- [ ] Step 3: Create `decision/__init__.py` re-exporting
  `TradingDecisionPipeline, TradingDecisionPipelineResult, TradingDecisionRecord` from `.pipeline`,
  and the builder hub (`from . import option_strategy_builder`). Add an explicit `__all__`.

- [ ] Step 4: Rewrite `workflows/trading_decision.py` as a shim:
  `from src.trading.decision.pipeline import (TradingDecisionPipeline, TradingDecisionPipelineResult, TradingDecisionRecord)`
  plus `from src.trading.decision.pipeline import _build_option_strategy_payloads` (and any other
  private name the pre-move module exposed that callers/tests rely on — confirm against
  `git show HEAD:src/trading/workflows/trading_decision.py`). Keep the module docstring and
  `from __future__ import annotations`. This preserves the monkeypatch target
  `src.trading.workflows.trading_decision.TradingDecisionPipeline`.

- [ ] Step 5: Rewrite `workflows/option_strategy_builder.py` as a shim that re-exports the hub
  surface from the new subpackage with an **explicit** `from src.trading.decision.option_strategy_builder import (…)`
  name list and an **explicit** `__all__` (the same 37-name list). Do NOT use the `globals()`
  pattern and do NOT use `import *` — `test_compatibility_hub_all_lists_only_intended_exports` reads
  this file and asserts `"globals()"` is absent and that the names are in `__all__`. Preserve
  `preopen_risk.py`'s import surface (line ~510 list).

- [ ] Step 6: Run
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr40_structural_splits.py tests/trading/test_pr32_structural_splits.py -q`
  Expected: all pass (canonical + shim + identity contracts hold).

- [ ] Step 7: Run the monkeypatch-seam regression — this is the highest-risk check:
  `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py -q`
  Expected: all pass. If the `TradingDecisionPipeline` monkeypatch test fails, the shim is not
  exposing the class as a real module attribute, or a caller was accidentally migrated to the new
  path — fix the shim/caller, do not edit the test.

## Task 4: Repoint the PR 34 structural test and run full slice verification

**Files:** Modify `tests/trading/test_pr34_structural_splits.py`, `plan/progress_tracker.md`

- [ ] Step 1: In `test_pr34_structural_splits.py`, repoint only the 3 flat-sibling imports in
  `test_option_strategy_builder_split_modules_exist_and_export_representative_helpers` (lines ~5–11)
  to the new subpackage modules:
  `src.trading.decision.option_strategy_builder.{chain,evidence,payload,policy}`. Leave unchanged:
  `test_compatibility_hubs_still_reexport_runtime_import_surfaces` and
  `test_compatibility_hub_all_lists_only_intended_exports` (both import from
  `src.trading.workflows.option_strategy_builder` — preserved by the shim; the latter also reads the
  shim's `__file__` for `"globals()"`, which the explicit-`__all__` shim from Task 3 Step 5
  satisfies), `test_repository_mixins_do_not_star_import_repository_base` (unrelated), and the
  import-smoke test.

- [ ] Step 2: `source ~/.venv/bin/activate && python -m compileall -q src`

- [ ] Step 3: Import smoke:
  `source ~/.venv/bin/activate && python -c "import src.trading.decision, src.trading.decision.pipeline, src.trading.decision.option_strategy_builder, src.trading.workflows.trading_decision, src.trading.workflows.option_strategy_builder, src.trading.runtime.preopen_risk, src.trading.runtime.preopen_dependencies, src.trading.workflows.paper_execution, src.trading.repositories.sqlalchemy; print('imports ok')"`

- [ ] Step 4: Focused regression suite:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr40_structural_splits.py tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py tests/trading/test_navigation_imports.py tests/trading/test_runtime_live.py tests/trading/test_trading_decision_repository.py tests/trading/test_strategy_lifecycle.py tests/trading/test_paper_stock_broker.py tests/trading/test_sqlalchemy_repository.py -q`

- [ ] Step 5: Confirm no stray references to the deleted flat paths remain:
  `grep -rn --include="*.py" "option_strategy_builder_policy\|option_strategy_builder_chain\|option_strategy_builder_payload\|option_strategy_builder_evidence" src tests scripts`
  Expected: zero matches (the prefix-named flat modules are gone; everything goes through the hub or
  the subpackage).

- [ ] Step 6: `git diff --check`

- [ ] Step 7: Prepend a dated entry to `plan/progress_tracker.md` summarizing the PR 40 extraction,
  touched files, and verification commands/results.

Expected result: trade-decision logic lives in `src/trading/decision/`, the builder family is a
clean subpackage, all old import paths and the monkeypatch seam still work, and the prior structural
suites pass — proving zero behavior delta.

## Out of scope / follow-ups

- Migrating callers off the `workflows.*` shims onto `src.trading.decision.*` (optional later
  cleanup; shims are permanent compatibility hubs otherwise).
- Splitting the >400-line `pipeline.py` (was `trading_decision.py`, ~617 lines) — tracked separately
  per the topology doc's non-goals.
- PR 41 (`execution/`, `universe/`, fold adapters) and PR 42 (`phases/` + retire `runtime/`).
