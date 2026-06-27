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

## Design Principles

### 1. Keep stable import paths

The implementation must preserve the current public and semi-private import contracts:

- `src.trading.workflows.option_strategy_builder` stays the import path used by
  `trading_decision.py`, `preopen_risk.py`, and structural tests.
- `src.trading.repositories._base` stays the wildcard-import hub used by repository mixins and the
  `_RepositoryBase` import used by structure tests.

This means both original files remain as thin compatibility hubs rather than being deleted outright.

### 2. Split by reasoning cluster, not line count

The goal is to let a reader hold one concern in working memory at a time:

- policy and fallback planning
- option-chain and leg selection
- payload orchestration and serialization
- read-model payload shaping
- ORM row-to-record adaptation

The split should not produce tiny fragments or arbitrary line-based shards.

### 3. Preserve one-directional dependencies

New helper modules should form a simple DAG:

- the compatibility hub may import from all sibling helper modules
- orchestration modules may import lower-level helper modules
- lower-level helper modules must not import the compatibility hub

No monkeypatch seam like `today_loaders.py` is needed here, so direct sibling imports are safe.

## Target Structure

### A. `option_strategy_builder.py` → compatibility hub plus 4 sibling helper modules

Keep `src/trading/workflows/option_strategy_builder.py` as a re-export hub. Add these sibling
modules:

- `src/trading/workflows/option_strategy_builder_policy.py`
  - instrument-type classification and fallback-plan helpers
  - expression and option policy helpers
  - earnings-policy, DTE, profit-target, max-loss, roll/close, pairing, assignment helpers
- `src/trading/workflows/option_strategy_builder_chain.py`
  - underlying-price inference
  - deterministic leg construction
  - option-chain flattening, viability scoring, contract-to-leg conversion, IV context
- `src/trading/workflows/option_strategy_builder_payload.py`
  - `_build_option_strategy_payloads`
  - `_build_option_strategy_payload`
  - rejection payload assembly
  - serialized payload shaping
- `src/trading/workflows/option_strategy_builder_evidence.py`
  - `_render_news_source_text`
  - `_WINDOWED_EVENT_NEWS_FIELDS`
  - evidence-limit / evidence-priority helpers
  - nested-float rounding

Rationale:

- `trading_decision.py` consumes both option payload builders and evidence/window constants, but
  those are separate reasoning concerns. A hub keeps the import path stable while letting readers
  open only the relevant cluster.
- `preopen_risk.py` only needs the option decision-action/payload path and should keep importing
  through the hub.
- The policy and chain layers have a clean dependency direction into payload assembly.

### B. `_base.py` → compatibility hub plus 4 sibling helper modules

Keep `src/trading/repositories/_base.py` as the shared import hub and the home of `_RepositoryBase`.
Add these sibling modules:

- `src/trading/repositories/_base_common.py`
  - UUID / decimal / datetime / string coercion helpers
  - legacy option order-id formatting
  - option contract symbol formatting
  - generic row-sorting helper
- `src/trading/repositories/_base_manual_review.py`
  - manual-request payload
  - manual-review execution-path and linkage-state helpers
  - manual-review actionable decision helper
  - intraday context metadata helper
- `src/trading/repositories/_base_payloads.py`
  - dict payload builders returned by repository read methods
  - portfolio, candidate, order, execution, risk, hedge, reflection, and outcome summary payloads
- `src/trading/repositories/_base_records.py`
  - ORM row-to-record adapters
  - portfolio event-risk storage-key helper
  - latest portfolio-risk-snapshot lookup helper

Rationale:

- Repository mixins currently rely on `from src.trading.repositories._base import *`. A thin hub
  preserves that contract while shrinking the file that a human must inspect.
- `_RepositoryBase` remains in `_base.py` because it is the only class-level concern and is part of
  the structural test surface.
- The payload helpers and record adapters are distinct mental models and should not live together.

## Compatibility Requirements

### `option_strategy_builder`

- All currently imported names remain importable from `src.trading.workflows.option_strategy_builder`.
- The hub re-exports the same private helper names that current tests assert on:
  `_build_option_strategy_payload`, `_build_option_strategy_payloads`,
  `_decision_action_for_expression`, and the evidence/window helpers used by
  `trading_decision.py`.
- No caller should need to change import paths for this refactor.

### `_base`

- Repository mixins remain unchanged and continue to work with wildcard imports from `_base.py`.
- `tests/trading/test_sqlalchemy_repository_structure.py` must continue to import `_RepositoryBase`
  from `src.trading.repositories._base`.
- `_base.py` keeps an explicit `__all__` contract or an equivalent generated export list so the hub
  remains the single import surface for mixins.

## Verification Strategy

Add a dedicated structural regression test file for this slice:

- `tests/trading/test_pr34_structural_splits.py`

It should verify:

- `option_strategy_builder.py` still exports the helpers used by current call sites/tests.
- `_base.py` still exports `_RepositoryBase` plus representative helper names consumed by mixins.
- Import smoke for `src.trading.repositories.sqlalchemy`, `src.trading.runtime.preopen_risk`, and
  `src.trading.workflows.trading_decision` still succeeds.

Targeted runtime verification:

- `pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py -q`
- `pytest tests/trading/test_sqlalchemy_repository_structure.py tests/trading/test_sqlalchemy_repository.py -q`
- `pytest tests/trading/test_runtime_live.py -q`
- `python -m compileall -q src`

## Why Not Split `today.py` Or `trading_decision.py` Again

Those files are still over 500 lines, but they no longer fail for the same reason:

- `today.py` is now a router/orchestrator plus a compatibility seam for loader monkeypatching. The
  expensive helper tail is already gone.
- `trading_decision.py` now contains one public datamodel pair plus one pipeline class. Its next
  refactor, if ever needed, should be an internal class-method extraction driven by workflow
  behavior, not another module split done just to lower the line count.

This slice is specifically about residual helper hubs where the structural payoff remains high.
