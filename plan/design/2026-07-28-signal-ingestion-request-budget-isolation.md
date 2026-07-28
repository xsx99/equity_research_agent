# Signal Ingestion Request-Budget Isolation

Date: 2026-07-28
Status: Approved in conversation and independent spec review

## Summary

Prevent large pre-open and intraday ticker scopes from losing complete technical
signal families when the shared market-data request budget is exhausted.

The fix will batch required daily-bar loading, isolate budgets by market-data
operation, make optional enrichment phase-aware, and preserve a daily-bar
technical source record when premarket or intraday enrichment fails.

## Confirmed Production Failure

On 2026-07-24 the pre-open run requested 178 tickers. `SourceIngestionService`
created one `ProviderResiliencePolicy` named `market_bars` with
`max_requests=100` and reused it for:

- one daily-bar request per ticker;
- two benchmark daily-bar requests for SPY and QQQ;
- one premarket request per ticker;
- one intraday-bar request per ticker, even though pre-open occurs before the
  regular session.

LITE was the 36th ticker. Its provider telemetry recorded
`status=budget_exceeded`, `budget_remaining=0`, and `request_count=0`, so no LITE
daily-bar request reached Alpaca. The snapshot consequently stored:

```text
signal_json.technical = {}
source_freshness_json.technical = "missing"
missing_signals_json includes "technical.market_bars"
```

The trading decision agent accurately summarized that snapshot as missing
technical signals. This was not a UI cache problem or missing Alpaca coverage.

Historical snapshots show the transition clearly: LITE technical freshness was
`fresh` through 2026-06-30 and was `missing` on every recorded pre-open snapshot
from 2026-07-15 through 2026-07-24.

## Goals

- Every requested ticker gets a required daily-bar loading opportunity,
  independent of its position in the input sequence.
- Use Alpaca's existing multi-symbol daily-bars capability instead of one daily
  request per ticker when the provider supports it.
- Treat daily bars as the required technical input.
- Treat premarket and intraday bars as optional, phase-specific enrichments.
- A failure or exhausted budget in an optional enrichment must not discard
  successfully loaded daily bars.
- Provider telemetry must retain distinct endpoint names and failure states for
  daily bars, premarket prices, and intraday bars.
- Preserve the point-in-time fields and existing `SourceRecord` payload contract.
- Keep fake and non-Alpaca providers working when they only implement the
  single-symbol daily-bar method.

## Non-Goals

- Implementing the cross-sectional relative-strength ranker.
- Reducing the full research universe to Top-N in this change.
- Batching fundamentals, news, or option chains.
- Changing trading, strategy, risk, or UI decision semantics.
- Backfilling historical signal snapshots or rewriting prior decisions.
- Treating a genuinely unavailable daily-bar history as fresh data.

## Considered Approaches

### A. Raise the shared limit

Increasing `max_requests_per_endpoint` would be the smallest patch, but the
failure would return as the universe or per-ticker enrichment count grows. It
would also preserve coupling between required daily bars and optional intraday
data.

### B. Batch daily bars and isolate operation budgets

This is the selected approach. It reduces required daily-bar calls from O(N) to
bounded provider batches, prevents optional calls from consuming the required
daily budget, and keeps the current source/snapshot contract.

### C. Prioritize positions and forced tickers only

Reordering could protect LITE while leaving later tickers deterministically
starved. It is useful as defense in depth but is not sufficient as the primary
fix.

## Design

### 1. Operation-specific resilience policies

`SourceIngestionService.refresh_tickers()` will create separate policies for:

- `market_daily_bars_batch`;
- `market_daily_bars_fallback`;
- `market_premarket_price`;
- `market_intraday_bars`;
- the existing fundamental, news, social-macro, and option-chain operations.

The batch and fallback daily policies are separate, so retries consumed by a
failed batch attempt cannot reduce fallback capacity. The fallback policy is
sized for the exact fallback symbol count, including SPY and QQQ when needed,
times the policy's maximum attempts per scope (`max_retries + 1`). Its
circuit-failure threshold is set above the number of fallback symbol scopes for
that run. Consequently, one symbol's exhausted retries cannot open a shared
circuit that prevents a later required symbol's first attempt. The finite
attempt budget remains the hard upper bound.

The existing default limit remains the floor for each policy. Per-ticker optional
policies use the same scope-based budget formula:

```text
max(default_limit, ticker_count * (max_retries + 1))
```

This prevents budget exhaustion caused merely by scope size. Optional policies
retain the normal circuit breaker: repeated provider failures may intentionally
skip later optional enrichment, but those skips cannot remove successfully
loaded daily bars. The cap remains finite and telemetry remains per operation.

Daily, premarket, and intraday failures will no longer share request counters or
circuit state.

### 2. Batch required daily bars

Before the per-ticker loop, technical ingestion will call an optional provider
capability:

```python
fetch_daily_bars_for_symbols(symbols, lookback_days)
```

The symbols include the requested ticker scope plus SPY and QQQ. The existing
Alpaca implementation performs bounded multi-symbol requests and returns
normalized ascending daily bars by symbol.

The current Alpaca batch method must be completed as part of this change: it
shall follow `next_page_token` until the token is absent for every symbol chunk.
Alpaca's total-bar page limit can otherwise truncate a 178-symbol by 252-session
request and omit later symbols. Each request reuses the original parameters and
adds the returned `page_token`; results from all pages are accumulated before
normalization. A repeated page token is treated as a provider error rather than
looping indefinitely.

The daily loader returns an internal result containing `bars_by_symbol` and all
caught batch or fallback errors. The batch result is held only for the current
ingestion run. It is not a new database cache and does not alter point-in-time
persistence.

