# Today Candidate/Trade Semantic Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/today` route and presenter logic separate review-only/non-actionable candidate surfaces from actionable trade-path surfaces without changing manual request creation or trading logic.

**Architecture:** Keep the existing `/today` tabs and trading pipelines, but move the display split to the route/read-model boundary in `today.py`. Candidates will receive only review-only or non-actionable rows, while the Trades workspace will be seeded only from actionable trade-path rows plus real position lifecycle state. Risk/news/fundamental datasets remain detail enrichers, not ticker discovery sources.

**Tech Stack:** Python, FastAPI/Jinja, existing today presenters, pytest.

**Design Doc:** [13_today_candidate_trade_semantic_split.md](../design/13_today_candidate_trade_semantic_split.md)

---

## File map

- Modify: `src/web/routers/today.py`
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `tests/web/test_today.py`
- Modify: `tests/web/test_today_candidates.py`
- Modify: `tests/web/test_today_workspace.py`
- Modify after implementation: `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Task 1: Lock the routing semantics with failing tests

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `tests/web/test_today_candidates.py`
- Modify: `tests/web/test_today_workspace.py`

- [ ] **Step 1: Add failing candidate-surface tests**

Add focused tests that prove:

```python
assert review_only_actionable_ticker in candidate_rows
assert paper_trade_eligible_actionable_ticker not in candidate_rows
assert non_actionable_watch_ticker in candidate_rows
```

- [ ] **Step 2: Add failing trades-workspace tests**

Add focused tests that prove:

```python
assert actionable_ticker in workspace_tickers
assert actionable_no_trade_ticker in workspace_tickers
assert context_only_ticker not in workspace_tickers
```

Also cover the `review_only` precedence case:

```python
assert review_only_actionable_ticker not in workspace_tickers
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k "candidate or trades or manual_review"`

Expected: FAIL because the current route/workspace logic still mixes actionable, watch-only, and
context-only tickers.

## Task 2: Split route-level read models by display ownership

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Add explicit row-splitting helpers**

Introduce focused helpers in `today.py` that answer:

- is this row candidate-surface?
- is this row trade-surface?
- is this manual request `review_only`?
- does this ticker have a trade-path decision state?

Keep the rules aligned with the design doc:

- `review_only` -> Candidates
- non-actionable -> Candidates
- actionable non-review-only -> Trades

- [ ] **Step 2: Build separate route payloads**

Update `load_today_dashboard(...)` so it derives:

- candidate-surface rows for `build_today_candidates_view(...)`
- trade-workspace seed rows for `build_ticker_workspace(...)`

Do not keep asking downstream presenters to infer ownership from mixed raw rows.

- [ ] **Step 3: Run route tests**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k "candidate or trades or manual_review"`

Expected: PASS for routing semantics while other presenter expectations may still fail.

## Task 3: Restrict Candidates to review-only and non-actionable outcomes

**Files:**
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `tests/web/test_today_candidates.py`
- Modify: `src/templates/today.html`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Make presenter assumptions explicit**

Update `today_candidates.py` so it treats incoming rows as already candidate-surface owned. Remove
any remaining assumptions that actionable trade-path rows belong in the generic candidate decision
readout.

- [ ] **Step 2: Rename candidate-facing labels where needed**

If the template still uses ambiguous `watch` wording for candidate-surface rows, update the wording
so it clearly represents review-only / watch-only / blocked candidate outcomes rather than
trade-path no-trade outcomes.

- [ ] **Step 3: Run candidate tests**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k candidate`

Expected: PASS.

## Task 4: Seed Trades only from the trade path

**Files:**
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `tests/web/test_today_workspace.py`
- Modify: `src/templates/today.html`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Write the minimal workspace change**

Change `build_ticker_workspace(...)` so ticker discovery is based on:

- actionable trade-surface rows
- persisted trade decisions
- open positions
- recent closed positions

Risk, signal, news, and fundamentals remain available for detail enrichment but must not create a
new workspace ticker by themselves.

- [ ] **Step 2: Distinguish reviewed-no-trade from watch-only**

Update workspace bucket labeling so actionable trade-path rows that resolved to `no_trade` or `hold`
do not render as the same `watch` concept used by watch-only/non-actionable candidates.

- [ ] **Step 3: Run workspace tests**

Run:
- `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py -q -k trades`

Expected: PASS.

## Task 5: Final verification and tracker update

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run final verification**

Run:
- `source ~/.venv/bin/activate && python -m py_compile src/web/routers/today.py src/web/presenters/today_candidates.py src/web/presenters/today_workspace.py`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_candidates.py tests/web/test_today_workspace.py -q`

- [ ] **Step 2: Render verification**

Inspect `/today?tab=candidates` and `/today?tab=trades` and verify:

- `review_only` rows remain on Candidates
- actionable non-review-only rows appear on Trades
- reviewed no-trade trade-path rows are not labeled as generic watch-only candidates
- context-only tickers no longer appear in Trades

- [ ] **Step 3: Update the progress tracker**

Add a dated entry summarizing the semantic split implementation and the exact verification commands
and results.

- [ ] **Step 4: Commit**

```bash
git add src/web/routers/today.py src/web/presenters/today_candidates.py src/web/presenters/today_workspace.py src/templates/today.html tests/web/test_today.py tests/web/test_today_candidates.py tests/web/test_today_workspace.py plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "fix: split today candidate and trade display semantics"
```
