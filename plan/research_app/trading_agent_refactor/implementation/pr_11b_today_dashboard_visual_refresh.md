# Today Dashboard Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh `/today` into a hybrid command-center workspace that reduces visual density, establishes clear hierarchy, and only shows the operator the currently selected work surface instead of rendering every section at once.

**Architecture:** Keep FastAPI + Jinja server rendering and the current `/today` payload structure as the source of truth. Implement the redesign with navigation-driven conditional rendering: the top-level `tab` query controls which major workstation surface is shown, the `Trades` workspace remains ticker-first, and a second layer of selection state controls which local detail panel and item detail are visible. Only touch route payload shaping where explicit selection state or item-detail helpers are needed to avoid brittle template logic.

**Tech Stack:** Python, FastAPI, Jinja2, CSS, pytest, existing `/today` router/template stack.

---

## Scope

This plan is a follow-up slice to PR 11 and PR 11A. It focuses on presentation-layer restructuring for `/today`, not on new data families or new trading logic.

In scope:

- `/today` shell layout and reading order
- top-level tab behavior that only renders the selected workstation surface
- grouped operator header
- card hierarchy and typography/spacing system
- `Trades` as the dominant workspace canvas
- ticker-first drill-down flow inside `Trades`
- local detail tab behavior that only renders the selected panel
- item-detail drill-down for timeline/history-style lists where detail payload already exists or can be shaped presentation-side
- visual demotion and density control for `Candidates`, `Risk & Macro`, `Overview`, and `Portfolio`
- responsive behavior and empty-state cleanup

Out of scope:

- schema changes
- new persisted trading artifacts
- major `today_workspace` business-logic redesign
- JS-heavy new interactions or SPA state management
- changing the meaning of existing tabs or trade/risk/candidate outputs

## File Structure

### Existing files to modify

- `src/templates/today.html`
  Recompose the page into operator strip plus conditionally rendered workstation surfaces, with `Trades` using ticker/detail drill-down.
- `src/static/style.css`
  Add the visual system for hierarchy, layout, spacing, typography, card tiers, local/global navigation separation, and responsive behavior.
- `tests/web/test_today.py`
  Update route rendering assertions to match top-level tab scoping, local detail scoping, drill-down rendering, and reduced-noise layout landmarks.
- `src/web/routers/today.py`
  Shape explicit selection state for top-level tabs, local detail tabs, and optionally selected detail items if the template cannot derive them safely inline.
- `documents/repo_overview.md`
  Update the high-level repo summary if the final implementation is a major enough UI refactor to change how `/today` is described.

## Delivery Notes

- Keep data semantics stable. If a section looks better by hiding or collapsing content, do that before inventing new data fields.
- Do not render all top-level sections in the same viewport by default. `selected_tab` must control the dominant rendered surface.
- Prefer route/query-param driven server rendering over front-end stateful tab implementations.
- Prefer template restructuring over presenter changes. Only add route-side convenience fields if it materially simplifies the template and stays presentation-only.
- Use TDD around route rendering landmarks so layout changes remain intentional.
- Keep desktop as the primary operating mode, but verify narrow-screen readability before closing the work.

## Task 1: Lock top-level tab-scoped rendering before restyling

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `src/web/routers/today.py` if explicit tab-state helpers are needed
- Modify: `src/templates/today.html`

- [ ] Write failing route assertions that each top-level tab only renders its own major content surface:
  - `tab=trades` renders the `Trades` workspace and does not render `Overview`, `Portfolio`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, or `Ops & Cost` body content
  - `tab=overview` renders only `Overview` body content
  - at least one additional non-trades tab proves the pattern is general, not special-cased
- [ ] Add assertions that the top-level tab strip remains visible while non-selected tab bodies are absent from the response.
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: FAIL because the current template still renders all major sections on the same page.
- [ ] Implement the minimum `today.html` restructuring so the top-level `selected_tab` gates body rendering while preserving the shared operator strip and global tab strip.
- [ ] If needed, add a lightweight route-side helper for normalized top-level render state instead of scattering `selected_tab` conditions throughout the template.
- [ ] Re-run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS for top-level tab scoping, with deeper visual refinements still pending.

## Task 2: Build the operator strip and grouped header hierarchy

**Files:**
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `src/web/routers/today.py` only if grouped header helpers are required
- Modify: `tests/web/test_today.py`

- [ ] Write failing tests that assert the new header grouping semantics:
  - action-driving status group
  - session-context group
  - demoted explanatory subtitle and metadata labels
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: FAIL because the current header still uses equally weighted chips plus a separate KPI row.
- [ ] Implement grouped header markup in `today.html` using existing values first:
  - open alerts
  - material changes or action count
  - buying power
  - gross exposure
  - trade date
  - macro regime
  - risk appetite
  - job status when available
- [ ] If the template becomes too brittle, add minimal route-side convenience fields in `src/web/routers/today.py` to shape header groups without changing underlying meaning.
- [ ] Add CSS for the operator strip, including:
  - primary vs secondary metric emphasis
  - quieter metadata labels
  - desktop grouping and narrow-screen wrapping
- [ ] Re-run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS with grouped header landmarks and no broken route rendering.

## Task 3: Recompose the `Trades` body into ticker buckets and a single selected ticker canvas

**Files:**
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `src/web/routers/today.py` if route-side selected detail state is needed
- Modify: `tests/web/test_today.py`

- [ ] Write failing route assertions for the `Trades` composition:
  - `Trades` renders buckets in the intended order: `Action Now`, `In Position`, `Watch`
  - the ticker rail remains a navigator and only one ticker is selected at a time
  - when `ticker` is selected, the main canvas shows that ticker's hero and support modules
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: FAIL because the current `Trades` layout still mixes visible detail surfaces and does not fully enforce the selected-ticker reading flow.
- [ ] Rework `today.html` so `tab=trades` reads as:
  - ticker bucket rail
  - one selected ticker hero block
  - one selected ticker support area
  - one local detail-navigation control
