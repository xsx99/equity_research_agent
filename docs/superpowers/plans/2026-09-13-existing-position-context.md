# Existing-Position Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry broker-synced same-ticker portfolio exposure into pre-open trading decisions so repeated signals are evaluated as target-exposure decisions.

**Architecture:** The live pre-open and manual-review runners pass their already-synced `PortfolioContext` into `TradingDecisionPipeline`. The pipeline derives a small, JSON-safe same-ticker position context and uses it for both normal agent input and missing-snapshot fallbacks. Direct legacy callers may omit the context and retain an empty-portfolio default.

**Tech Stack:** Python 3.13, Pydantic, dataclasses, pytest.

---

## File map

- Modify `src/agents/trading_schemas.py`: validate the explicit position-context field.
- Modify `src/agents/prompts/trading/trading_decision_v1.yaml`: define total-target and existing-position semantics.
- Modify `src/trading/decision/pipeline.py`: accept portfolio context, derive matching positions, and persist the context.
- Modify `src/trading/phases/preopen/dependencies.py`: update the live decision-pipeline protocol.
- Modify `src/trading/phases/preopen/runner.py`: pass synced portfolio context into decision generation.
- Modify `src/trading/phases/manual_review/__init__.py`: preserve the same behavior for manual-review decisions.
- Modify `tests/trading/test_trading_decision_repository.py`: test the payload and fallback contract.
- Modify `tests/trading/test_runtime_live.py`: test runtime forwarding.
- Modify `plan/progress_tracker.md`: record files, tests, and verification results.

## Task 1: Add the failing decision-context regression test

**Files:** `tests/trading/test_trading_decision_repository.py`

- [x] Add a test that builds a `PortfolioContext` with a matching position and invokes `TradingDecisionPipeline.run`.
- [x] Assert the captured agent input has `has_existing_position is True`, includes the matching quantity and market value, and computes current weight from account equity.
- [x] Add a no-match assertion proving the same candidate remains `False` with an empty positions list.
- [x] Run the focused test and confirm it fails because the pipeline does not yet accept or use portfolio context.

## Task 2: Implement the normalized position context

**Files:** `src/agents/trading_schemas.py`, `src/trading/decision/pipeline.py`

- [x] Add a defaulted `position_context: dict[str, Any]` field to `TradingDecisionInput`.
- [x] Add a small pipeline helper that matches candidate ticker to `PortfolioContext.positions` case-insensitively and emits JSON-safe quantity/value/details plus aggregate market value and current weight.
- [x] Add `portfolio_context: PortfolioContext | None = None` to `TradingDecisionPipeline.run`.
- [x] Pass the derived context into `_build_input_payload` and `_build_missing_signal_snapshot_decision`; populate the top-level boolean from it.
- [x] Keep the no-context path backward compatible for existing direct tests and non-live callers.
- [x] Run the focused repository test and confirm it passes.

## Task 3: Forward live portfolio state and update prompt semantics

**Files:** `src/trading/phases/preopen/dependencies.py`, `src/trading/phases/preopen/runner.py`, `src/trading/phases/manual_review/__init__.py`, `src/agents/prompts/trading/trading_decision_v1.yaml`, `tests/trading/test_runtime_live.py`

- [x] Extend the live decision-pipeline protocol with the optional portfolio-context argument.
- [x] Pass `portfolio_result.portfolio_context` from both live runners into decision generation.
- [x] Add a runtime test that records the forwarded context and verifies it is the same object used by risk evaluation.
- [x] Update the prompt to explain current exposure, quantity/value context, and total target-weight semantics without adding new output actions.
- [x] Run the focused decision and runtime tests.

## Task 4: Verify fallback and complete the tracker

**Files:** `tests/trading/test_trading_decision_repository.py`, `plan/progress_tracker.md`

- [x] Add/adjust missing-snapshot fallback coverage to assert the same position context is persisted.
- [x] Run the relevant agent, decision, runtime, and phase tests.
- [x] Run `pytest -q` and `git diff --check`.
- [x] Update `plan/progress_tracker.md` with the implementation summary and exact verification commands/results.
