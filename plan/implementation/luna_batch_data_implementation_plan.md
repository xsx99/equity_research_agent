# Batch-First Trading Data Layer — Luna Implementation Plan

## How to use this file

Implement **one task at a time**.

Rules for every task:

1. Implement only the requested task.
2. Do not implement later tasks.
3. Inspect existing repo conventions before adding new abstractions.
4. Write focused tests.
5. Preserve existing public interfaces unless the task explicitly changes one.
6. Do not refactor unrelated code.
7. Run focused tests, `python -m compileall -q src`, and `git diff --check`.
8. Report:
   - files changed
   - behavior changed
   - tests run
   - anything deferred

If the repo differs from this plan, preserve the architecture goal and adapt to the current structure.

---

# Master goal

Move non-live data out of the pre-open/intraday critical path.

Target:

```text
scheduled external APIs
        ↓
batch jobs
        ↓
PostgreSQL
        ↓
pre-open / intraday read DB

Alpaca live
        ↓
premarket / intraday / broker / shortlisted options
```

Final rule:

```text
If data does not need minute-level freshness, read it from PostgreSQL.
```

Implementation order:

```text
1. daily bars -> DB
2. technical signals read DB
3. batch Alpaca premarket
4. fundamentals -> DB
5. earnings/economic calendar -> DB
6. universe/liquidity -> DB
7. news/global context -> DB
8. option chain only after shortlist
```

---

# Task 1 — Add daily-bar storage

## Goal

Persist daily OHLCV in PostgreSQL.

## Add

Table:

```text
market_daily_bars
```

Fields:

```text
ticker
trade_date
open_raw
high_raw
low_raw
close_raw
adj_close
volume_raw
dividend
stock_split
provider
ingested_at
available_for_decision_at
quality_flags_json
created_at
```

Constraint:

```text
UNIQUE(ticker, trade_date, provider)
```

Indexes:

```text
(ticker, trade_date)
available_for_decision_at
```

Add repository methods:

```python
save_market_daily_bars(...)
load_market_daily_bars(ticker, decision_time, limit)
load_market_daily_bars_for_symbols(tickers, decision_time, limit_per_ticker)
```

All reads must enforce:

```text
available_for_decision_at <= decision_time
```

## Do not

Do not add Yahoo fetching yet.

## Acceptance

Model, migration, repository tests, compileall, diff check pass.

---

# Task 2 — Add Yahoo daily-bar provider

## Goal

Fetch daily OHLCV for many symbols.

Create:

```text
src/providers/market_data/yfinance_prices.py
```

Implement:

```python
fetch_daily_bars_for_symbols(
    symbols,
    start,
    end,
    batch_size=40,
)
```

Use:

```python
yf.download(
    tickers=list(chunk),
    start=start,
    end=end,
    interval="1d",
    group_by="ticker",
    auto_adjust=False,
    actions=True,
    threads=False,
    progress=False,
)
```

Map:

```text
Open -> open_raw
High -> high_raw
Low -> low_raw
Close -> close_raw
Adj Close -> adj_close
Volume -> volume_raw
Dividends -> dividend
Stock Splits -> stock_split
```

Support both single-symbol and MultiIndex DataFrames.

One missing ticker must not fail other tickers.

## Tests

No network.

Inject `download_fn`.

Test:

```text
single symbol
multiple symbols
raw close vs adjusted close
dividends/splits
NaN rows
missing symbol
81 symbols with batch_size=40 -> 3 calls
```

---

# Task 3 — Add daily-bars batch workflow + scheduler

## Goal

Fetch Yahoo daily bars outside the trading runtime.

Create a workflow such as:

```text
MarketDailyBarsBatch
```

Flow:

```text
active tickers + SPY + QQQ + GLD
        ↓
Yahoo batch
        ↓
market_daily_bars
```

If Yahoo misses symbols:

```text
Alpaca fetch_daily_bars_for_symbols(missing_symbols)
```

Fallback only missing symbols.

Never delete previous DB rows when providers fail.

Record `source_ingestion_runs` coverage.

Example:

```json
{
  "tickers_requested": 181,
  "tickers_succeeded": 180,
  "tickers_missing": ["XYZ"],
  "fallback_used": true
}
```

Add scheduled job using the existing `BaseJob` / `JobConfig` pattern.

Run once after market close.

## Acceptance

- complete Yahoo result -> zero Alpaca calls
- one Yahoo miss -> Alpaca receives only that ticker
- provider failure does not erase old DB data
- scheduler test passes

---

