# Today Dashboard Operator UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/today` as an operator workstation that is readable under real trading volume: dedupe repeated candidates and signals, show meaningful timeline deltas, add bounded scroll regions, and render the backend risk/macro/event read model from `2026-06-15-risk-macro-event-backend-contract.md`.

**Architecture:** Keep FastAPI + server-rendered Jinja, but move aggregation and display decisions out of `today.py`/template loops into presenter modules. The route returns tab-specific read models for overview, trades, risk/macro, and candidates; the template renders those models with compact default views, collapsible advanced audit details, and CSS-bounded scroll containers.

**Tech Stack:** Python, pytest, FastAPI, Jinja2, CSS, existing `/today` route and presenters.

---

## Required Pre-Read

- `documents/general_instructions.md`
- `plan/research_app/trading_agent_refactor/design/09_ui_error_testing_delivery.md`
- `docs/superpowers/specs/2026-06-03-ticker-first-today-dashboard-design.md`
- `docs/superpowers/specs/2026-06-04-today-dashboard-visual-refresh-design.md`
- `docs/superpowers/specs/2026-06-05-today-trend-panel-design.md`
- `docs/superpowers/plans/2026-06-15-risk-macro-event-backend-contract.md`
- `docs/superpowers/plans/2026-06-15-manual-review-execution-audit-contract.md`
- `docs/superpowers/plans/2026-06-15-research-signal-expansion-into-trading.md`

## Dependency Boundary

- This frontend plan can start with fixture-backed presenter tests.
- The final `Risk & Macro` tab must consume the backend read model from `src/web/presenters/today_risk_macro.py`.
- Manual-review queue/detail UI must consume backend request-audit fields from `2026-06-15-manual-review-execution-audit-contract.md` instead of re-deriving decision/order linkage inside Jinja loops.
- Insider and social/policy signal display must consume structured fields from `2026-06-15-research-signal-expansion-into-trading.md` instead of dumping raw `signal_json` families or raw source rows into Jinja.
- Do not make the frontend query macro/event tables directly.
- Do not implement manual-review execution policy changes in this plan; only consume the backend linkage/availability contract.
- Do not hide backend data gaps with optimistic placeholder text; show degraded availability from the backend model.

## Current UI Problems This Plan Addresses

- Macro/risk data is missing because backend contracts are absent or not consumed.
- The page header does not keep session-state chips such as market phase, macro/risk posture, runtime mode, and live/degraded state in one compact always-visible strip.
- KPI cards and panels do not consistently disclose `last updated`, source-of-truth, or whether a number is broker/live, review-window realized, or estimated.
- Signal summaries and timeline entries repeat raw snapshot text instead of surfacing deltas.
- Candidate decisions show many duplicate rows for the same ticker, especially `AAPL`.
- Manual review cards do not show dismiss controls, evaluation recency, or whether a request is linked to a signal snapshot / trade audit path yet.
- Long rails/lists do not have bounded scroll, so the page becomes visually unbounded.
- Dense sections like `Signal Summary` show too many bullets at once.
- The `Trades` tab does not make differences between pre-open/intraday runs visible.
- The `Risk & Macro` tab is mostly a shallow metadata view instead of an operator risk surface.
- Material insider pressure and policy/social shocks are not selectively surfaced; they would either be invisible or appear as noisy raw snapshot text.

## Reference Patterns To Borrow

- Add a compact operator strip that keeps `session state`, `macro/risk posture`, `runtime mode`, and `alert count` visible without forcing a scroll back to the top.
- Add per-card and per-panel freshness plus truth-basis metadata so mixed metrics do not read like they came from the same source.
- Treat `Risk & Macro` as a command center first, with a terse summary row and warning banner before deep audit tables.
- Use row-summary plus expandable evidence modules for signals, trades, and manual-review audit instead of long raw bullet piles.
- Keep live alerts compact by default: show count/severity first, details second.

## File Map

- `src/web/routers/today.py`
  - Keep route orchestration; delegate read-model construction to presenters.
- `src/web/presenters/today_workspace.py`
  - Extend or split ticker workspace presenter for trade rail, selected ticker, signal summary, and timeline deltas.
- `src/web/presenters/today_candidates.py`
  - New candidate dedupe and action-queue presenter.
- `src/web/presenters/today_overview.py`
  - New overview command-surface presenter for the operator strip, KPI cards, truth-basis copy, and current-summary card.
- `src/web/presenters/today_risk_macro.py`
  - Consume backend risk/macro/event read model; if implemented by the backend plan, refine frontend-specific sections here.
- `src/web/presenters/today_copy.py`
  - Add concise labels for event severity, macro regime, risk state, candidate grouping, and timeline change types.
- `src/templates/today.html`
  - Render compact read-model sections instead of raw row expansions.
- `src/static/style.css`
  - Add scroll containers, sticky rails, improved density, responsive grids, and status styling.
