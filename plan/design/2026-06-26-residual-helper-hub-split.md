# Residual Helper Hub Split

## Context

PR 32 and PR 33 removed the highest-cost god files, but two residual helper hubs still carry more
local reasoning cost than their public surface justifies:

- `src/trading/workflows/option_strategy_builder.py` remains ~995 lines after the original
  `trading_decision.py` extraction.
- `src/trading/repositories/_base.py` remains ~721 lines after the repository mixin split.

By contrast, `src/trading/workflows/trading_decision.py` (~617 lines) and
`src/web/routers/today.py` (~513 lines) are now mostly public orchestration surfaces. Their
remaining size is real workflow/router logic, not a tail of unrelated helpers, so another
mechanical file split would add churn without materially lowering local comprehension cost.

## Problem

The current residual files are understandable at a high level, but still expensive to reason about
locally because a reader must scan several unrelated helper families in one place:

- `option_strategy_builder.py` mixes expression-policy resolution, option-chain selection, payload
  assembly, news evidence helpers, and serialization constants.
- `_base.py` mixes scalar coercion helpers, manual-review state derivation, read-model payload
  builders, ORM row-to-record adapters, and a few repository-only utility functions.

The issue is no longer "one file owns the whole subsystem"; it is "one helper hub still owns too
many unrelated helper clusters."

## Scope Decision

This follow-up is intentionally narrow and structural:

- Split `src/trading/workflows/option_strategy_builder.py` into focused sibling helper modules.
- Split `src/trading/repositories/_base.py` into focused sibling helper modules while keeping
  `_base.py` as the compatibility import hub for repository mixins.
- Preserve all current import paths and behavior through re-exports.

Explicit non-goals:

- No behavior changes, signature changes, or business-logic reorderings.
- No further split of `src/trading/workflows/trading_decision.py`.
- No further split of `src/web/routers/today.py`.
- No query rewrites, dead-code cleanup, or schema changes in the repository layer.

## Target Structure

### A. `option_strategy_builder.py`

Keep `src/trading/workflows/option_strategy_builder.py` as a re-export hub. Add these sibling
modules:

- `src/trading/workflows/option_strategy_builder_policy.py`
- `src/trading/workflows/option_strategy_builder_chain.py`
- `src/trading/workflows/option_strategy_builder_payload.py`
- `src/trading/workflows/option_strategy_builder_evidence.py`

The split follows reasoning clusters rather than line count: fallback/policy, chain/leg selection,
payload orchestration, and evidence/window helpers.

### B. `_base.py`

Keep `src/trading/repositories/_base.py` as the shared import hub and the home of `_RepositoryBase`.
Add these sibling modules:

- `src/trading/repositories/_base_common.py`
- `src/trading/repositories/_base_manual_review.py`
- `src/trading/repositories/_base_payloads.py`
- `src/trading/repositories/_base_records.py`

This preserves the existing repository mixin contract while shrinking the file a human has to hold
in memory.

## Compatibility Requirements

- `src.trading.workflows.option_strategy_builder` must continue exporting the helpers used by
  `trading_decision.py`, `preopen_risk.py`, and structural tests.
- `src.trading.repositories._base` must continue exporting `_RepositoryBase` and the helper/model
  names consumed by repository mixins via `from ..._base import *`.

## Verification Strategy

Add a dedicated structural regression file:

- `tests/trading/test_pr34_structural_splits.py`

It must verify:

- the new helper submodules exist and expose representative names
- the original compatibility hubs still re-export the expected runtime surfaces
- import smoke for `src.trading.repositories.sqlalchemy`,
  `src.trading.runtime.preopen_risk`, and `src.trading.workflows.trading_decision`

Targeted verification:

- `pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py -q`
- `pytest tests/trading/test_sqlalchemy_repository_structure.py tests/trading/test_sqlalchemy_repository.py -q`
- `pytest tests/trading/test_runtime_live.py -q`
- `python -m compileall -q src`

## Why Not Split `today.py` Or `trading_decision.py` Again

- `today.py` is now a router/orchestrator plus a compatibility seam for loader monkeypatching. The
  expensive helper tail is already gone.
- `trading_decision.py` now contains one public datamodel pair plus one pipeline class. Its next
  refactor, if ever needed, should be an internal class-method extraction driven by workflow
  behavior, not another module split done just to lower the line count.
