# PR 11C: Ticker Lifecycle + Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `/today` so ticker lifecycle stays visible after close/reject, overview becomes a real command center, and primary UI copy translates internal strategy/risk IDs into operator-facing language.

**Architecture:** Keep FastAPI + Jinja server rendering and existing persisted trading artifacts as the source of truth. Add a thin presenter/copy layer that derives one primary lifecycle state plus attention flags per ticker from `TradingDecision`, `PaperPosition`, `CandidateScore`, `RiskDecision`, signal snapshots, and alerts; keep raw/debug payloads available only behind advanced surfaces. Do not add schema changes in this slice.

**Tech Stack:** Python, FastAPI, Jinja2, SQLAlchemy ORM, pytest, existing `/today` route/template/CSS stack.

---

## Scope

This plan is a follow-up slice to PR 11A and PR 11B. It fixes the operator-facing behavior gaps called out in review:

- closed positions disappear from the workstation after exit
- ticker state is inconsistent across `Overview`, `Portfolio`, `Trades`, and `Candidates`
- `Risk & Macro` reads like a raw factor-exposure dump instead of a risk surface
- `Candidates` exposes internal IDs instead of operator-facing reasoning
- homepage still summarizes data, but does not direct operator attention

In scope:

- one derived ticker lifecycle model for `/today`
- closed-today and rejected/no-trade visibility without new DB tables
- operator-facing translation helpers for strategy/risk/candidate language
- overview command-center action items
- risk summary-first rendering with advanced drill-down
- candidate summary-first rendering with translated status/reason copy

Out of scope:

- schema or migration changes
- new trading logic or new persisted artifacts
- redesigning `/research`
- SPA/JS state management
- changing the meaning of existing persisted risk or candidate records

## File Structure

### Existing files to modify

- `src/web/routers/today.py`
  - Load recent closed positions and build command-center/risk/candidate summary payloads.
  - Stop passing raw internal fields directly to the template when a translated presentation field is available.
- `src/web/presenters/today_workspace.py`
  - Replace the three-bucket model with lifecycle-aware buckets and detail shaping.
  - Keep advanced/raw payloads available, but remove them from primary summaries.
- `src/templates/today.html`
  - Recompose `Overview`, `Trades`, `Risk & Macro`, and `Candidates` to use lifecycle-aware operator-first surfaces.
- `src/static/style.css`
  - Add styles for lifecycle rail sections, command-center alert modules, advanced panels, and translated status badges.
- `tests/web/test_today_workspace.py`
  - Cover lifecycle bucketing, closed-position persistence, lifecycle timeline shaping, and translated detail summaries.
- `tests/web/test_today.py`
  - Cover command-center overview, risk summary-first rendering, advanced/raw collapse behavior, and translated candidate/trade copy.

### New files to create

- `src/web/presenters/today_copy.py`
  - Centralize human-facing labels/summaries for strategy IDs, candidate outcomes, risk statuses, lifecycle labels, and "why now" copy.
- `tests/web/test_today_copy.py`
  - Lock user-facing translations so templates and presenters do not drift back to raw IDs.

## Delivery Notes

- Use TDD. Presenter and copy-layer behavior should land in focused unit tests before template updates.
- Derive lifecycle state from existing rows. Do not invent new DB columns just to support UI labels.
- A ticker should have one primary lifecycle state for grouping plus separate attention flags for urgency, degraded data, or risk escalation.
- Primary UI must prefer translated labels and summaries; raw IDs belong in `<details>` / advanced surfaces only.
- Keep `/research` and raw JSON audit access intact.

### Task 1: Add a user-facing translation layer for trading copy

**Files:**
- Create: `src/web/presenters/today_copy.py`
- Create: `tests/web/test_today_copy.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/web/routers/today.py`

- [ ] **Step 1: Write failing translation tests**

```python
from src.web.presenters.today_copy import (
    candidate_result_label,
    lifecycle_label,
    risk_status_label,
    strategy_label,
)


def test_strategy_label_translates_internal_ids_to_operator_copy():
    assert strategy_label("direct_negative_catalyst") == "Negative catalyst detected"
    assert strategy_label("valuation_repair_quality_software_v1") == "Valuation repair setup"


def test_candidate_result_label_translates_rejection_like_results():
    assert candidate_result_label("blocked_by_missing_data") == "Blocked: required data unavailable"
    assert candidate_result_label("no_trade") == "No trade"


def test_lifecycle_label_translates_primary_states():
    assert lifecycle_label("closed") == "Closed"
    assert lifecycle_label("open_position") == "Open Position"


def test_risk_status_label_keeps_approved_but_humanizes_blocks():
    assert risk_status_label("approved") == "Approved"
    assert risk_status_label("reduced_by_concentration_limit") == "Reduced: concentration limit"
```

