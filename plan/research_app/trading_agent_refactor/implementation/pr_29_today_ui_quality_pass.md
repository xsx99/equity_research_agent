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
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today_portfolio_analytics.py`
- Modify: `tests/web/test_today_candidates.py`
- Modify: `tests/web/test_today.py`
- Modify after implementation: `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Task 1: Split Portfolio analytics into separate equity and daily P&L charts

**Files:**
- Modify: `tests/web/test_today_portfolio_analytics.py`
- Modify: `src/web/presenters/today_portfolio_analytics.py`
- Modify: `tests/web/test_today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`

- [ ] **Step 1: Write the failing analytics tests**

Add expectations that the analytics payload exposes separate chart payloads instead of one mixed
surface, for example:

```python
assert payload["equity_chart"]["points"]
assert payload["pnl_chart"]["bars"]
assert payload["pnl_chart"]["bar_width"] < 8.0
```

Also add a long-series case proving bar widths shrink with density instead of overlapping into a
solid block.

- [ ] **Step 2: Run the targeted analytics tests and verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_portfolio_analytics.py -q`

Expected: FAIL because the current payload still exposes `equity_points` / `daily_bars` as one mixed
chart surface.

- [ ] **Step 3: Implement the minimal analytics payload change**

Update `build_portfolio_analytics(...)` so it returns:

```python
{
    "equity_chart": {"points": "...", "min": 0.0, "max": 0.0},
    "pnl_chart": {"bars": (...,), "baseline_y": 0.0, "bar_width": 0.0},
    "metrics": {...},
}
```

Use width logic that scales with `count` instead of enforcing a minimum bar width that guarantees
overlap at high density.

- [ ] **Step 4: Update the Portfolio template and CSS**

Render one SVG for equity and one SVG for daily P&L. Keep the surrounding card structure brief and
use additive CSS classes such as:

```css
.portfolio-chart-stack { ... }
.equity-chart { ... }
.pnl-chart { ... }
```

Do not overlay bars and line in the same `viewBox`.

- [ ] **Step 5: Run portfolio tests and route render tests**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_portfolio_analytics.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k portfolio_analytics`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/web/test_today_portfolio_analytics.py tests/web/test_today.py src/web/presenters/today_portfolio_analytics.py src/templates/today.html src/static/style.css
git commit -m "fix: split today portfolio analytics charts"
```

## Task 2: Collapse duplicate candidate history into a human review timeline

**Files:**
- Modify: `tests/web/test_today_candidates.py`
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `tests/web/test_today.py`
- Modify: `src/templates/today.html`

- [ ] **Step 1: Write failing candidate dedupe tests**

Add a presenter test with multiple rows for the same ticker that share the same outcome, summary,
and timestamp and assert the rendered evaluation history collapses to one logical entry.

Add a route test that asserts:

```python
assert "Duplicate Rows" not in response.text
```

- [ ] **Step 2: Run the targeted candidate tests and verify they fail**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k candidate`

Expected: FAIL because the presenter currently preserves repeated evaluations and the template still
renders `Duplicate Rows`.

- [ ] **Step 3: Implement presenter-level dedupe**

In `today_candidates.py`, collapse repeated evaluations before they reach the template. Keep the most
recent row as the primary card and shape timeline entries into a display-friendly structure, e.g.:

```python
{
    "decision_time": item.get("decision_time"),
    "outcome": ...,
    "strategy_label": ...,
    "confidence": ...,
    "summary": ...,
}
```

Add a human-facing history count only if it contributes meaning; do not expose raw duplicate counters.

- [ ] **Step 4: Update the candidate template**

Remove the `Duplicate Rows` tile. Use the timeline only when there is meaningful deduped history, and
render timestamps with the existing `local_time` template filter instead of raw ISO strings.

- [ ] **Step 5: Run candidate presenter and route tests**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k candidate`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/web/test_today_candidates.py tests/web/test_today.py src/web/presenters/today_candidates.py src/templates/today.html
git commit -m "fix: clean today candidate review history"
```

## Task 3: Preserve Trades workflow while removing detail noise

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`

- [ ] **Step 1: Write failing tests for cleaned trade detail copy**

Add a route/presenter-level regression proving internal smoke/raw identifiers do not surface in the
hero or trade-plan blocks when a cleaned alternative exists.

- [ ] **Step 2: Run the focused trades tests and verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k trades`

Expected: FAIL because the current detail surface still renders raw values in at least one block.

- [ ] **Step 3: Implement minimal presenter cleanup**

Use the existing copy helpers in `today_workspace.py` so summary/thesis/plan fields prefer human text
and suppress raw internal strings. Preserve the rail/detail structure and current detail tabs.

- [ ] **Step 4: Tighten the template and styles**

Reduce redundant labels, quiet repeated `No material update` copy, and keep the support cards aligned
with the calmer briefing direction without changing workflow.

- [ ] **Step 5: Run the trades route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k trades`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/web/test_today.py src/web/presenters/today_workspace.py src/templates/today.html src/static/style.css
git commit -m "fix: clean today trades detail presentation"
```

## Task 4: Normalize Risk & Macro and attention lists into briefing rows

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`

- [ ] **Step 1: Write failing render assertions**

Add route assertions covering the touched list surfaces and empty states, for example:

```python
assert 'data-testid="economic-calendar"' in response.text
assert "No economic calendar rows are currently visible." in response.text
```

and the updated card/list class hooks used by the template.

- [ ] **Step 2: Run the focused risk/portfolio route tests and verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k "risk_macro or needs_attention"`

Expected: FAIL once the new markup expectations are in place.

- [ ] **Step 3: Implement additive template/CSS cleanup**

Keep the data source unchanged, but normalize list/card rows so they share the same visual language as
the rest of `/today`. Ensure card-like links explicitly set `text-decoration: none`.

- [ ] **Step 4: Run the broader `/today` suite**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_candidates.py tests/web/test_today_portfolio_analytics.py -q`

Expected: PASS.

- [ ] **Step 5: Template structure verification**

Run the template structure lint used by the existing UI plan and confirm `STRUCTURE OK`.

- [ ] **Step 6: Commit**

```bash
git add tests/web/test_today.py src/templates/today.html src/static/style.css
git commit -m "fix: normalize today briefing lists"
```

## Task 5: Final verification and tracker update

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run final verification**

Run:
- `source ~/.venv/bin/activate && python -m py_compile src/web/presenters/today_portfolio_analytics.py src/web/presenters/today_candidates.py src/web/presenters/today_workspace.py`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_candidates.py tests/web/test_today_portfolio_analytics.py -q`

- [ ] **Step 2: Render verification**

Run the app normally and inspect `/today`. If app startup is blocked here, explicitly record that the
code/tests passed but rendered verification still needs fresh screenshots before claiming the UI is
finished.

- [ ] **Step 3: Update the progress tracker**

Add a dated entry to `plan/research_app/trading_agent_refactor/progress_tracker.md` summarizing the
UI quality-pass implementation and the exact verification commands/results.

- [ ] **Step 4: Commit**

```bash
git add plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "docs: record today ui quality pass"
```