- `tests/web/test_today.py`
  - Existing route regression coverage.
- `tests/web/test_today_workspace.py`
  - Extend for timeline deltas, summary truncation, and scroll classes.
- `tests/web/test_today_candidates.py`
  - New candidate dedupe/action queue tests.
- `tests/web/test_today_risk_macro.py`
  - Risk/macro rendering contract tests.
- `tests/web/test_today_copy.py`
  - Label/copy coverage.
- `documents/repo_overview.md`
  - Update UI architecture summary after implementation.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Implementation status and verification evidence.

## UI Read Model Shape

Presenters should emit stable structures like this before template rendering:

```python
@dataclass(frozen=True)
class PanelMetaView:
    updated_at_label: str | None
    refresh_mode_label: str | None
    source_of_truth_label: str | None
    basis_note: str | None
    degraded_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OperatorMetricCardView:
    metric_id: str
    label: str
    primary_value: str
    secondary_value: str | None
    tone: str
    meta: PanelMetaView


@dataclass(frozen=True)
class CandidateGroupView:
    ticker: str
    latest_outcome: str
    primary_reason: str
    trade_identity: str | None
    latest_decision_time: datetime | None
    best_strategy: str | None
    alternatives: tuple[CandidateAlternativeView, ...]
    duplicate_count: int
    action_required: bool
    priority: int


@dataclass(frozen=True)
class TimelineEventView:
    event_id: str
    phase: str
    event_time: datetime | None
    title: str
    summary: str
    change_type: str
    delta_fields: tuple[str, ...]
    severity: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class SignalSummaryView:
    headline: str
    primary_bullets: tuple[str, ...]
    hidden_bullet_count: int
    grouped_sections: tuple[SignalGroupView, ...]
```

Rules:

- Templates render only read-model fields, not raw SQLAlchemy model fields.
- Every top metric, command panel, and AI-cost summary exposes `updated_at_label`; metrics with non-obvious provenance also expose `source_of_truth_label` and `basis_note`.
- Default view shows the highest-signal 3 to 5 bullets; the rest lives under collapsible details.
- Every repeated row must have an explicit `duplicate_count`, `alternatives`, or `source_refs` explanation.
- Surfaces that compare model intent vs execution must carry separate decision-state and execution-state labels instead of collapsing them into one ambiguous status string.
- Panels that mix live broker numbers with review-window or estimated analytics must render a brief truth-basis explainer rather than implying identical provenance.
- `insider` and `social_macro` families are selective-display families: default UI only shows material cluster buys/sales, large net insider imbalance, or fresh high-importance policy/social items with ticker/theme impact; the rest stays behind audit details.
- Scroll is layout behavior, not data loss: counts must still show total available items.

## Task 0: Build Operator Strip And Metric-Provenance Surface

**Files:**

- Create: `src/web/presenters/today_overview.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/web/routers/today.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Test: `tests/web/test_today.py`
- Test: `tests/web/test_today_copy.py`

- [ ] Step 1: Write failing tests for an operator strip that shows `market phase`, `macro regime`, `risk appetite`, `runtime mode`, live/degraded status, and alert count, plus KPI cards with `updated_at_label`, `source_of_truth_label`, and optional `basis_note`.
- [ ] Step 2: Build `today_overview` presenter output for `operator_strip`, `metric_cards`, `alert_bar`, and `current_summary`.
- [ ] Step 3: Render a compact header that stays scannable on one screen and visually separates action-driving chips from contextual chips.
- [ ] Step 4: Add truth-basis copy for mixed metrics such as broker equity vs realized review-window P&L vs estimated AI cost.
- [ ] Step 5: Keep the longer current-state narrative behind a bounded, collapsible summary card with explicit timestamp.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_copy.py -q`.

Expected result: the top of `/today` answers “what state am I operating in right now?” without forcing the operator to infer metric provenance.

## Task 1: Create Candidate Dedupe Presenter

**Files:**

- Create: `src/web/presenters/today_candidates.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/web/routers/today.py`
- Test: `tests/web/test_today_candidates.py`
- Test: `tests/web/test_today.py`