# Task 4 — Make technical signals read daily bars from DB

## Goal

Remove historical daily market API calls from pre-open.

Change `SourceIngestionService` so technical history comes from:

```text
market_daily_bars
```

not:

```python
market_provider.fetch_daily_bars(...)
```

Before the ticker loop, bulk load:

```text
all universe tickers
SPY
QQQ
```

Compute SPY/QQQ benchmark returns from those DB bars.

Preserve the existing downstream technical payload shape.

## Acceptance

For 178 fake tickers:

```text
178 technical records
0 Alpaca historical daily calls
```

The last ticker must still have valid technical bars.

---

# Task 5 — Batch Alpaca premarket prices

## Goal

Keep live premarket data in Alpaca, but fetch symbols in batch.

Add:

```python
AlpacaMarketDataProvider.fetch_premarket_prices_for_symbols(
    symbols,
    as_of,
)
```

Use Alpaca multi-symbol bars:

```text
GET /v2/stocks/bars
timeframe=1Min
start=04:00 ET
end=decision_time
```

Before ticker loop:

```python
premarket_prices = fetch_premarket_prices_for_symbols(tickers, as_of)
```

Calculate:

```text
premarket_gap_pct =
    (premarket_price - previous_close_raw)
    / previous_close_raw
```

`previous_close_raw` comes from DB.

If live premarket fails:

```text
technical daily data remains valid
premarket_gap_pct = None
run becomes degraded
```

Do not discard the technical record.

---

# Task 6 — Remove unnecessary pre-open live calls

For:

```text
run_type = pre_open
```

remove:

```text
regular-session intraday fetches
whole-universe option-chain fetches
```

Remove `option_chain` from broad pre-open source families.

## Phase 1 acceptance

For 178 tickers:

```text
178 covered technical records
0 Alpaca historical daily calls
0 regular-session intraday calls
0 whole-universe option-chain calls
premarket uses batch path
```

**Stop after Task 6 and verify Phase 1 before continuing.**

---

# Task 7 — Add Yahoo fundamentals batch

## Goal

Move Yahoo fundamentals out of pre-open.

Reuse existing:

```text
YFinanceFundamentalsProvider
fundamental_snapshots
```

Flow:

```text
Yahoo Ticker.info
    ↓
existing normalization
    ↓
FundamentalSnapshotRecord
    ↓
fundamental_snapshots
```

Do not create a new fundamentals table.

Use actual ingestion time for:

```text
ingested_at
available_for_decision_at
```

Do not backdate current Yahoo aggregate values to fiscal-quarter dates.

Add a nightly/post-close scheduled job.

On provider failure:

```text
keep last good snapshot
record degraded/failed ingestion
```

---

# Task 8 — Make pre-open fundamentals DB-only

Remove synchronous broad-universe:

```python
fetch_context(...)
```

from pre-open.

Use latest decision-visible `fundamental_snapshots`.

Initial freshness:

```text
<= 48h -> fresh
48h to ~4 trading days -> stale but usable
older -> unavailable
```

Do not call Yahoo as emergency fallback.

Test fresh, stale, hard-stale, and future snapshots.

---

# Task 9 — Add Nasdaq earnings batch

## Goal

Persist future earnings into `calendar_events`.

Use existing Nasdaq source:

```text
api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
```

Fetch a 45-60 day horizon once per day.

Persist:

```text
event_key = earnings:{ticker}:{date}
event_type = own_earnings
ticker
event_time
source = nasdaq_earnings
available_for_decision_at = ingestion time
```

Handle reschedules.

If an earnings date moves, the old future date must no longer be active.

Successful coverage with no event in horizon means:

```text
covered + no known earnings event
```

not provider failure.

---

# Task 10 — Make pre-open earnings DB-only

Remove live `NasdaqEarningsCalendar` lookup from pre-open/intraday signal ingestion.

Derive:

```text
earnings_in_days
known_event_date
own_earnings_event_type
```

from decision-visible `calendar_events`.

No Nasdaq API call should be required during pre-open.

---

# Task 11 — Add FRED/FMP economic-calendar batch

## Goal

Persist macro calendar into `calendar_events`.

Primary:

```text
FRED /fred/releases/dates
```

Fallback/enrichment:

```text
FMP economic calendar
```

FRED owns the release date where available.

FMP may enrich:

```text
exact time
impact
estimate
previous
actual
```

Do not create duplicate FRED and FMP events for the same macro release.

Run daily.

---

# Task 12 — Make pre-open macro calendar DB-only

Replace runtime:

