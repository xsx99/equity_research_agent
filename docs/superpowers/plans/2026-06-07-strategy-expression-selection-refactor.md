# Strategy Expression Selection Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split trading strategy definitions from expression-bucket definitions, add deterministic expression ranking plus same-strategy fallback ordering, and carry the chosen expression contract through selection and downstream execution paths.

**Architecture:** Keep strategy matching as the first stage, then introduce a dedicated expression-selection stage that consumes only the chosen tactical strategy plus active expression definitions. Persist the active expression choice and ordered same-strategy fallback list on the selected trade so classifier and downstream execution can re-resolve trade identity without rerunning strategy selection.

**Tech Stack:** Python, pytest, dataclasses, existing trading workflow/repository contracts

---

### Task 1: Split Seed Definitions And Public Exports

**Files:**
- Create: `src/trading/strategies/definitions/__init__.py`
- Create: `src/trading/strategies/definitions/strategies.py`
- Create: `src/trading/strategies/definitions/expressions.py`
- Modify: `src/trading/strategies/__init__.py`
- Modify: `tests/trading/test_strategy_catalog.py`
- Modify: `tests/trading/test_navigation_imports.py`

- [ ] **Step 1: Write failing tests for split definition loaders and top-level exports**
- [ ] **Step 2: Run `pytest tests/trading/test_strategy_catalog.py tests/trading/test_navigation_imports.py -q` and verify the new assertions fail**
- [ ] **Step 3: Move catalog seeds behind the new definitions package and keep compatibility exports**
- [ ] **Step 4: Re-run `pytest tests/trading/test_strategy_catalog.py tests/trading/test_navigation_imports.py -q` and verify they pass**

### Task 2: Add Deterministic Expression Selection Contract

**Files:**
- Modify: `src/trading/strategies/selector.py`
- Modify: `tests/trading/test_primary_strategy_selector.py`

- [ ] **Step 1: Write failing tests for preferred expression ranking, ordered same-strategy fallbacks, and option expressions staying on the trade path**
- [ ] **Step 2: Run `pytest tests/trading/test_primary_strategy_selector.py -q` and verify the new assertions fail**
- [ ] **Step 3: Implement expression-selection helpers and enrich `SelectedTradeRecord` with selected/fallback expression context**
- [ ] **Step 4: Re-run `pytest tests/trading/test_primary_strategy_selector.py -q` and verify they pass**

### Task 3: Propagate Expression Contract Through Classification And Replay

**Files:**
- Modify: `src/trading/strategies/classifier.py`
- Modify: `src/trading/workflows/strategy_scoring.py`
- Modify: `src/trading/replay/historical.py`
- Modify: `tests/trading/test_trade_classifier.py`
- Modify: `tests/trading/test_pipeline.py`

- [ ] **Step 1: Write failing tests that assert classifier consumes the concrete selected expression context and that workflow results preserve fallback metadata**
- [ ] **Step 2: Run `pytest tests/trading/test_trade_classifier.py tests/trading/test_pipeline.py -q` and verify the new assertions fail**
- [ ] **Step 3: Update downstream contracts to consume the richer selected-trade expression payload without watch-path downgrades**
- [ ] **Step 4: Re-run `pytest tests/trading/test_trade_classifier.py tests/trading/test_pipeline.py -q` and verify they pass**

### Task 4: Add Same-Strategy Fallback Resolution For Option Execution Paths

**Files:**
- Modify: `src/trading/workflows/paper_execution.py`
- Modify: `tests/trading/test_options_strategy.py`
- Modify: `tests/trading/test_paper_option_broker.py`

- [ ] **Step 1: Write failing tests for trying an option expression first and falling back to the next allowed same-strategy expression when the option path is rejected**
- [ ] **Step 2: Run the focused fallback tests and verify they fail for the current behavior**
- [ ] **Step 3: Implement deterministic fallback resolution without rerunning strategy selection**
- [ ] **Step 4: Re-run the focused fallback tests and verify they pass**

### Task 5: Verify, Document, And Record Progress

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run the relevant trading test suite covering definitions, selector, classifier, replay, and option execution**
- [ ] **Step 2: Update repository overview with the new strategy/expression selection architecture**
- [ ] **Step 3: Add a progress-tracker entry summarizing the completed refactor and verification evidence**