- [ ] **Step 2: Run translation tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_copy.py -q`

Expected: FAIL with import error or missing helper functions.

- [ ] **Step 3: Implement the translation helper module**

Implementation notes:

- Use deterministic mapping tables for known IDs that appear in primary UI.
- Fall back to generic underscore-to-sentence humanization when an ID is unknown.
- Keep raw input value available through separate fields so advanced views can still show exact IDs.

- [ ] **Step 4: Thread translated labels into presenter payloads**

Implementation notes:

- `today_workspace` should expose both raw IDs and translated labels for strategy, lifecycle, candidate result, and risk status.
- `today.py` candidate/risk summary rows should use translated fields by default.

- [ ] **Step 5: Re-run focused presenter/copy tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_copy.py tests/web/test_today_workspace.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/presenters/today_copy.py tests/web/test_today_copy.py src/web/presenters/today_workspace.py src/web/routers/today.py
git commit -m "feat: add operator-facing today workspace copy layer"
```

### Task 2: Replace the three-bucket trades rail with a lifecycle-aware ticker model

**Files:**
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `tests/web/test_today_workspace.py`
- Modify: `src/web/routers/today.py`

- [ ] **Step 1: Write failing lifecycle-bucketing tests**

```python
def test_build_ticker_workspace_keeps_closed_ticker_visible_in_closed_today_bucket():
    workspace = build_ticker_workspace(
        trade_rows=[
            {"ticker": "NVDA", "decision": "exit", "order_status": "filled", "created_at": "2026-06-05T19:58:00Z"},
            {"ticker": "AAPL", "decision": "enter_long", "order_status": "filled", "created_at": "2026-06-05T14:31:00Z"},
        ],
        selected_ticker=None,
        positions_by_ticker={"AAPL": {"status": "open"}},
        closed_positions_by_ticker={"NVDA": {"status": "closed", "closed_at": "2026-06-05T20:05:00Z"}},
        risk_by_ticker={},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    assert [item["ticker"] for item in workspace["buckets"]["closed_today"]] == ["NVDA"]
    assert workspace["selected_ticker"] == "AAPL"


def test_build_ticker_workspace_assigns_primary_lifecycle_state_and_attention_flags():
    workspace = build_ticker_workspace(
        trade_rows=[{"ticker": "MSFT", "decision": "no_trade", "risk_status": "approved", "material_signal_change": True}],
        selected_ticker="MSFT",
        positions_by_ticker={},
        closed_positions_by_ticker={},
        risk_by_ticker={"MSFT": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    item = workspace["buckets"]["reviewing"][0]
    assert item["primary_state"] == "reviewing"
    assert item["attention_flags"] == ["material_change"]
```

- [ ] **Step 2: Run lifecycle presenter tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: FAIL because `closed_positions_by_ticker`, new buckets, and lifecycle fields do not exist yet.

- [ ] **Step 3: Extend route loading to include recent closed positions**

Implementation notes:

- Add a route helper such as `_load_recent_closed_positions(session)` that reads `PaperPosition.status == "closed"` and orders by `closed_at`.
- Pass a `closed_positions_by_ticker` collection into `build_ticker_workspace`.
- Keep `Portfolio` open-book rendering unchanged in this task; closed rows are for workstation lifecycle visibility, not portfolio inventory.

- [ ] **Step 4: Implement the lifecycle presenter contract**

Implementation notes:

- Replace `action_now / in_position / watch` with:
  - `action_now`
  - `open_positions`
  - `closed_today`
  - `reviewing`
  - `watch`
- Derive one `primary_state` per ticker from latest decision, open/closed position state, and candidate/risk context.
- Derive `attention_flags` separately for material change, blocked risk, data degraded, or pending execution.
- Keep bucket ordering deterministic and favor still-actionable work over already-closed tickers when choosing the default selection.

