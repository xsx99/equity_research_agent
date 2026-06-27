# PR 36 Timezone-Aware Reflection + Push Date Filters Into SQL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reflection must never silently skip a day because of a UTC-vs-local timezone boundary, and the repository must stop loading whole tables into memory only to filter them in Python by `.date()`. Both are the same bug surface: derive the trade-day window in the scheduler timezone, and push that window into timezone-aware SQL `WHERE` clauses.

**Architecture:** Introduce one helper that, given a `trade_date` (a calendar date in `SCHEDULER_TIMEZONE`) and the configured timezone, returns the `[start_utc, end_utc)` half-open instant range covering that local trading day. Reflection derives `trade_date` from local time, not `decision_time.date()` (which is UTC). Every `session.query(Model).all()` in the reflection load path (and the ~56 sibling `.all()` + Python `.date()==trade_date` sites across `repositories/mixins/`) is rewritten to `.filter(col >= start_utc, col < end_utc)` so Postgres does the filtering on indexed timestamp columns.

**Tech Stack:** Python, SQLAlchemy, Postgres (timezone-aware `DateTime(timezone=True)` columns), `zoneinfo`, pytest.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md` — reflection inputs contract
3. `plan/implementation/README.md` — Execution Rules
4. `plan/design/07_replay_reflection_learning.md`
5. `plan/progress_tracker.md` — **Recent** section only
6. `plan/review_backlog.md` — items #2 and #4 (this PR implements both)

## Context: what is broken today (verified file:line)

**Timezone skip** — `src/trading/runtime/reflection.py:85-90`:
```python
def run(self) -> dict[str, Any]:
    decision_time = self.now()                       # datetime.now(timezone.utc) — UTC
    load_result = self.dependencies.request_loader.load(
        trade_date=decision_time.date(),             # UTC calendar date
        decision_time=decision_time,
    )
```
The reflection job is scheduled at ~16:20 in `SCHEDULER_TIMEZONE` (US market close). When local 16:20 is past UTC midnight (it is not for US/Eastern, but the bug bites for any non-UTC `SCHEDULER_TIMEZONE` whose local trading day straddles a UTC date boundary, and for the symmetric early-morning case), `decision_time.date()` (UTC) names a different calendar day than the rows were written under, so the day's rows are missed.

**Naive combine + whole-table load** — `src/trading/repositories/mixins/reflection.py:13-19`:
```python
def load_reflection_inputs(self, *, trade_date: date) -> dict[str, object]:
    latest_portfolio_snapshot = (
        self.session.query(PortfolioSnapshotModel)
        .filter(PortfolioSnapshotModel.snapshot_time >= datetime.combine(trade_date, datetime.min.time()))   # naive datetime vs tz-aware column
        .all()
    )
    portfolio_rows = [row for row in latest_portfolio_snapshot if row.snapshot_time.date() == trade_date]      # Python-side .date() filter
