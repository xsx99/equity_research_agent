# Phase 1 Batch Data Cleanup Design

**Date:** 2026-10-04  
**Status:** Approved for implementation  
**Scope:** Attached Phase 1 Tasks A–G only

## Goal

Make scheduled Yahoo daily-bar ingestion and pre-open technical ingestion obey the
batch-first architecture:

```text
Yahoo daily bars -> scheduled batch -> PostgreSQL -> pre-open technical baseline
Alpaca live data -> batched premarket overlay
```

Yahoo failures must preserve last-good database data. Neither daily-bar ingestion
nor pre-open technical ingestion may use Alpaca historical daily bars as a fallback.

Task 8 and the later fundamentals, earnings, news, global-context, and option-chain
architecture changes are explicitly out of scope.

## Design

### 1. Yahoo-only daily-bar batch

`MarketDailyBarsBatch` will depend on the Yahoo fetcher, repository, and ticker
loader only. The scheduler will no longer construct an Alpaca market-data provider
for this job. A missing or failed Yahoo result leaves existing rows untouched and
records degraded coverage using only:

```json
{
  "tickers_requested": 181,
  "tickers_succeeded": 175,
  "tickers_missing": ["ABC", "XYZ"]
}
```

Historical Alpaca APIs remain available to explicit offline consumers elsewhere in
the repository.

### 2. Bounded Yahoo requests

`fetch_daily_bars_for_symbols` will issue one request per configured symbol chunk.
If a chunk raises, it returns no bars for that chunk and does not fan out into
single-symbol retries. A successful multi-symbol DataFrame is normalized per symbol;
absent symbols remain missing without additional downloads.

### 3. Incremental, point-in-time-safe persistence

Normal post-close runs fetch the ten calendar days ending at the run date, which is
enough to cover the latest completed session and a small overlap. The explicit
`run(backfill=True)` path may use the configured 400-day lookback for a new ticker or
an intentional repair; the scheduler always calls the default incremental mode.
For every newly inserted row, both `ingested_at` and
`available_for_decision_at` are set to the batch decision time (`as_of`, or the
workflow clock when omitted). The normal scheduled path will not repeatedly rewrite
a rolling 400-day history.

Repository writes use `(ticker, trade_date, provider)` as an immutable natural key:

- new bars are inserted with their original ingestion and availability timestamps;
- existing bars are left unchanged, including provider values and PIT timestamps.

No delete or destructive replacement is introduced.

### 4. Latest-session coverage

The batch will reuse `RankingSessionCalendar` to resolve the latest completed XNYS
session for the run's decision time. A ticker is successful only when its Yahoo
result reaches that session. Older returned rows may still be inserted, but a stale
latest bar marks the ticker missing and degrades the run. Weekend and holiday runs
therefore use the prior completed session automatically.

### 5. Split-safe technical projection

Persisted raw OHLC values remain unchanged. The technical source payload will use a
small in-memory split-adjustment projection derived from raw OHLC, stock-split
events, and volume. For bars sorted chronologically, a bar's adjustment factor is
the product of all later non-zero `stock_split` values; adjusted OHLC values are
raw values divided by that factor, and adjusted volume is raw volume multiplied by
that factor. This applies multiple and reverse splits consistently while leaving
the split-event bar on its post-split basis. This keeps long-horizon returns, moving
averages, RSI, and ATR from interpreting a split as a market loss. Premarket gap
calculations continue to use the latest persisted `close_raw`, preserving real-price
semantics. Yahoo `Adj Close` is not substituted as a total-return series because it
may include dividends.

### 6. Batched premarket contract

For `run_type="pre_open"`, source ingestion requires
`fetch_premarket_prices_for_symbols`. If the provider lacks that capability or the
batch call fails, the run is degraded and technical records remain based on DB bars
with no premarket gap where unavailable. If the batch returns only a subset, valid
prices are used for those tickers, missing tickers get no gap, and the run is
degraded. Coverage metadata records requested, succeeded, and missing premarket
tickers. No per-ticker premarket fallback is used in pre-open. Non-pre-open targeted
workflows may retain their existing single-symbol behavior where still required.

## Verification

The daily-bar example of 181 requested symbols includes the 178 research tickers
plus `SPY`, `QQQ`, and `GLD` support symbols. The Phase 1 pre-open regression counts
technical records for the 178 research tickers and sends those 178 tickers through
the batched premarket overlay; benchmark bars are loaded from the database but do
not create additional technical records or premarket requests.

Tests will cover:

- Yahoo-only daily-bar ingestion and scheduler wiring;
- no per-symbol Yahoo retries after a batch exception;
- partial Yahoo results and missing-symbol coverage;
- immutable repository PIT timestamps on re-ingestion;
- latest-session coverage across normal days, weekends, and holidays;
- split-safe technical values with raw premarket close behavior;
- missing batched-premarket capability without single-symbol calls;
- the 178-ticker Phase 1 pre-open regression and last-good DB behavior after a
  nightly Yahoo failure.

Required checks:

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
