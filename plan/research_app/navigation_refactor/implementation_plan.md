# Navigation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize tools, providers, trading workflows, and research workflows so file paths describe responsibility while preserving runtime behavior.

**Architecture:** Move real API provider code out of `src/tools` into `src/providers`, move workflow orchestration into `workflows`, signal code into `signals`, strategy code into `strategies`, and in-memory persistence into `repositories`. Delete old root-level compatibility modules after internal imports move to the new paths.

**Tech Stack:** Python, SQLAlchemy, FastAPI, pytest, existing provider clients.

---

### Task 1: Add Import Compatibility Tests

**Files:**
- Modify: `tests/tools/test_tool_registry.py`
- Create or modify: `tests/trading/test_navigation_imports.py`
- Create or modify: `tests/research/test_navigation_imports.py`

- [x] Add tests that import the new package paths and assert key classes/functions resolve.
- [x] Run targeted tests and verify failures before moving modules.

### Task 2: Move Provider Implementations

**Files:**
- Create: `src/providers/market_data/`
- Create: `src/providers/news_data/`
- Create: `src/providers/global_context/`
- Modify: `src/tools/market_data.py`
- Modify: `src/tools/news_data.py`
- Modify: `src/tools/global_context.py`
- Modify imports in `src/`, `tests/`, and `scripts/`.

- [x] Move real API clients, helper functions, and provider contracts under `src/providers`.
- [x] Keep agent-callable wrappers in `src/tools`.
- [x] Run provider/tool tests.

### Task 3: Move Trading Workflows and Repositories

**Files:**
- Create: `src/trading/workflows/`
- Create: `src/trading/signals/`
- Create: `src/trading/strategies/`
- Create: `src/trading/repositories/`
- Delete: `src/trading/pipeline.py`
- Delete: `src/trading/repository.py`
- Modify imports in `src/`, `tests/`, and `scripts/`.

- [x] Move `UniverseScanPipeline`, `SignalPipeline`, and `StrategyPipeline` into focused workflow modules.
- [x] Move signal source contracts, PIT helpers, builders, snapshots, and ingestion into `src/trading/signals/`.
- [x] Move strategy catalog, matching, selector, classifier, taxonomy, and calibration into `src/trading/strategies/`.
- [x] Move universe contracts and provider resilience guardrails into `src/trading/data_sources/`.
- [x] Move manual ticker request contracts into `src/trading/manual_review/`.
- [x] Move portfolio intent helpers into `src/trading/portfolio/`.
- [x] Move relationship graph helpers into `src/trading/relationships/`.
- [x] Move historical replay and outcome evaluation into `src/trading/replay/`.
- [x] Move `InMemoryTradingRepository` into `src/trading/repositories/in_memory.py`.
- [x] Delete old root-level trading compatibility modules after moving internal imports.
- [x] Run trading tests.

### Task 4: Move Research Workflows and Repository Helpers

**Files:**
- Create: `src/research/workflows/`
- Create: `src/research/repositories/`
- Delete: `src/research/pipeline.py`
- Delete: `src/research/eval_pipeline.py`
- Delete: `src/research/repository.py`
- Modify imports in `src/`, `tests/`, and `scripts/`.

- [x] Move research batch workflow and eval workflow into `src/research/workflows`.
- [x] Move research DB helpers into `src/research/repositories/research_repository.py`.
- [x] Delete old root-level research compatibility modules after moving internal imports.
- [x] Run research tests.

### Task 5: Docs and Full Verification

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/README.md`
- Modify: `plan/research_app/navigation_refactor/progress_tracker.md`

- [x] Update repo overview with the new source-tree responsibilities.
- [x] Update progress tracker with files changed, commands run, and known gaps.
- [x] Run full test suite.
- [x] Run diff whitespace check.