- [ ] Simplify ticker cards to the intended compact fields:
  - ticker
  - decision
  - `why now`
  - compact state badge
- [ ] Add or refine CSS layout primitives for:
  - page shell
  - trades-only workspace grid
  - support module stacks
  - ticker navigator readability
- [ ] Re-run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS, with route tests confirming the selected-ticker-first structure.

## Task 4: Make local detail tabs render one panel at a time with optional item drill-down

**Files:**
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today.py`

- [ ] Write failing route assertions for local detail state:
  - `detail_tab=timeline` renders `Timeline` and hides `Trend`, `Decisions`, and `Risk` bodies
  - `detail_tab=trend` renders `Trend` and hides the others
  - the local detail control remains visible while only one panel body is rendered
- [ ] Add failing route assertions for item drill-down behavior:
  - selecting a timeline item renders a dedicated detail panel for that item
  - the list remains a navigator, not a second fully expanded content stream
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: FAIL because the current template renders all local panels together and provides no focused item-detail view.
- [ ] Extend `/today` route loading to accept explicit local selection state, for example:
  - `detail_tab`
  - `detail_item`
  - `detail_item_index` or another stable presentation-only selector
- [ ] Rework the selected ticker detail area so it renders:
  - one hero conclusion panel
  - one decision-support module group
  - one risk/execution module group
  - one local detail-navigation control
  - one currently selected local panel body
  - one optional item-detail surface beneath the selected local panel when an item is selected
- [ ] Add CSS for hero, support, selected-panel, list/detail split, and lighter local navigation controls that are visually distinct from the global tab strip.
- [ ] Re-run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS with local detail scoping and focused item drill-down visible in rendered HTML.

## Task 5: Rebuild non-trades tabs as focused standalone surfaces instead of same-page secondary cards

**Files:**
- Modify: `src/templates/today.html`
- Modify: `src/static/style.css`
- Modify: `tests/web/test_today.py`

- [ ] Write failing tests for per-tab focused rendering:
  - `Overview` only shows overview content blocks
  - `Portfolio` only shows portfolio content blocks
  - `Risk & Macro` only shows risk/macro content blocks
  - `Candidates` only shows candidate/universe/manual-request content blocks
- [ ] Add lower-noise assertions within those focused tabs:
  - active universe filter summarized before full controls
  - `manual requests` isolated as an operation module
  - `Risk & Macro` surfaces constraints and top summary before long tables
  - quiet empty states for `Overview` and `Portfolio`
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: FAIL because current layout still assumes these surfaces live together on one page.
- [ ] Recompose each non-trades tab as its own standalone surface with one clear heading, one primary summary zone, and lower-priority tables/controls below.
- [ ] Recompose `Candidates` so the summary and primary actions precede dense controls and tables.
- [ ] Recompose `Risk & Macro` so the first read is config + constraints + top exposure context, with long exposure rows visually secondary.
- [ ] Tighten `Overview` and `Portfolio` headings, spacing, and empty-state rendering so they read as focused destinations rather than leftovers from a composite dashboard.
- [ ] Add CSS for standalone tab surfaces, quieter section cards, summary rows, compact tables, and subdued empty states.
- [ ] Re-run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS with non-trades tabs rendered as focused destinations.

## Task 6: Finish responsive behavior, empty states, and repo docs

**Files:**
- Modify: `src/static/style.css`
- Modify: `src/templates/today.html`
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today.py`
- Modify: `documents/repo_overview.md` if the implementation materially changes the `/today` architecture description

- [ ] Add or extend route assertions for empty-state and narrow-layout-safe rendering:
  - no selected ticker
  - no live alerts
  - no material changes
  - no rows in major buckets
  - invalid `tab` falls back safely
  - invalid local `detail_tab` falls back safely
  - invalid `detail_item` falls back safely without rendering a broken detail panel
- [ ] Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q`
  Expected: PASS or expose any remaining empty-state regressions.
- [ ] Finalize CSS responsive behavior for:
  - operator strip wrapping
  - primary workspace collapsing
  - local list/detail drill-down collapsing
  - table overflow handling
  - ticker rail readability
- [ ] Replace repetitive unavailable/no-update strings where necessary with quieter, standardized empty-state treatments.
- [ ] Update `documents/repo_overview.md` if the final implementation changes the repo-level description of the `/today` UI architecture.
- [ ] Run broader web verification:
  - `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_workspace.py -q`
  Expected: PASS.
- [ ] Run final targeted regression check:
  - `source ~/.venv/bin/activate && pytest tests/web -q`
  Expected: PASS.

## Suggested Commit Boundaries

Use small commits aligned to visible milestones:

1. `test: lock today visual refresh shell expectations`
2. `feat: scope today rendering to the selected global tab`
3. `feat: add today operator strip and trades workspace hierarchy`
4. `feat: add local detail tab selection and item drilldown`
5. `feat: rebuild non-trades tabs as focused standalone surfaces`
6. `docs: update repo overview for today workspace refresh`

## Verification Checklist

Before calling the work complete:

- `/today` first viewport makes primary vs secondary content obvious
- only the selected top-level tab body renders at one time
- global and local navigation controls no longer compete visually
- selected ticker detail reads as a hero-led workspace rather than a long text stack
- local detail navigation renders one panel at a time, not all panels together
- timeline/history-style lists can drill into one selected item detail without expanding every item at once
- non-trades tabs read as focused destinations rather than secondary leftovers
- empty states are quiet and consistent
- focused and broader web tests pass