- [ ] Step 1: Write failing tests where four `AAPL` candidate rows collapse into one group with three alternatives.
- [ ] Step 2: Define grouping key priority: `ticker`, latest decision date/run, current outcome, trade identity, strategy lens.
- [ ] Step 3: Implement one primary row per ticker for default display, sorted by action priority, latest material change, then score.
- [ ] Step 4: Keep alternatives visible under a collapsible `Strategy alternatives` section.
- [ ] Step 5: Replace `_load_candidate_rows` direct display behavior with presenter output.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py tests/web/test_today.py -q`.

Expected result: `Candidates` no longer shows repeated `AAPL` cards as separate default rows.

## Task 2: Rebuild Candidate Action Queue And Manual Review Blocks

**Files:**

- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Test: `tests/web/test_today_candidates.py`

- [ ] Step 1: Write failing tests for pinned/manual requests being separated from scanner-derived candidate rows and for each manual-review card to expose dismiss controls, latest evaluation recency, and linked-audit state.
- [ ] Step 2: Build `action_queue`, `manual_review_queue`, and `decision_readout` as separate presenter sections, with manual-review rows carrying backend-fed fields such as `last_evaluated_label`, `linked_detail_url`, `decision_state_label`, `execution_state_label`, `latest_block_reason`, and `dismiss_form_action`.
- [ ] Step 3: Show only reason, latest result, evaluation recency, required operator action, and model-intent-vs-execution-state summary in queue cards, plus explicit degraded copy when backend audit linkage is still unavailable.
- [ ] Step 4: Move raw advanced fields behind `<details>`.
- [ ] Step 5: Add bounded scroll to long queue/readout lists.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py -q`.

Expected result: operator queue becomes actionable, manual-review cards expose controls and auditability, and dense candidate audit stays available without dominating the page.

## Task 3: Build Meaningful Trade Timeline Delta Model

**Files:**

- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/web/routers/today.py`
- Modify: `src/templates/today.html`
- Test: `tests/web/test_today_workspace.py`

- [ ] Step 1: Write failing tests for repeated `pre_open` entries where only catalyst quality or risk status changes.
- [ ] Step 2: Add timeline grouping by run/source record and dedupe exact duplicate summaries.
- [ ] Step 3: Compute `delta_fields`, e.g. `sentiment neutral -> negative`, `risk approved -> reduced`, `candidate watch -> blocked`, `new event`, `stale source`.
- [ ] Step 4: Rename repeated phases with sequence and time context, e.g. `Pre-open baseline`, `Pre-open rerun`, `Intraday refresh 10:30`.
- [ ] Step 5: Render a two-pane timeline: compact event list on the left, selected event details on the right.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`.

Expected result: the `Trades` timeline explains what changed in each run instead of repeating the same `pre_open` text.

## Task 4: Reduce Signal Summary Density

**Files:**

- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Test: `tests/web/test_today_workspace.py`

- [ ] Step 1: Write failing tests that a 26-bullet signal summary renders 3 to 5 primary bullets plus grouped hidden sections.
- [ ] Step 2: Rank bullets by materiality: decision/risk blockers, direct catalysts, insider pressure, policy/social shocks, technical trend, fundamentals, freshness.
- [ ] Step 3: Dedupe semantically identical bullets from consecutive snapshots.
- [ ] Step 4: Add grouped sections: `Decision drivers`, `Risk blockers`, `Insider`, `Policy / Social`, `Trend`, `Evidence`, `Data quality`.
- [ ] Step 5: Add collapsed audit details for full source text.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`.

Expected result: signal summary becomes scannable while retaining auditability, and only material insider/policy-social items appear in the default view.

## Task 5: Render The Full Risk & Macro Surface

**Files:**

- Modify: `src/web/presenters/today_risk_macro.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Test: `tests/web/test_today_risk_macro.py`
- Test: `tests/web/test_today.py`

- [ ] Step 1: Write failing tests for visible macro regime, risk budget multiplier, blocked tags, top risk sources, event calendar cards, selective policy/social shock cards, binding constraints, exposures, and availability issues.
- [ ] Step 2: Render macro as a compact command strip: `regime`, `risk appetite`, `exposure usage`, `event risk`, `volatility`, and `freshness`.
- [ ] Step 3: Render event risk and policy/social risk as filtered table/card lists with `event`, `affected ticker or theme`, `days`, `severity`, `recommended action`, and `why visible`.
- [ ] Step 4: Render risk sources, binding constraints, favored/avoided exposures, and hedge posture as priority chips, not paragraph text.
- [ ] Step 5: Render advanced risk audit under collapsed details with raw exposure rows and metadata refs.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_risk_macro.py tests/web/test_today.py -q`.

Expected result: `Risk & Macro` is no longer empty/degraded when backend data exists, material policy/social shocks are selectively visible, and degraded mode is explicit when it does not.

## Task 6: Refactor `/today` Route Around Presenters

**Files:**

- Modify: `src/web/routers/today.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/web/presenters/today_risk_macro.py`
- Test: `tests/web/test_today.py`
- Test: `tests/web/test_today_workspace.py`
- Test: `tests/web/test_today_candidates.py`
- Test: `tests/web/test_today_risk_macro.py`

- [ ] Step 1: Write tests that the route context contains presenter outputs, not raw repeated rows for tabs, including manual-review presenter outputs that normalize backend audit linkage into stable fields and an explicit unlinked/degraded state when the backend contract has not produced one yet.
- [ ] Step 2: Keep DB loading in `today.py`, but move aggregation/ranking/grouping to presenters.
- [ ] Step 3: Add small loader helpers only where DB joins are unavoidable.
- [ ] Step 4: Preserve existing tab URLs and form actions.
- [ ] Step 5: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py tests/web/test_today_candidates.py tests/web/test_today_risk_macro.py -q`.