- [ ] **Step 5: Re-run lifecycle presenter tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/routers/today.py src/web/presenters/today_workspace.py tests/web/test_today_workspace.py
git commit -m "feat: add lifecycle-aware today trades buckets"
```

### Task 3: Add lifecycle detail, close records, and trade history to the selected ticker canvas

**Files:**
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today_workspace.py`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write failing detail-shaping tests for entry/exit history**

```python
def test_build_ticker_workspace_detail_includes_entry_exit_reason_times_and_pnl():
    workspace = build_ticker_workspace(
        trade_rows=[
            {
                "ticker": "NVDA",
                "decision": "enter_long",
                "created_at": "2026-06-05T14:31:00Z",
                "selected_strategy_id": "breakout_v1",
                "thesis": "Momentum breakout confirmed",
            },
            {
                "ticker": "NVDA",
                "decision": "exit",
                "created_at": "2026-06-05T20:00:00Z",
                "thesis": "Target reached before close",
            },
        ],
        selected_ticker="NVDA",
        positions_by_ticker={},
        closed_positions_by_ticker={
            "NVDA": {
                "status": "closed",
                "opened_at": "2026-06-05T14:32:00Z",
                "closed_at": "2026-06-05T20:02:00Z",
                "realized_pnl": 1250.0,
            }
        },
        risk_by_ticker={"NVDA": {"status": "approved", "reason": "within_limits"}},
        signal_history_by_ticker={},
        news_by_ticker={},
        fundamentals_by_ticker={},
    )

    detail = workspace["detail"]
    assert detail["lifecycle"]["state_label"] == "Closed"
    assert detail["lifecycle"]["opened_at"] == "2026-06-05T14:32:00Z"
    assert detail["lifecycle"]["closed_at"] == "2026-06-05T20:02:00Z"
    assert detail["lifecycle"]["realized_pnl"] == 1250.0
    assert detail["tabs"]["timeline"][-1]["event_type"] == "close"
```

- [ ] **Step 2: Run focused detail tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py tests/web/test_today.py -q`

Expected: FAIL because detail payload lacks lifecycle history and close events.

- [ ] **Step 3: Add lifecycle detail shaping to the presenter**

Implementation notes:

- Build a `lifecycle` block separate from `latest_conclusion` with:
  - primary state
  - opened/closed timestamps
  - entry decision summary
  - exit decision summary
  - realized/unrealized P&L when available
  - current execution state
- Expand `timeline` to explicitly label `entry`, `decision`, `risk`, `news`, and `close` events.
- If outcome or P&L data is absent, render explicit empty-state markers instead of dropping the block.

- [ ] **Step 4: Merge audit detail into lifecycle detail instead of raw-only fallback**

Implementation notes:

- Use `TradingDecision`, risk decision, order status, and outcome rows to populate readable lifecycle events before storing raw payloads.
- Keep raw JSON in advanced mode only.

- [ ] **Step 5: Re-run focused detail tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/presenters/today_workspace.py src/web/routers/today.py tests/web/test_today_workspace.py tests/web/test_today.py
git commit -m "feat: add ticker lifecycle detail and trade history"
```

### Task 4: Turn `Overview` into a command-center action surface

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write failing route tests for command-center rendering**

```python
def test_overview_tab_renders_action_modules_and_system_issues(client):
    response = client.get("/today?tab=overview")

    assert "Needs Review" in response.text
    assert "Open Positions" in response.text
    assert "System Issues" in response.text
    assert "Macro regime unavailable" in response.text
```

- [ ] **Step 2: Run route tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: FAIL because `Overview` still renders passive tables rather than action modules.

- [ ] **Step 3: Add route-side command-center summary shaping**

Implementation notes:

- Build overview payloads that answer:
  - what needs action now
  - what open positions are healthy vs need review
  - what system/data issues are blocking confidence
- Reuse lifecycle buckets, risk statuses, and macro/data availability rather than inventing new source queries.

- [ ] **Step 4: Recompose the overview template**

Implementation notes:

- Replace the passive alert tables at the top with 3 primary modules:
  - `Needs Review`
  - `Open Positions`
  - `System Issues`
- Keep raw alert/material-change tables below as secondary drill-downs.

- [ ] **Step 5: Re-run route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/routers/today.py src/templates/today.html src/static/style.css tests/web/test_today.py
git commit -m "feat: turn today overview into command center"
```

### Task 5: Rebuild `Risk & Macro` as summary-first with advanced drill-down

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write failing route tests for summary-first risk rendering**

```python
def test_risk_macro_tab_surfaces_operator_summary_before_raw_exposures(client):
    response = client.get("/today?tab=risk-macro")

    assert "Risk Status" in response.text
    assert "Top Risk Sources" in response.text
    assert "Data / Model Availability" in response.text
    assert "Advanced Risk Audit" in response.text
