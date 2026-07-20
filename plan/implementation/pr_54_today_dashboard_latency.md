# PR 54 Today Dashboard Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:systematic-debugging`; use `ui-development` before touching dashboard presenters/templates. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `/today` refresh and tab-click latency by removing avoidable whole-table reads and tab-unnecessary dashboard loaders.

**Architecture:** Keep the server-rendered FastAPI/Jinja dashboard and existing presenter boundaries. Push risk/macro and manual-review filtering into SQL, narrow candidate loading to the current display cohort, and avoid building overview/risk-macro data for tabs that do not render it.

**Tech Stack:** Python, SQLAlchemy ORM, pytest, FastAPI/Jinja.

---

### Task 1: Lock The Slow Loader Boundaries

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `tests/trading/test_sqlalchemy_repository.py`

- [x] Add RED route-loader tests proving `portfolio` does not call `_load_today_risk_macro`, `_load_live_alerts`, or `_load_material_changes`.
- [x] Add RED repository tests proving risk/macro repository loaders apply SQL filters before `all()`.
- [x] Add RED repository tests proving manual review audit loading scopes decisions/orders/executions to active manual requests.

### Task 2: Push Filtering Into SQL

**Files:**
- Modify: `src/trading/repositories/mixins/macro_calendar.py`
- Modify: `src/trading/repositories/mixins/runtime_misc.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/web/routers/loaders/risk_macro.py`

- [x] Replace Python-side `.all()` filters in risk/macro read methods with ORM filters, ordering, and optional UI bounds.
- [x] Make `/today` risk/macro load only the window the presenter can show: upcoming calendar rows and recent decision-visible news.
- [x] Rewrite `load_manual_review_audit_rows()` to load active requests first, then related decisions, risk rows, orders, and executions by ID.

### Task 3: Narrow Candidate Loading

**Files:**
- Modify: `src/web/routers/loaders/candidates.py`
- Modify: `tests/web/test_today.py`

- [x] Add RED coverage that candidate loading queries the latest scanner/manual cohorts rather than materializing a 500-row lookback.
- [x] Implement run-key lookup and load only the selected scanner/manual cohort rows, preserving the existing no-scanner fallback.

### Task 4: Tab-Specific Loader Pruning

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today.py`

- [x] Stop building `overview` and risk/macro payloads on the `portfolio` tab.
- [x] Keep header and portfolio KPIs intact, including macro regime from the lightweight latest macro snapshot.

### Task 5: Verification And Tracker

**Files:**
- Modify: `plan/progress_tracker.md`

- [x] Run focused RED/GREEN tests.
- [x] Run affected web/repository tests, `python -m compileall -q src`, and `git diff --check`.
- [x] Re-profile real `/today` tab loader latency against the configured DB.
- [x] Update `plan/progress_tracker.md` with measured before/after evidence.
