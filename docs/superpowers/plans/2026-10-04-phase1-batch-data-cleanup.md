# Phase 1 Batch Data Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Enforce Yahoo-only incremental daily-bar ingestion and batched pre-open market-data behavior across Phase 1 Tasks A–G.

**Architecture:** The post-close workflow will fetch recent daily bars from Yahoo, validate coverage against the existing XNYS calendar, and insert only new natural-key rows while preserving last-good data. Pre-open technical ingestion will read the database for historical bars and use only one batched Alpaca premarket overlay; split-safe values will be projected in memory for technical indicators while raw closes remain available for gap calculations.

**Tech Stack:** Python, pytest, SQLAlchemy, PostgreSQL models/repository, yfinance normalization, `exchange_calendars` through `RankingSessionCalendar`.

**Spec:** `docs/superpowers/specs/2026-10-04-phase1-batch-data-cleanup-design.md`

---

## File map

- Modify `src/providers/market_data/yfinance_prices.py` — remove failed-batch fan-out.
- Modify `src/trading/workflows/market_daily_bars.py` — Yahoo-only workflow, recent-window mode, latest-session coverage, and degraded metadata.
- Modify `src/scheduler/jobs/market_daily_bars_job.py` — remove Alpaca construction and obsolete logging.
- Modify `src/trading/repositories/source_sqlalchemy.py` — make existing natural-key bars immutable on routine re-ingestion.
- Modify `src/trading/signals/source_ingestion.py` — split-safe technical projection and explicit pre-open batch capability handling.
- Modify `tests/tools/test_yfinance_prices.py` — batch failure/no-fan-out coverage.
- Modify `tests/trading/test_market_daily_bars_batch.py` — Yahoo-only, recent-window, coverage, and failure behavior.
- Modify `tests/scheduler/test_market_daily_bars_job.py` — scheduler construction contract.
- Modify `tests/trading/test_market_daily_bar_repository.py` — PIT timestamp immutability and insert behavior.
- Modify `tests/trading/test_source_ingestion_daily_bars.py` — split-safe payload, missing batch capability, and last-good DB regression.
- Modify `tests/trading/test_pipeline.py` only if the changed source contract requires a fixture update.
- Modify `plan/progress_tracker.md` — record completion after verification.
- Modify `documents/repo_overview.md` only if the existing overview tracks this architecture area and the cleanup meets its major-refactor threshold.

## Task 1: Lock Yahoo provider and daily-batch behavior with tests

**Files:** `tests/tools/test_yfinance_prices.py`, `tests/trading/test_market_daily_bars_batch.py`, `tests/scheduler/test_market_daily_bars_job.py`

- [ ] Add a provider test whose batch downloader raises and assert exactly one call per failed chunk, with no single-symbol calls.
- [ ] Update batch fixtures to construct `MarketDailyBarsBatch` without Alpaca.
- [ ] Add assertions that a complete Yahoo result saves rows and records only Yahoo coverage metadata.
- [ ] Add assertions that an absent Yahoo symbol is missing/degraded and does not trigger any fallback call.
- [ ] Add assertions that a global Yahoo failure leaves an existing repository row untouched.
- [ ] Add a scheduler test that patches or inspects construction and proves no Alpaca market-data provider is created for the daily-bars job.
- [ ] Run focused tests and confirm they fail against the current implementation.

Run:

```bash
source ~/.venv/bin/activate
pytest tests/tools/test_yfinance_prices.py tests/trading/test_market_daily_bars_batch.py tests/scheduler/test_market_daily_bars_job.py -q
```

Expected before implementation: failures for the new no-fallback/no-fan-out contracts.

## Task 2: Implement Yahoo-only incremental daily-bar workflow

**Files:** `src/providers/market_data/yfinance_prices.py`, `src/trading/workflows/market_daily_bars.py`, `src/scheduler/jobs/market_daily_bars_job.py`