```

- [ ] **Step 2: Run risk route tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: FAIL because the tab still leads with raw exposure counts and tables.

- [ ] **Step 3: Add risk summary shaping in the route**

Implementation notes:

- Summarize:
  - whether portfolio risk is within limits / near limits / blocked
  - which tickers or factors are the main risk contributors
  - why a risk decision was approved/reduced/blocked
  - whether macro regime or required data is unavailable
- Keep factor exposures and raw decision payloads intact, but package them as advanced audit data.

- [ ] **Step 4: Recompose the risk template**

Implementation notes:

- Top section should show operator summaries and approval context.
- Move full exposure tables into an `<details>` or explicit advanced panel titled `Advanced Risk Audit`.
- Preserve accessibility and server-rendered behavior; no client-side state required.

- [ ] **Step 5: Re-run risk route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/routers/today.py src/templates/today.html src/static/style.css tests/web/test_today.py
git commit -m "feat: make today risk view summary first"
```

### Task 6: Rebuild `Candidates` around operator-facing reasons and advanced internals

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write failing route tests for translated candidate inventory**

```python
def test_candidates_tab_shows_operator_reason_copy_instead_of_internal_ids(client):
    response = client.get("/today?tab=candidates")

    assert "Why It Was Reviewed" in response.text
    assert "Current Outcome" in response.text
    assert "Negative catalyst detected" in response.text
    assert "No clean entry, so no trade" in response.text
    assert "valuation_repair_quality_software_v1" not in response.text
```

- [ ] **Step 2: Run candidate route tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: FAIL because the table still renders `selection_source`, `result_status`, `trade_identity`, and `strategy_match` raw fields.

- [ ] **Step 3: Add translated candidate presentation fields**

Implementation notes:

- `_load_candidate_rows` should return:
  - `why_reviewed_label`
  - `current_outcome_label`
  - `strategy_label`
  - `detail_internal_ids`
- Preserve raw source fields only for advanced disclosure.
- Keep manual requests separate from scanner-selected candidates as already intended in design.

- [ ] **Step 4: Recompose the candidates template**

Implementation notes:

- Replace raw-field column names with operator-facing labels.
- Add an advanced/details disclosure per row or per section for raw IDs.
- Keep universe filter controls and manual review queue, but visually demote the internal config density below the primary candidate readout.

- [ ] **Step 5: Re-run candidate route tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web/routers/today.py src/templates/today.html src/static/style.css tests/web/test_today.py
git commit -m "feat: translate today candidates into operator language"
```

### Task 7: Final verification, docs, and tracker updates

**Files:**
- Modify: `documents/repo_overview.md` if the final implementation materially changes the `/today` architecture summary
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run the focused `/today` test suite**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py tests/web/test_today_copy.py -q`

Expected: PASS.

- [ ] **Step 2: Run the broader relevant web/app regression suite**

Run: `source ~/.venv/bin/activate && pytest tests/test_app.py tests/web/test_today.py tests/web/test_today_workspace.py tests/web/test_today_copy.py -q`

Expected: PASS.

- [ ] **Step 3: Run diff hygiene checks**

Run: `git diff --check`

Expected: PASS with no whitespace or conflict-marker issues.

- [ ] **Step 4: Update repo docs if the architecture summary changed materially**

Implementation notes:

- If `/today` now depends on explicit lifecycle and copy-presenter helpers, document that in `documents/repo_overview.md`.

- [ ] **Step 5: Update the trading-agent progress tracker**

Implementation notes:

- Add the implementation date, what landed, verification commands, and commit hashes after each completed task or at the end of the slice, following the existing tracker style.

- [ ] **Step 6: Commit**

```bash
git add documents/repo_overview.md plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "docs: record today lifecycle command center follow-up"
```

## Suggested Slice Order

1. Translation layer
2. Lifecycle bucket model
3. Lifecycle detail and close history
4. Overview command center
5. Risk summary-first surface
6. Candidate translation surface
7. Verification and docs

This order keeps the semantic contract stable before touching templates, and it makes the review path clear: first the model, then the surfaces that consume it.