If the provider lacks the batch capability, the service falls back to its
existing single-symbol `fetch_daily_bars()` interface through the isolated
fallback policy.

If the batch operation itself fails, the service falls back to single-symbol
loading rather than marking the entire universe missing from one batch error.
The caught batch exception remains in the daily-load result even when every
single-symbol fallback succeeds. `refresh_tickers()` merges it into the
run-level error list, so recovery preserves usable data but the ingestion run is
still `degraded`.
After a successful batch response, any requested symbol omitted from the result
or returned with malformed or empty bars also receives a single-symbol fallback
attempt. This distinguishes pagination or provider omissions from a genuine
symbol-level no-bars result. Missing or malformed bars for one symbol do not
invalidate bars returned for other symbols.

### 3. Benchmark returns from the same daily-bar run

SPY and QQQ one-day returns will be computed from the daily bars loaded for the
current run. They will retain the current fractional-return formula:

```text
(latest_close - previous_close) / previous_close
```

This removes the two extra benchmark requests from `_refresh_technical()` and
ensures ticker and benchmark inputs share the same ingestion run and decision
time. The existing date-keyed benchmark cache may remain as a compatibility
fallback, but the run-local batch result is authoritative when present.

### 4. Phase-aware optional enrichment

Operation selection will follow the run type:

| Run type | Daily bars | Premarket price | Intraday bars |
| --- | --- | --- | --- |
| `pre_open` | required | optional | skipped |
| `intraday_refresh` | required | skipped | optional |
| `targeted` / `fixture` | required | optional when supported | optional when supported |

This prevents pre-open runs from spending a logical request on regular-session
intraday data that cannot yet exist. It also avoids re-querying a premarket price
during hourly intraday runs.

### 5. Required versus optional failure boundary

`_refresh_technical()` will receive already loaded daily bars plus the
operation-specific optional policies. It will return a small internal result
containing the optional technical `SourceRecord` and any caught enrichment
errors. `refresh_tickers()` will append the record when present and merge the
returned errors into its existing run-level `errors` list.

- No valid daily bars: return no technical `SourceRecord`; the snapshot correctly
  records `technical.market_bars` as missing.
- Premarket failure: record provider failure telemetry, set
  `premarket_gap_pct=None`, and keep the daily-bar `SourceRecord`.
- Intraday failure: record provider failure telemetry, omit `intraday_bars`, and
  keep the daily-bar `SourceRecord`.

Optional failures must be caught only at their boundary. They must not hide
programming errors in daily-bar normalization or snapshot construction.
Because caught enrichment exceptions are returned to `refresh_tickers()`, the
existing `_ingestion_status(errors=..., source_records=...)` calculation still
marks the ingestion run `degraded` and persists the first error code and message,
even though the usable daily technical record is retained.

### 6. Compatibility and contracts

No schema or migration is required. The technical source payload remains:

```python
{
    "bars": [...],
    "benchmark_returns": {"SPY": ..., "QQQ": ...},
    "premarket_gap_pct": ...,
    "intraday_bars": [...],  # only when available
}
```

`event_time`, `published_at`, `ingested_at`, and
`available_for_decision_at` retain their current semantics. Snapshot builders,
strategy matching, trading decisions, replay, and UI consumers remain unchanged.

## Error Handling and Observability

- Distinct telemetry endpoint names identify which operation degraded.
- Ingestion-run `status` remains `degraded` when any provider operation fails.
- Coverage continues to report requested tickers and stored source records.
- A batch error followed by successful single-symbol fallback is observable in
  provider telemetry, marks the ingestion run `degraded`, and does not make
  successfully recovered symbols missing.
- A real symbol-level no-bars result remains an explicit technical-family miss.

## Testing

Implementation will follow TDD.

Unit tests will cover:

1. A scope larger than 100 tickers uses batch daily loading and produces a
   technical source record for a late ticker such as LITE.
2. A multi-symbol provider follows `next_page_token`, accumulates all pages, and
   detects a repeated page token.
3. SPY/QQQ benchmark returns come from the same batch result.
4. A provider without the batch method falls back to single-symbol loading
   without starving late tickers.
5. Batch retry consumption cannot reduce the independent fallback capacity.
6. Three early fallback-symbol failures cannot open a circuit that skips a valid
   late required symbol.
7. Pre-open skips intraday fetching.
8. Intraday refresh skips premarket fetching.
9. Premarket budget or provider failure leaves the daily technical record intact
   while the ingestion run is `degraded`.
10. Intraday budget or provider failure leaves the daily technical record intact
   while the ingestion run is `degraded`.
11. A batch failure falls back to single-symbol loading and leaves the recovered
    ingestion run `degraded`.
12. A symbol omitted from a successful batch receives a single-symbol fallback.
13. A symbol genuinely missing daily bars remains missing without affecting
   neighboring symbols.
14. Existing targeted-run behavior and payload fields remain compatible.

Verification will include:

- focused source-ingestion and technical-signal unit tests;
- provider market-data tests;
- pre-open and intraday runtime tests;
- the broader trading test suite;
- Python compilation and `git diff --check`;
- one standalone, rate-conscious live smoke for LITE that confirms a non-empty
  technical payload without refreshing the whole universe.

## Success Criteria

- A 178-ticker pre-open fixture cannot exhaust the required daily-bar budget
  before reaching LITE.
- LITE receives a non-empty technical payload when the provider returns valid
  LITE daily bars.
- No optional enrichment failure can convert valid daily bars into
  `technical.market_bars` missing.
- Telemetry distinguishes daily, premarket, and intraday operations.
- Existing point-in-time and downstream signal contracts remain intact.