```text
EconomicCalendarFallback(
    FREDEconomicCalendar(),
    FMPEconomicCalendar(),
)
```

with repository-backed calendar reads.

If FRED/FMP are unavailable during pre-open, stored valid calendar data must still work.

---

# Task 13 — Persist asset master

Add:

```text
market_assets
```

Use Alpaca:

```text
GET /v2/assets
```

Persist:

```text
symbol
name
exchange
asset_class
status
tradable
shortable
easy_to_borrow
provider
ingested_at
```

Add daily or weekly batch job.

Do not fetch price/liquidity here.

---

# Task 14 — Persist universe daily metrics and cut over scanner

Add:

```text
universe_daily_metrics
```

Fields:

```text
ticker
trade_date
close_raw
avg_volume_20d
avg_dollar_volume_20d
realized_volatility_20d
eligible_by_liquidity
computed_at
input_max_available_at
```

Compute locally from `market_daily_bars`.

No external API calls.

Then make pre-open universe filtering read:

```text
market_assets
+
universe_daily_metrics
```

Preserve existing:

```text
manual watchlist
manual include
manual exclude
forced ticker
```

behavior.

---

# Task 15 — Add scheduled company-news ingestion

Primary:

```text
Finnhub /api/v1/company-news
```

Fallback:

```text
Alpaca /v1beta1/news
```

Persist to existing:

```text
event_news_items
```

Run every 30 minutes.

Scope:

```text
active universe
held positions
manual/watchlist tickers
```

Use stable article ID or canonical URL for dedupe.

---

# Task 16 — Make trading paths news DB-only

Remove synchronous company-news fetch from pre-open/intraday.

Signal generation reads decision-visible:

```text
event_news_items
```

Freshness:

```text
<= 30m -> fresh
30-90m -> stale but usable
> 90m -> unavailable during active monitoring
```

Important:

```text
successful collector + no relevant news
```

must mean:

```text
covered + no event
```

not missing provider data.

---

# Task 17 — Normalize global context

## Goal

Stop copying the same policy/geopolitical item into every ticker.

Add:

```text
global_context_items
```

Fields:

```text
category
source_type
source_key
provider
title
summary
sentiment_direction
importance_score
importance_label
theme_tags_json
source_refs_json
dedupe_key
event_time
published_at
ingested_at
available_for_decision_at
metadata_json
```

Optional:

```text
global_context_ticker_links
```

Sources:

```text
WhiteHouseUpdatesProvider
APWorldNewsProvider
```

Run every 30 minutes.

Do not delete `social_macro_items` yet.

---

# Task 18 — Make trading paths global-context DB-only

Signal generation should read:

```text
global_context_items
+
ticker/theme links
```

and derive the existing social/macro signal.

Remove synchronous:

```python
get_global_context(...)
```

from pre-open/intraday decision paths.

---

# Task 19 — Move option chain after shortlist

## Goal

Never fetch option chains for the whole universe.

Create a post-shortlist enrichment service.

Flow:

```text
SignalSnapshot
    ↓
StrategyPipeline
    ↓
shortlist / selected candidates
    ↓
OptionEnrichmentService
    ↓
Alpaca option chain
```

Use:

```text
/v1beta1/options/snapshots/{underlying_symbol}
```

Only fetch for option-relevant shortlisted candidates.

Do not put option-chain fetch back into initial `SignalPipeline`.

---

# Final regression

Create one end-to-end test for ~178 stocks.

Seed DB-backed:

```text
daily bars
fundamentals
calendar
news
global context
insider data
universe metrics
```

Allow fake Alpaca to provide only live premarket data.

Assert:

```text
historical daily Alpaca calls = 0
fundamental external calls = 0
Nasdaq calls = 0
FRED/FMP calendar calls = 0
company-news calls = 0
global-context calls = 0
regular intraday calls = 0
whole-universe option-chain calls = 0

premarket batch calls > 0
```

Also simulate nightly Yahoo failure while old DB bars exist.

Next pre-open must still run using stale/degraded DB data rather than losing technical signals.

---

# Prompt to give Luna for each task

Use this wrapper and append only the current task section:

```text
Implement ONLY the task below.

Rules:
- Do not implement later tasks.
- Inspect existing repo conventions first.
- Write focused tests.
- Preserve existing public behavior unless explicitly changed.
- Do not refactor unrelated code.
- Run focused tests.
- Run `python -m compileall -q src`.
- Run `git diff --check`.
- Report files changed, behavior changed, tests run, and deferred work.
```
