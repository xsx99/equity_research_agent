# Today UI Quality Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the existing `/today` redesign so portfolio charts render correctly, candidate/risk lists read cleanly, and machine-facing UI artifacts stop leaking into operator surfaces.

**Architecture:** Keep the current `/today` IA and Trades rail/detail workflow intact. Restrict changes to server-rendered template/CSS work plus presenter-level display shaping, with targeted test updates proving chart geometry, duplicate collapse, and rendered markup changes.

**Tech Stack:** Python, FastAPI/Jinja, existing presenter modules, inline SVG, pytest.

**Design Doc:** [12_today_ui_quality_pass.md](../design/12_today_ui_quality_pass.md)

---

## File map

- Modify: `src/web/presenters/today_portfolio_analytics.py`
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today_portfolio_analytics.py`
- Modify: `tests/web/test_today_candidates.py`
- Modify: `tests/web/test_today_copy.py`
- Modify: `tests/web/test_today_workspace.py`
- Modify: `tests/web/test_today.py`
- Modify after implementation: `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Tasks

- [ ] Split Portfolio analytics into separate equity and daily P&L charts.
- [ ] Collapse duplicate candidate history into a human review timeline.
- [ ] Preserve Trades workflow while removing detail noise and smoke/internal leakage.
- [ ] Normalize Risk & Macro and attention lists into calmer briefing rows.
- [ ] Run focused verification, update the progress tracker, and capture visual follow-up.