Expected result: UI behavior is testable without inspecting template loops or live DB state.

## Task 7: Rework Template Structure

**Files:**

- Modify: `src/templates/today.html`
- Test: `tests/web/test_today.py`
- Test: `tests/web/test_today_workspace.py`
- Test: `tests/web/test_today_candidates.py`
- Test: `tests/web/test_today_risk_macro.py`

- [ ] Step 1: Split each tab into clear sections: `status strip`, `primary work area`, `secondary audit/details`.
- [ ] Step 2: Replace repeated `<ul>` dumps with semantic cards/tables that show count, status, reason, freshness, and truth-basis metadata where needed.
- [ ] Step 3: Use `<details>` for advanced source context and raw metadata.
- [ ] Step 4: Add stable `data-testid` attributes for critical sections: candidate groups, timeline events, signal summary, macro strip, event risk list.
- [ ] Step 5: Preserve accessibility basics: headings, table headers, form labels, and focusable controls.
- [ ] Step 6: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py tests/web/test_today_candidates.py tests/web/test_today_risk_macro.py -q`.

Expected result: the template becomes a renderer of concise sections, not a dumping ground for backend rows.

## Task 8: Add Bounded Scroll, Sticky Rails, And Responsive Layout

**Files:**

- Modify: `src/static/style.css`
- Test: `tests/web/test_today_workspace.py`
- Test: `tests/web/test_today_candidates.py`

- [ ] Step 1: Add CSS classes for bounded scroll containers: `.scroll-rail`, `.scroll-panel`, `.scroll-table`, `.audit-scroll`.
- [ ] Step 2: Make the ticker rail sticky on desktop with a viewport-relative max height.
- [ ] Step 3: Make candidate decision lists and timeline event lists scroll within their panels.
- [ ] Step 4: Keep horizontal table overflow for wide portfolio/risk tables.
- [ ] Step 5: Add mobile breakpoints that collapse rails above content and remove sticky behavior.
- [ ] Step 6: Add tests that critical scroll classes appear in rendered HTML.
- [ ] Step 7: Run `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py tests/web/test_today_candidates.py -q`.

Expected result: long content is navigable without making the whole page visually endless.

## Task 9: Add Visual/Operator Smoke Coverage

**Files:**

- Modify: `tests/web/test_today.py`
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] Step 1: Add route tests for all primary tabs: `overview`, `portfolio`, `trades`, `risk_macro`, `candidates`, `learning`, `ops`.
- [ ] Step 2: Add regression tests for empty states, degraded backend availability, large repeated candidate/timeline fixtures, and manual-review cards with both linked and unlinked backend audit states.
- [ ] Step 3: Update docs with the new presenter-based UI architecture.
- [ ] Step 4: Update the progress tracker with implementation status and verification evidence after each completed task.
- [ ] Step 5: Run `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py tests/web/test_today_copy.py tests/web/test_today_candidates.py tests/web/test_today_risk_macro.py -q`.
- [ ] Step 6: Run `git diff --check`.

Expected result: the UI fixes are locked by route/presenter tests, not only visual inspection.

## Acceptance Criteria

- `Risk & Macro` renders backend macro, event calendar, event-risk, exposure, and availability data when present.
- The operator strip and KPI cards disclose freshness and truth-basis so broker/live, review-window, and estimated metrics are not visually conflated.
- `Candidates` defaults to one visible group per ticker/outcome, with strategy alternatives nested.
- Manual-review queue cards show dismiss controls, latest evaluation recency, and a drill-down path into the same audit surface when backend linkage exists.
- `Trades` timeline shows material deltas and source/time context for each run.
- `Signal Summary` shows a concise primary summary with grouped/collapsible details.
- Material insider and social/policy signals are selectively surfaced in default views and otherwise remain available behind progressive disclosure.
- Long rails and lists have bounded scroll behavior on desktop and sane stacking on mobile.
- Existing tab navigation and pinned review/manual request actions keep working.
- Empty/degraded states are explicit and do not imply data exists when backend contract is missing, including when manual-review linkage fields are not yet available from the backend.

## Non-Goals

- Do not create or migrate macro/event backend tables in this frontend plan.
- Do not change trading, sizing, risk approval, or broker execution behavior.
- Do not define or change `paper_trade_eligible` execution policy in this frontend plan; that belongs to the dedicated manual-review backend contract plan.
- Do not add a client-side framework; keep this server-rendered unless a future plan justifies the dependency.
- Do not remove audit detail; move it behind progressive disclosure.
