# PR 34 Residual Helper Hub Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower the remaining local reasoning cost in `option_strategy_builder.py` and `repositories/_base.py` by splitting unrelated helper clusters into focused sibling modules while preserving all current behavior and import paths.

**Architecture:** Keep both original modules as thin compatibility hubs. Move helper families into sibling files grouped by reasoning concern, re-export them through the original module, and add structural regression tests that lock the compatibility contract. No business logic, repository query behavior, or workflow behavior changes are in scope.

**Tech Stack:** Python, pytest, existing SQLAlchemy repository mixins, existing trading workflow modules.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md`
3. `plan/design/2026-06-26-residual-helper-hub-split.md`
4. `plan/implementation/PR_32_refactor-split-god-files.md`
5. `plan/implementation/PR_33_refactor-split-god-files-round2.md`
6. `plan/progress_tracker.md` Recent section only

## Guardrails

- Pure structural refactor only.
- Keep current import paths stable.
- Do not combine this slice with query cleanup, dead-code deletion, or behavior changes.

## File Map

- Create: `src/trading/workflows/option_strategy_builder_policy.py`
- Create: `src/trading/workflows/option_strategy_builder_chain.py`
- Create: `src/trading/workflows/option_strategy_builder_payload.py`
- Create: `src/trading/workflows/option_strategy_builder_evidence.py`
- Modify: `src/trading/workflows/option_strategy_builder.py`
- Create: `src/trading/repositories/_base_common.py`
- Create: `src/trading/repositories/_base_manual_review.py`
- Create: `src/trading/repositories/_base_payloads.py`
- Create: `src/trading/repositories/_base_records.py`
- Modify: `src/trading/repositories/_base.py`
- Create: `tests/trading/test_pr34_structural_splits.py`
- Modify: `plan/progress_tracker.md`

## Verification

- `source ~/.venv/bin/activate && pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py -q`
- `source ~/.venv/bin/activate && pytest tests/trading/test_sqlalchemy_repository_structure.py tests/trading/test_sqlalchemy_repository.py -q`
- `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py -q`
- `source ~/.venv/bin/activate && python -m compileall -q src`
- `source ~/.venv/bin/activate && python -c "import src.trading.workflows.option_strategy_builder, src.trading.workflows.trading_decision, src.trading.runtime.preopen_risk, src.trading.repositories._base, src.trading.repositories.sqlalchemy"`
- `git diff --check`
