# Risk Macro Decision Visible News Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the macro news and event news that were available to the latest RiskManager decision on the `/today?tab=risk-macro` page.

**Architecture:** Extend the existing `load_decision_available_risk_macro_context()` repository contract so the Risk & Macro presenter receives one canonical decision-visible context containing macro snapshot, calendar events, event-risk assessments, `macro_news`, and `event_news`. Keep point-in-time behavior by filtering all news with `available_for_decision_at <= decision_time`, dedupe by `dedupe_key`, and format rows in the presenter before Jinja renders them.

**Tech Stack:** Python, SQLAlchemy ORM models, pytest, FastAPI/Jinja, existing `/today` presenters and stylesheet.

---

## File Map

- Modify: `src/trading/repositories/mixins/macro_calendar.py`
  - Add decision-available loaders for `SocialMacroItem` and `EventNewsItem`.
  - Include `macro_news` and `event_news` in `load_decision_available_risk_macro_context()`.
- Modify: `src/trading/repositories/in_memory.py`
  - Mirror the contract for repository-backed tests and non-SQL workflows.
- Modify: `src/trading/repositories/_base.py`
  - Add a shared converter for `SocialMacroItemRecord` if needed.
- Modify: `src/web/presenters/today_risk_macro.py`
  - Convert raw news records into compact display rows.
  - Deduplicate and cap default display lists.
- Modify: `src/templates/today/_tab_risk_macro.html`
  - Render `Macro News` and `Event News` with explicit empty states.
- Modify: `src/static/style.css`
  - Add compact list styling only if existing news/card classes are insufficient.
- Test: `tests/trading/test_sqlalchemy_repository.py`
  - Repository contract filters out future news and scopes event news by relevant tickers.
- Test: `tests/web/test_today_risk_macro.py`
  - Presenter emits display-ready news rows without raw timestamps.
- Test: `tests/web/test_today.py`
  - Risk & Macro tab renders both news sections and empty states.

## Task 1: Extend Repository Context

- [x] Step 1: Write a failing SQLAlchemy repository test that saves past and future `SocialMacroItem`/`EventNewsItem` rows, calls `load_decision_available_risk_macro_context(decision_time=...)`, and expects only decision-visible rows.
- [x] Step 2: Write the matching in-memory behavior if needed by existing tests.
- [x] Step 3: Implement SQLAlchemy loaders and add `macro_news` / `event_news` to the returned context.
- [x] Step 4: Run `source ~/.venv/bin/activate && pytest tests/trading/test_sqlalchemy_repository.py -q -k decision_visible_news`.

## Task 2: Present News Rows

- [x] Step 1: Write failing presenter tests for macro/news display rows: title/headline, source, ticker/category, sentiment/importance, available time, summary, dedupe, and no future rows.
- [x] Step 2: Implement presenter normalization helpers and include `macro_news` and `event_news` in the payload.
- [x] Step 3: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_risk_macro.py -q`.

## Task 3: Render The Risk & Macro Tab

- [x] Step 1: Write failing template tests proving Macro News and Event News render on `/today?tab=risk-macro` and empty states are visible when no rows exist.
- [x] Step 2: Update the Jinja template using existing shared visual classes where possible.
- [x] Step 3: Add minimal CSS only for layout gaps.
- [x] Step 4: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k risk_macro`.

## Task 4: Verify And Track

- [x] Step 1: Run focused repository and web tests.
- [x] Step 2: Run `source ~/.venv/bin/activate && pytest tests/web -q`.
- [x] Step 3: Run `source ~/.venv/bin/activate && python -m compileall -q src`.
- [x] Step 4: Run `git diff --check`.
- [x] Step 5: Render `/today?tab=risk-macro` locally and inspect the changed sections.
- [x] Step 6: Update `plan/progress_tracker.md` with implementation and verification evidence.