```
`datetime.combine(trade_date, datetime.min.time())` is **naive** (no tzinfo); comparing it against a `DateTime(timezone=True)` column is both a correctness hazard and only a lower bound — the function then re-filters in Python with `row.snapshot_time.date() == trade_date`, which evaluates `.date()` in whatever tz the driver returns (UTC), reintroducing the boundary bug.

**Whole-table loads** — the rest of `load_reflection_inputs` (`reflection.py:21-123`) issues `self.session.query(Model).all()` for `PortfolioRiskSnapshot`, `DailyReflection`, `RiskHedgeDecision`, `CandidateScore`, `ManualTickerRequest`, `TradingDecision`, `NewsAlert`, `IntradayRebalanceDecision`, `PaperOrder`, `PaperExecution`, `RiskFactorExposure`, `CandidateOutcomeEvaluation`, `OptionStrategyDecision`, `PaperOptionPositionModel`, `OptionRiskSnapshot` — each `.all()` then filtered in Python by `.date() == trade_date` (or `== trade_date` for `Date` columns). The backlog counts ~56 such `.all()` + Python-filter sites across `repositories/mixins/`. As data grows these load entire tables per reflection run.

## The fix in one sentence

`trade_date` = "today" in `SCHEDULER_TIMEZONE`; window = `[local_midnight(trade_date) → UTC, local_midnight(trade_date+1) → UTC)`; filter every timestamp column with `col >= start_utc AND col < end_utc`. Columns that are `Date` (not `DateTime`) — `PaperOrder.trade_date`, `PaperExecution.trade_date`, `DailyReflection.trade_date` — keep an `== trade_date` equality (they already store the trade day directly; confirm at each site).

## Guardrails

- **Behavior parity on the result set:** for any day fully inside one UTC date the new query must return the same rows as today. Add a regression test that runs the same fixture both ways.
- Do not change the shape of the `load_reflection_inputs` return dict (it feeds `ReflectionPipelineRequest` field-for-field — see `reflection.py:37-63`). Only change HOW rows are selected.
- Distinguish `DateTime(timezone=True)` columns (range filter) from `Date` columns (equality). Audit each model before rewriting — see the column map in Task 2.
- All produced bound datetimes must be timezone-aware (UTC). Never compare a naive datetime against a tz-aware column.
- `SCHEDULER_TIMEZONE` comes from config — read it from the same place the scheduler does; do not hardcode `US/Eastern`.
- Keep the "latest snapshot" / "max(...)" reductions (e.g. `latest_snapshot`, `latest_risk_snapshot`, `latest_reflection`) — those are correct selections within the window; just feed them the windowed rows.

## File Map

- Create: `src/trading/runtime/trade_day.py` — `trade_date_for(now, tz)` + `local_day_bounds_utc(trade_date, tz) -> tuple[datetime, datetime]`
- Modify: `src/trading/runtime/reflection.py` — derive `trade_date` in scheduler tz; pass window or trade_date to the loader
- Modify: `src/trading/repositories/mixins/reflection.py` — rewrite `load_reflection_inputs` to filter in SQL using the window
- Modify: other `repositories/mixins/*.py` files with `.all()` + Python `.date()` filters — sweep (Task 4); enumerate first, rewrite the date-filtered ones
- Modify: `src/core/config.py` (only if a tz accessor helper is needed; reuse existing `SCHEDULER_TIMEZONE`)
- Create: `tests/trading/test_pr36_trade_day_window.py`
- Create/Modify: `tests/trading/test_reflection_*` — add timezone-boundary + parity cases
- Modify: `plan/progress_tracker.md`
- Modify: `plan/review_backlog.md` — strike items #2 and #4 when done

## Task 1: The trade-day window helper

**Files:** `src/trading/runtime/trade_day.py`, `tests/trading/test_pr36_trade_day_window.py`.

- [ ] Step 1: Write a failing test first. Cases:
  - `trade_date_for(now=<UTC instant that is 2026-03-10 23:30 UTC>, tz="America/New_York")` → `date(2026, 3, 10)` (local 19:30, same day) — the realistic 16:20 ET close case.
  - The symmetric straddle: an instant where UTC date and local date differ, asserting the local date wins.
  - `local_day_bounds_utc(date(2026, 3, 10), "America/New_York")` → `(2026-03-10T05:00:00+00:00, 2026-03-11T05:00:00+00:00)` (EST, UTC-5). Add a DST-boundary case (spring-forward day) to prove the helper uses `zoneinfo`, not a fixed offset.
- [ ] Step 2: Implement using `zoneinfo.ZoneInfo`. `trade_date_for(now, tz)` = `now.astimezone(ZoneInfo(tz)).date()`. `local_day_bounds_utc(trade_date, tz)` = localize `datetime.combine(trade_date, time.min)` and `combine(trade_date + 1 day, time.min)` in the tz, then `.astimezone(timezone.utc)`. Return tz-aware UTC datetimes. Both bounds must be timezone-aware.
- [ ] Step 3: Make the test pass. Keep the module dependency-free (stdlib only) so it is trivially unit-testable.

## Task 2: Audit the column types (do this before rewriting queries)

- [ ] Step 1: For every model touched by `load_reflection_inputs`, record whether the filtered column is `DateTime(timezone=True)` or `Date`. From `src/db/models/trading/execution.py` already known: `PortfolioSnapshot.snapshot_time` = DateTime(tz); `PaperOrder.trade_date` = `Date`; `PaperExecution.trade_date` = `Date`; `OptionStrategyDecision.created_at` = DateTime(tz); `PaperOptionPosition.opened_at` = DateTime(tz). For the rest (`PortfolioRiskSnapshot.decision_time`, `DailyReflection.trade_date`, `RiskHedgeDecision.created_at`, `CandidateScore.decision_time`, `ManualTickerRequest.created_at`/`last_evaluated_at`, `TradingDecision.decision_time`, `NewsAlert.created_at`, `IntradayRebalanceDecision.decision_time`, `RiskFactorExposure` (filtered by FK, not date), `CandidateOutcomeEvaluation.decision_time`, `OptionRiskSnapshot.created_at`) — read the model files and classify each.
- [ ] Step 2: Write the classification into the PR description / a comment block. DateTime columns → range filter `col >= start_utc, col < end_utc`. Date columns → `col == trade_date`. FK-keyed selections (e.g. `RiskFactorExposure.portfolio_risk_snapshot_id == risk_snapshot_id`) stay as-is.

## Task 3: Rewrite `load_reflection_inputs`

**Files:** `src/trading/repositories/mixins/reflection.py`.

- [ ] Step 1: Change the signature to accept the window (preferred: `load_reflection_inputs(self, *, trade_date: date, window: tuple[datetime, datetime])`), or compute the window inside from `trade_date` + the configured tz. Keep `trade_date` for the `Date`-column equalities. Decide one approach and apply it consistently; passing the window in from the loader keeps the repo tz-agnostic and is preferred.
- [ ] Step 2: Replace the naive `datetime.combine(...)` portfolio-snapshot filter with `.filter(PortfolioSnapshotModel.snapshot_time >= start_utc, PortfolioSnapshotModel.snapshot_time < end_utc).all()`; drop the Python `row.snapshot_time.date() == trade_date` re-filter.
- [ ] Step 3: For each remaining `self.session.query(Model).all()` + Python `.date()==trade_date` block (`reflection.py:21-122`), move the predicate into `.filter(...)` per the Task 2 classification. For `ManualTickerRequest` (filtered on `created_at` OR `last_evaluated_at`), use `or_(and_(created_at >= start, created_at < end), and_(last_evaluated_at >= start, last_evaluated_at < end))`. Preserve the existing extra predicates (e.g. `decision not in {"no_trade","hold"}` for `trading_decisions`, `decision in {"no_trade","hold"}` for `rejected_decisions`) by adding them as additional `.filter(...)` terms.
- [ ] Step 4: Keep the `max(...)`/`latest_*` reductions, now applied to the already-windowed query results.
- [ ] Step 5: Confirm the returned dict keys + value shapes are byte-for-byte the same contract as before.

## Task 4: Update the reflection runtime to derive trade_date locally

**Files:** `src/trading/runtime/reflection.py`.

- [ ] Step 1: In `LiveReflectionRuntime.run` (`reflection.py:85`), compute `trade_date = trade_date_for(decision_time, SCHEDULER_TIMEZONE)` and `window = local_day_bounds_utc(trade_date, SCHEDULER_TIMEZONE)`. Pass both into `request_loader.load(...)`.
- [ ] Step 2: Update `LiveReflectionRequestLoader.load` (`reflection.py:26`) to accept and forward the window to `repository.load_reflection_inputs(...)`. `ReflectionPipelineRequest.trade_date` must be the local `trade_date` (not the UTC date).
- [ ] Step 3: Read `SCHEDULER_TIMEZONE` from `src/core/config.py` (the same source the scheduler uses — verify the exact symbol name; do not introduce a second config path).

## Task 5: Sweep the remaining `.all()` + Python `.date()` filter sites

**Files:** other `src/trading/repositories/mixins/*.py`.

- [ ] Step 1: Enumerate the candidates: `grep -rn "\.all()" src/trading/repositories/mixins/ | wc -l` and then `grep -rn "\.date() == \|\.date()==\|== trade_date\|\.date() ==" src/trading/repositories/mixins/`. Produce the list in the PR description.
- [ ] Step 2: For each site that filters a `DateTime`/`Date` column by a single day or window, push the predicate into SQL using the Task 1 helper. **Do not** blindly rewrite `.all()` calls that legitimately need the full table (e.g. `load_active_learning_factors` at `reflection.py:7-12` filters by `status`, not date — leave it, or convert to `.filter(LearningFactor.status.in_(("active","shadow")))` as an optional efficiency win, clearly separated).
- [ ] Step 3: Anything that is genuinely a whole-table scan with no date predicate is out of scope for THIS PR — note it in the tracker rather than expanding scope. Keep the PR focused on the date-filtered hot paths entangled with the timezone bug.

## Task 6: Tests

**Files:** `tests/trading/test_pr36_trade_day_window.py`, reflection repo/runtime tests.

- [ ] Step 1: Window helper unit tests (Task 1) including a DST day.
- [ ] Step 2: A **parity** test: build a fixture day fully inside one UTC date, assert the new windowed `load_reflection_inputs` returns the same row sets as a reference Python-filtered implementation (or a hand-asserted expected set).
- [ ] Step 3: A **boundary** regression test: write rows whose `snapshot_time` etc. fall late in the local day but on the next UTC calendar date; assert reflection no longer returns `status="skipped"` and that the rows are included. This is the exact bug being fixed — it must fail on the old code and pass on the new.
- [ ] Step 4: Run targeted reflection + repository tests, then the broader `tests/trading/` reflection/repository suites. Record results in the PR.

## Task 7: Tracker + backlog

- [ ] Step 1: Prepend a dated entry to the **Recent** section of `plan/progress_tracker.md` describing the tz-aware window helper and the SQL-side filtering, and list any remaining whole-table scans deliberately left for later.
- [ ] Step 2: In `plan/review_backlog.md`, mark #2 and #4 resolved.

## Done when

- `trade_date` is derived in `SCHEDULER_TIMEZONE`, not UTC; reflection includes the correct day's rows on a tz/UTC-boundary day (proven by the boundary test).
- `load_reflection_inputs` filters in SQL with tz-aware bounds; no naive-datetime comparisons remain; the return contract is unchanged (proven by the parity test).
- The date-filtered `.all()` + Python `.date()` sites in the reflection hot path are converted to `WHERE` filters; remaining whole-table scans are documented.
- Targeted + relevant broader tests pass; tracker + backlog updated.
