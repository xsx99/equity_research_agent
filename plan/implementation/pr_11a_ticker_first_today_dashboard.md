# PR 11A: Ticker-First Today Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `/today` workstation from a flat trade-row view into a ticker-first workspace with attention buckets, latest-conclusion-first detail, and summary-first history tabs.

**Architecture:** Keep FastAPI + Jinja server rendering, but move ticker-centric aggregation and bucketing logic out of the template into focused presenter helpers. Reuse persisted trading artifacts (`TradingDecision`, `RiskDecision`, `PaperOrder`, `PaperPosition`, `SignalSnapshot`, `IntradaySignalSnapshot`, `NewsAlert`) to build one operator-facing view model per ticker, then render that model as a left ticker rail plus a right detail panel.

**Tech Stack:** Python, FastAPI, Jinja2, SQLAlchemy ORM, pytest, existing `/today` router/template/CSS stack.

---

## Scope

This plan is a refinement of existing PR 11 UI work, not a replacement for the whole `/today` module. The target is the ticker-first redesign centered on the current `Trades` experience and adjacent per-ticker context.

Stop after this PR slice for review/merge.

## File Structure

### Existing files to modify

- `src/web/routers/today.py`
  - Keep route handlers and DB loading orchestration.
  - Remove ticker bucketing / summary-string logic from inline route code once helper module exists.
- `src/templates/today.html`
  - Replace the flat `Trades` section with ticker rail + ticker detail layout.
  - Preserve top-level workstation tabs and non-target sections unless needed for layout consistency.
- `src/static/style.css`
  - Add styles for ticker rail, bucket sections, ticker cards, summary blocks, detail tabs, timeline cards, and evidence modules.
- `tests/web/test_today.py`
  - Update route rendering assertions for the new layout and selected ticker flow.

### New files to create

- `src/web/presenters/today_workspace.py`
  - Own ticker-centric aggregation, bucket assignment, default selection, summary blocks, timeline shaping, and evidence-module shaping.
- `tests/web/test_today_workspace.py`
  - Unit test bucketing, ordering, selected ticker resolution, and summary/evidence shaping without requiring HTML parsing.

## Delivery Notes

- Use TDD. Keep logic in Python helpers where possible so tests are deterministic and template complexity stays low.
- Do not invent new persistence tables in this PR. If a data family is absent, render deterministic empty states.
- Keep raw JSON behind detail/expand areas only. Primary UX must remain summary-first.

### Task 1: Add ticker workspace presenter skeleton

**Files:**
- Create: `src/web/presenters/today_workspace.py`
- Create: `tests/web/test_today_workspace.py`

- [ ] **Step 1: Write the failing presenter tests for bucket assignment and default selection**

```python
from datetime import datetime, timezone

from src.web.presenters.today_workspace import build_ticker_workspace


def test_build_ticker_workspace_groups_attention_buckets():
    rows = [
        {
            "ticker": "NVDA",
            "decision": "enter_long",
            "confidence": 0.82,
            "risk_status": "approved",
            "order_status": "pending",
            "material_signal_change": True,
        },
        {
            "ticker": "AAPL",
            "decision": "no_trade",
            "confidence": 0.31,
            "risk_status": "approved",
            "order_status": None,
            "material_signal_change": False,
        },
    ]

    workspace = build_ticker_workspace(
        trade_rows=rows,
        selected_ticker=None,
        positions_by_ticker={},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["action_now"]] == ["NVDA"]
    assert [item["ticker"] for item in workspace["buckets"]["watch"]] == ["AAPL"]
    assert workspace["selected_ticker"] == "NVDA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: FAIL with import error or missing `build_ticker_workspace`.

- [ ] **Step 3: Write the minimal presenter skeleton**

```python
def build_ticker_workspace(
    *,
    trade_rows,
    selected_ticker,
    positions_by_ticker,
    risk_by_ticker,
    signal_history_by_ticker,
    news_by_ticker,
    fundamentals_by_ticker,
):
    return {
        "selected_ticker": selected_ticker,
        "buckets": {
            "action_now": [],
            "in_position": [],
            "watch": [],
        },
        "detail": None,
    }