- [ ] Remove the per-symbol retry loop from `fetch_daily_bars_for_symbols`; return valid results from successful chunks and skip failed chunks.
- [ ] Remove `alpaca_provider`, fallback merging, fallback result fields, and Alpaca metadata from `MarketDailyBarsBatch`.
- [ ] Keep `provider="yahoo"` in the ingestion run and retain only requested/succeeded/missing coverage fields.
- [ ] Add a normal recent fetch window (10 calendar days by default) and an explicit optional backfill mode that can use the configured long lookback without changing the normal scheduler path.
- [ ] Reuse `RankingSessionCalendar` to resolve the latest completed XNYS session for `as_of`.
- [ ] Classify each ticker as covered only when its normalized Yahoo rows reach the expected session; mark stale/missing tickers as missing and keep all existing DB rows.
- [ ] Preserve degraded status for any missing/stale ticker or Yahoo exception, while saving valid returned rows.
- [ ] Remove the Alpaca provider import/construction from the scheduler and update completion logging.
- [ ] Run the focused provider/workflow/scheduler tests.

## Task 3: Make repository re-ingestion PIT-safe

**Files:** `src/trading/repositories/source_sqlalchemy.py`, `tests/trading/test_market_daily_bar_repository.py`

- [ ] Change `save_market_daily_bars` so an existing `(ticker, trade_date, provider)` row is skipped entirely.
- [ ] Keep insertion behavior unchanged for new rows, including all timestamps and quality metadata.
- [ ] Update the existing upsert test to assert the original close and availability timestamp remain unchanged.
- [ ] Add a regression that inserts an Oct 1 bar, re-ingests the same key on Oct 4, and confirms a decision-time Oct 2 read still sees the original row.
- [ ] Add a regression that a new Oct 2 bar is inserted with its new ingestion timestamp while the Oct 1 row remains original.
- [ ] Run the repository tests.

## Task 4: Enforce split-safe technical payloads and pre-open batch capability

**Files:** `src/trading/signals/source_ingestion.py`, `tests/trading/test_source_ingestion_daily_bars.py`, `tests/trading/test_pipeline.py` if needed

- [ ] Add a small pure helper that projects persisted bars into split-adjusted technical OHLC/volume values using future split factors, without mutating stored records.
- [ ] Make `_market_daily_bar_payload` use the projection while retaining the legacy payload keys.
- [ ] Keep `stored_bars[-1].close_raw` as the previous raw close passed to premarket-gap computation.
- [ ] Add a 2:1 split regression proving technical return does not show an approximately -50% move and the raw premarket baseline remains the post-split raw close.
- [ ] In `run_type="pre_open"`, record a degradation error when the batched premarket method is unavailable and prevent `_premarket_gap_pct` from invoking the single-symbol method.
- [ ] Preserve single-symbol premarket behavior for non-pre-open targeted workflows.
- [ ] Add a provider-without-batch test asserting zero single-symbol calls and degraded status.
- [ ] Run source-ingestion and pipeline tests.

## Task 5: Add the Phase 1 178-ticker regression

**Files:** `tests/trading/test_source_ingestion_daily_bars.py`, `tests/trading/test_market_daily_bars_batch.py`

- [ ] Keep a fake live provider exposing only batched premarket prices and no historical Alpaca method.
- [ ] Assert 178 technical records, zero historical daily calls, zero intraday calls, zero whole-universe option-chain calls, zero single-symbol premarket calls, and one logical batched premarket request.
- [ ] Simulate a failed nightly Yahoo batch with existing DB bars and verify no existing rows are removed.
- [ ] Run the next pre-open against those last-good DB bars and assert technical records are still produced with the live premarket overlay available.
- [ ] Assert degraded/stale telemetry is visible where the batch failure is recorded.

## Task 6: Documentation and full verification

**Files:** `plan/progress_tracker.md`; `documents/repo_overview.md` if applicable

- [ ] Record the completed Phase 1 cleanup and deferred Task 8 boundary in the project tracker.
- [ ] Update the repository overview only with the consolidated architecture change, not a file-by-file changelog.
- [ ] Run the complete required test set.
- [ ] Run `python -m compileall -q src` after activating the project virtual environment.
- [ ] Run `git diff --check`.
- [ ] Review the final diff for any Alpaca historical call or single-symbol retry that remains inside the scoped workflow.

Required final command:

```bash
source ~/.venv/bin/activate
pytest tests/tools/test_yfinance_prices.py \
       tests/trading/test_market_daily_bars_batch.py \
       tests/trading/test_market_daily_bar_repository.py \
       tests/trading/test_source_ingestion_daily_bars.py \
       tests/scheduler/test_market_daily_bars_job.py \
       tests/trading/test_pipeline.py -q
python -m compileall -q src
git diff --check
```