```

- [ ] **Step 4: Implement bucket assignment and default selection until the test passes**

Implementation notes:

- Normalize tickers to uppercase keys.
- Bucket explicit `Action Now` reasons first:
  - executable trade / `order_status in {"pending", "accepted", "partial_fill"}`
  - strong directional opportunity such as `decision in {"enter_long", "enter_short", "trim", "exit"}` with actionable state
  - high/critical risk or blocked/reduced risk outcome
  - material signal change
- Put open positions without urgent attention into `in_position`.
- Put remaining rows into `watch`.
- Default selected ticker order:
  - first ticker in `action_now`
  - else first ticker in `in_position`
  - else first ticker in `watch`

- [ ] **Step 5: Run presenter tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/presenters/today_workspace.py tests/web/test_today_workspace.py
git commit -m "feat: add today ticker workspace presenter"
```

### Task 2: Expand presenter to build summary-first ticker detail

**Files:**
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `tests/web/test_today_workspace.py`

- [ ] **Step 1: Write failing tests for latest conclusion and evidence modules**

```python
def test_build_ticker_workspace_shapes_latest_conclusion_and_evidence():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "selected_strategy_id": "valuation_repair_quality_software_v1",
                "expression_bucket_id": "long_stock",
                "confidence": 0.78,
                "risk_status": "approved",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={"NVDA": {"pnl": "+2.1%", "order_status": "accepted"}},
        risk_by_ticker={"NVDA": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={
            "NVDA": {
                "technical": [{"label": "price", "points": [1, 2, 3]}],
                "summary": ["relative strength improving vs QQQ"],
            }
        },
        news_by_ticker={"NVDA": [{"title": "Raised guidance", "summary": "demand improved"}]},
        fundamentals_by_ticker={"NVDA": [{"title": "margin outlook", "summary": "gross margin stable"}]},
    )

    detail = workspace["detail"]
    assert detail["latest_conclusion"]["trade_decision"]["label"] == "Enter Long"
    assert detail["latest_conclusion"]["signal_summary"]["technical_charts"]
    assert detail["latest_conclusion"]["signal_summary"]["news_snippets"][0]["title"] == "Raised guidance"
    assert detail["latest_conclusion"]["risk_summary"]["status"] == "approved"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: FAIL with missing latest-conclusion shape.

- [ ] **Step 3: Implement detail shaping**

Implementation notes:

- Build a `latest_conclusion` dict with four blocks:
  - `trade_decision`
  - `signal_summary`
  - `risk_summary`
  - `position_execution`
- Convert raw decisions to human-readable labels such as `enter_long -> Enter Long`.
- Add `signal_summary.summary_bullets`.
- Add `signal_summary.technical_charts` with compact chart payloads for:
  - `price / key level trend`
  - `relative strength trend`
- Add `signal_summary.news_snippets` and `fundamental_snippets`.
- Render `No material update` / empty-state markers in the payload when data is absent.

- [ ] **Step 4: Add tab payload shaping**

Implementation notes:

- `timeline`: compact event cards with `time`, `event_type`, `summary`, `detail_anchor`
- `trend`: technical/news/fundamental evidence modules
- `decisions`: per-ticker compact decision list
- `risk`: current stance, position state, risk history

- [ ] **Step 5: Run presenter tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/presenters/today_workspace.py tests/web/test_today_workspace.py
git commit -m "feat: shape ticker-first detail summaries"
```

### Task 3: Wire the presenter into the `/today` route loader

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write the failing route test for selected ticker deep-link**

```python
def test_today_dashboard_selects_ticker_from_query_param(client):
    payload = _dashboard_payload()
    with patch("src.web.routers.today.load_today_dashboard", return_value=payload):
        response = client.get("/today?ticker=NVDA")

    assert response.status_code == 200
    assert "Latest Conclusion" in response.text
```

- [ ] **Step 2: Run route tests to verify failure**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: FAIL because ticker-oriented content/query handling is missing.

- [ ] **Step 3: Update the route/query contract**

Implementation notes:

- Add `ticker: str | None = None` to `/today`.
- Pass `selected_ticker=ticker` into `load_today_dashboard`.
- Update `load_today_dashboard(...)` signature to accept `selected_ticker`.
- Load DB artifacts into per-ticker collections and call `build_ticker_workspace(...)`.
- Keep existing top-level sections as needed, but replace `trades.rows + selected_detail` as the primary render payload with:
  - `ticker_workspace`
  - optional compatibility subpayloads only if another section still depends on them

- [ ] **Step 4: Add route tests for empty-state fallback and selected ticker**

Examples:

- selected ticker from query param
- fallback to highest-priority ticker when query ticker missing
- empty workstation when no tickers exist

- [ ] **Step 5: Run route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/routers/today.py tests/web/test_today.py
git commit -m "feat: wire ticker workspace into today route"
```

### Task 4: Replace the flat Trades UI with ticker rail + detail panel

**Files:**
- Modify: `src/templates/today.html`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write the failing route-render test for the new layout markers**

```python
def test_today_dashboard_renders_ticker_workspace_sections(client):
    with patch("src.web.routers.today.load_today_dashboard", return_value=_dashboard_payload()):
        response = client.get("/today")

    assert "Action Now" in response.text
    assert "In Position" in response.text
    assert "Watch" in response.text
    assert "Latest Conclusion" in response.text
    assert "Timeline" in response.text
    assert "Trend" in response.text
    assert "Decisions" in response.text
    assert "Risk" in response.text
```

- [ ] **Step 2: Run route tests to verify failure**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: FAIL because the old flat-trades markup still renders.

- [ ] **Step 3: Rewrite the main workstation markup**

Implementation notes:

- Replace the existing flat `Trades` table section with:
  - left ticker rail containing three bucket sections
  - right ticker detail panel
- In the rail, render compact ticker cards with:
  - ticker/company
  - attention badge
  - latest decision
  - one-line why-now
  - recency
  - mini position/risk line
- In the detail panel, render:
  - `Trade Decision`
  - `Signal Summary`
  - `Risk Manager Summary`
  - `Position / Execution State`
- Under that, render tab buttons/panels for:
  - `Timeline`
  - `Trend`
  - `Decisions`
  - `Risk`
- Keep raw JSON in a lower-priority `<details>` block only if still needed for audit.

- [ ] **Step 4: Update fixture payloads in `tests/web/test_today.py`**

Implementation notes:

- Replace `trades.rows` / `selected_detail` assertions with `ticker_workspace` fixture data.
- Include:
  - one action-now ticker
  - one in-position ticker
  - one watch ticker
  - technical chart/evidence snippets

- [ ] **Step 5: Run route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/templates/today.html tests/web/test_today.py
git commit -m "feat: render ticker-first today workspace"
```

### Task 5: Add CSS and finish verification

**Files:**
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today.py`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Optional if structure meaningfully changed: `documents/repo_overview.md`

- [ ] **Step 1: Write or extend assertions for evidence-module and empty-state rendering**

Examples:

- `No material update` appears when news/fundamental snippets are absent
- empty ticker workspace message appears when no tickers exist
- selected ticker card has active style marker in HTML

- [ ] **Step 2: Run targeted tests to verify failure if styles/markers are not wired**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py -q`

Expected: FAIL until final styles/empty-state markup is wired correctly.

- [ ] **Step 3: Implement styles**

Implementation notes:

- Add CSS variables only if they match the existing style direction.
- Add classes for:
  - `.ticker-workspace`
  - `.ticker-rail`
  - `.ticker-bucket`
  - `.ticker-card`
  - `.attention-badge`
  - `.latest-conclusion-grid`
  - `.summary-block`
  - `.timeline-list`
  - `.evidence-module`
- Ensure mobile collapses to one column without hiding selected-ticker context.

- [ ] **Step 4: Run targeted tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py -q`

Expected: PASS.

- [ ] **Step 5: Run broader relevant tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/test_app.py -q`

Expected: PASS.

- [ ] **Step 6: Update tracker/docs**

Implementation notes:

- Add a dated entry to `plan/research_app/trading_agent_refactor/progress_tracker.md` summarizing the ticker-first `/today` refinement and verification commands.
- If the final code substantially changes the web architecture, add a short note to `documents/repo_overview.md`.

- [ ] **Step 7: Commit**

```bash
git add src/static/style.css tests/web/test_today.py tests/web/test_today_workspace.py plan/research_app/trading_agent_refactor/progress_tracker.md documents/repo_overview.md
git commit -m "feat: polish ticker-first today dashboard"
```

### Task 6: Final verification

**Files:**
- No new files required

- [ ] **Step 1: Run full relevant verification**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py tests/test_app.py -q`

Expected: PASS.

- [ ] **Step 2: Run diff sanity checks**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 3: Review UI manually**

Run:

```bash
source ~/.venv/bin/activate && uvicorn src.app:app --reload
```

Expected:

- `/today` loads
- left rail shows `Action Now`, `In Position`, `Watch`
- selecting a ticker updates the right detail panel
- latest conclusion shows decision/signal/risk/position blocks
- technical/news/fundamental evidence render with empty states when missing

- [ ] **Step 4: Final commit if verification changed tracked files**

```bash
git add -A
git commit -m "test: verify ticker-first today dashboard"
```

Only commit if verification required tracked-file changes; otherwise skip.
