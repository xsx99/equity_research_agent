# Trading Agent Data Layer Redesign
## Batch-First Ingestion Architecture

**Status:** Proposed Design  
**Repository:** `xsx99/equity_research_agent`  
**Date:** 2026-09-27

---

## 1. Executive decision

### 1.1 Most important change: the database becomes the source of truth for all non-live data

The current system still performs too much data collection inside the pre-open and intraday decision path. That makes a trading run depend on Yahoo, Nasdaq, Finnhub, Alpaca, FRED, news websites, and provider rate limits all being healthy at the same moment.

The target architecture changes the responsibility boundary:

```text
slow / scheduled external data
        -> scheduled ingestion jobs
        -> PostgreSQL
        -> SignalPipeline reads DB

live market state
        -> Alpaca live/batched API
        -> live overlay

DB baseline + live overlay
        -> signals
        -> candidate scoring
        -> decision
```

**Conclusion:** pre-open should no longer be an ingestion workflow. It should be a **read + compute workflow**, with only a small live-market overlay.

### 1.2 Split data into three freshness tiers

| Tier | Data | Fetch pattern | Decision-time dependency |
|---|---|---|---|
| **Daily batch** | Daily OHLCV, fundamentals, earnings calendar, economic calendar, asset metadata, liquidity metrics | Nightly / post-close | Read DB only |
| **Frequent batch** | Company news, policy/geopolitical context | Every 15-30 min | Read DB only |
| **Live** | Premarket price, intraday bars/quotes, account/positions, candidate option chain | Batched / on demand | External API allowed |

The important distinction is not which vendor provides the data. The important distinction is **how quickly the information changes**.

### 1.3 Reuse existing point-in-time tables whenever possible

The repository already has useful persistence primitives:

- `fundamental_snapshots`
- `event_news_items`
- `calendar_events`
- `insider_trades`
- `source_ingestion_runs`
- `provider_request_runs`
- `signal_snapshots`

The redesign should reuse these instead of creating a second persistence model for the same facts.

The main new storage needed is:

1. `market_daily_bars`
2. `market_assets`
3. `universe_daily_metrics`
4. `macro_indicator_observations`
5. `global_context_items` and optionally `global_context_ticker_links`

---

## 2. Target architecture

### 2.1 Offline ingestion plane

```text
Yahoo/yfinance ---------> Daily Price Batch ----------> market_daily_bars
         |--------------> Fundamentals Batch ---------> fundamental_snapshots

Nasdaq -----------------> Earnings Calendar Batch ----> calendar_events
FRED/FMP ----------------> Economic Calendar Batch ----> calendar_events
FRED --------------------> Macro Indicators Batch ----> macro_indicator_observations

Finnhub / Alpaca News ---> News Batch -----------------> event_news_items
White House / AP --------> Global Context Batch ------> global_context_items
SEC EDGAR ---------------> Form 4 Batch --------------> insider_trades

Alpaca Assets -----------> Asset Master Batch --------> market_assets
market_daily_bars --------> Liquidity Compute Job -----> universe_daily_metrics
```

### 2.2 Decision plane

```text
PostgreSQL
   |-- 252d daily bars
   |-- latest fundamental snapshot
   |-- upcoming earnings / macro events
   |-- recent company news
   |-- recent global context
   |-- insider activity
   |-- universe / liquidity metrics
   |
   +------------------------------+
                                  |
Alpaca live batched data          |
   |-- premarket prices           |
   |-- intraday bars              |
   +------------------------------+
                                  v
                           SignalSnapshot
                                  |
                           candidate scoring
                                  |
                       shortlist / selected trade
                                  |
                   candidate-only option-chain fetch
```

### 2.3 Hard rule

A normal pre-open universe run must **not** synchronously fetch daily bars, fundamentals, earnings calendars, news, macro calendar, global context, or option chains for the entire universe.

The only normal external market-data call in the initial pre-open signal phase should be a **batched live-price/premarket request**.

---

## 3. Provider and API routing matrix

This table is the canonical routing contract. Implementation should not choose a different provider at call sites.

| Data | Primary source / API | What to fetch | Cadence | Persist to | Fallback / note |
|---|---|---|---|---|---|
| Daily OHLCV | **Yahoo via `yfinance.download()`** | Multi-ticker daily Open/High/Low/Close/Adj Close/Volume/actions | Every trading day after close | `market_daily_bars` | Alpaca `/v2/stocks/bars` only in batch-job recovery, never pre-open |
| Fundamentals | **Yahoo via `yfinance.Ticker.info`** | market cap, P/E, P/S, EV/Sales, FCF, revenue, short float, growth, margins, ROE/ROA, sector/name | Daily | existing `fundamental_snapshots` | Last good DB snapshot; no synchronous pre-open retry |
| Asset master | **Alpaca Trading API `/v2/assets`** | active status, symbol, exchange, asset class, tradable flags/name | Daily or weekly | `market_assets` | Existing Alpaca provider already exposes `fetch_universe_assets()` |
| Liquidity / universe metrics | **Local computation** | prior close, avg volume 20d, avg dollar volume 20d, realized volatility | After daily bars | `universe_daily_metrics` | No provider call |
| Earnings calendar | **Nasdaq public calendar endpoint** `api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD` | upcoming company earnings dates | Daily, 45-60d horizon | existing `calendar_events` | Yahoo `Ticker.calendar` only as targeted fallback; Nasdaq endpoint is best-effort, not a formal SLA API |
| Economic release calendar | **FRED `/fred/releases/dates`** | scheduled US macro release dates | Daily | existing `calendar_events` | FMP `stable/economic-calendar` enriches exact time/impact/estimate when available |
| Macro observations | **FRED `/fred/series/observations`** | WTI, Treasury yields, HY OAS, VIX and configured series | Daily / before pre-open | `macro_indicator_observations` | Use last published observation; do not pretend FRED is an intraday feed |
| Company news | **Finnhub `/api/v1/company-news`** | headline, summary, timestamp, source, URL | Every 15-30 min | existing `event_news_items` | Alpaca `/v1beta1/news?symbols=...` fallback; supports multi-symbol query |
| Policy / official updates | **White House public sitemap** `whitehouse.gov/post-sitemap.xml` | recent official posts | Every 15-30 min | `global_context_items` | Web source, not formal API; degrade without blocking trading |
| Geopolitical context | **AP World News page** `apnews.com/world-news` | relevant headlines + page metadata | Every 15-30 min | `global_context_items` | Web source, not formal API; degrade without blocking trading |
| Insider Form 4 | **SEC EDGAR current filings Atom/RSS + filing XML** | Forms 4/4-A and transactions | Existing scheduled collector | existing `insider_trades` | Keep current batch model |
| Premarket price | **Alpaca Market Data `/v2/stocks/bars`**, `timeframe=1Min`, multi-symbol | latest print between 04:00 ET and decision time | Live pre-open | live overlay; optionally audit raw inputs | Batch symbols; do not call once per ticker |
| Intraday bars | **Alpaca Market Data `/v2/stocks/bars`**, multi-symbol | regular-session minute bars | Live intraday | live overlay / decision audit | Batch current scope |
| Latest bar | **Alpaca `/v2/stocks/bars/latest`** | one latest minute bar per symbol | Optional live shortcut | not primary persistent store | Endpoint accepts comma-separated symbols |
| Option chain | **Alpaca `/v1beta1/options/snapshots/{underlying_symbol}`** | quotes/trades/Greeks per contract | Only after shortlist | candidate audit if needed | Free `indicative` feed is suitable for screening, not high-quality execution pricing |
| Broker positions / orders | **Alpaca Trading API** | account, positions, orders, execution | Live | existing portfolio/execution tables | Separate from market-data ingestion |

---

## 4. Daily OHLCV: move completely out of pre-open

### 4.1 Why

Daily history changes only once per trading day. Re-fetching 252 days of history for every ticker during pre-open is pure operational risk and wastes provider quota.

The post-close batch should fetch the active research universe plus benchmark/support symbols such as `SPY`, `QQQ`, `GLD`, and any other symbols needed by macro or relative-strength logic.

### 4.2 Yahoo API usage

Use `yfinance.download()` for many symbols:

```python
yf.download(
    tickers=symbols,
    start=start_date,
    end=end_date,
    interval="1d",
    group_by="ticker",
    auto_adjust=False,
    actions=True,
    threads=False,
    progress=False,
)
```

Important behavior:

- `tickers` accepts a string or list of symbols.
- `interval="1d"` provides daily bars.
- `end` is exclusive.
- `auto_adjust=False` is deliberate: the system needs both the **actual prior close** for premarket-gap calculation and an adjusted series for technical history.
- `actions=True` gives dividend/split information when available.
- Use controlled chunking, for example 25-50 symbols per application chunk, instead of uncontrolled parallel threads.

### 4.3 Price adjustment semantics must be explicit

Current Alpaca code requests `adjustment=split`. Yahoo's `Adj Close` can reflect dividends as well as splits, so silently swapping one series for the other changes technical signal semantics.

Persist enough information to support both use cases:

```text
market_daily_bars
-----------------
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
provider_payload_version
ingested_at
available_for_decision_at
quality_flags_json
```

Use:

- `close_raw` for **premarket gap** and actual prior-close comparisons.
- an adjusted price series for long-horizon RSI/SMA/momentum so stock splits do not create false signals.
- a versioned feature definition so a future change in adjustment method does not silently alter replay results.

### 4.4 Batch behavior

The job should normally fetch only the missing/latest trading day. A separate backfill mode can fetch 300-400 calendar days when a ticker is new or a gap is detected.

The job is idempotent with a uniqueness key such as:

```text
(ticker, trade_date, provider)
```

### 4.5 Failure behavior

If Yahoo fails for a subset of symbols, the batch job may use Alpaca `/v2/stocks/bars` for only those missing symbols. Alpaca's historical bars endpoint supports a comma-separated symbol list and `next_page_token`; fallback must stay batched.

If both providers fail, keep the previous DB data and mark the ingestion run degraded. Do **not** start hundreds of emergency pre-open requests the next morning.

---

## 5. Fundamentals: daily snapshots, not live provider calls

### 5.1 Yahoo fields used by the current signal model

The existing `YFinanceFundamentalsProvider` already maps Yahoo fields into the trading schema. Keep the same normalization logic.

| Trading field | Yahoo input |
|---|---|
| sector | `info["sector"]` |
| company name | `shortName` / `longName` |
| market cap | `marketCap` |
| P/E | `trailingPE` |
| P/S | `priceToSalesTrailing12Months` |
| EV/Sales input | `enterpriseToRevenue` |
| FCF margin input | `freeCashflow / totalRevenue` |
| short interest % float | `shortPercentOfFloat * 100` |
| revenue growth | `revenueGrowth * 100` |
| operating margin | `operatingMargins * 100` |
| ROE | `returnOnEquity * 100` |
| ROA | `returnOnAssets * 100` |

Derived values such as `ev_sales_percentile`, `fcf_margin_score`, `valuation_percentile`, `margin_trend_score`, and `quality_score` must continue to use the repository's existing normalization helpers. Do not create a second scoring formula inside the batch job.

### 5.2 Storage

Reuse `fundamental_snapshots`.

A daily Yahoo batch creates one normalized snapshot per covered ticker. `available_for_decision_at` should be the time the batch actually ingested the data.

**Do not backdate Yahoo aggregated metrics to a fiscal-quarter date.** Yahoo `Ticker.info` is a current aggregate and usually does not expose a trustworthy publication timestamp for every field. Backdating it would create lookahead bias.

This means historical replay can use Yahoo fundamental snapshots reliably **from the date the system started collecting them forward**. It cannot reconstruct point-in-time fundamentals from before collection began.

### 5.3 Refresh and stale policy

Recommended default:

- run once after close or overnight;
- fresh: latest successful snapshot <= 48 hours old on trading days;
- soft stale: use last good snapshot but expose stale status;
- hard stale: after roughly 3-4 trading days, mark the fundamental family unavailable for strategies that require it.

The pre-open path should never call `Ticker.info` as an emergency fallback.

---

## 6. Earnings calendar: scheduled event ingestion

### 6.1 Primary source

Keep the existing `NasdaqEarningsCalendar` behavior, but move it into a scheduled batch.

Current public endpoint:

```text
GET https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
```

The endpoint is date-scoped. The batch job should fetch the next 45-60 days and normalize all rows in one scheduled run.

### 6.2 Storage

Reuse `calendar_events` instead of embedding earnings dates into a live fundamental fetch.

Recommended normalized event:

```text
event_key = earnings:{ticker}:{event_date}
event_type = own_earnings
ticker = TSM
event_time = expected earnings timestamp/date
source = nasdaq_earnings
available_for_decision_at = batch ingestion time
metadata_json = provider payload / timing qualifier
```

`earnings_in_days` becomes a derived signal:

```text
event_date - decision_date
```

### 6.3 Reschedules are a first-class case

Earnings dates move. The job must not leave the old future event looking active when Nasdaq returns a new date.

Use one of these implementations:

1. add `status` / `last_seen_at` to `calendar_events`; or
2. record supersession in `metadata_json` and make repository reads return only the latest active event per ticker/type.

Do not simply insert a second event and allow both dates to feed risk logic.

### 6.4 Fallback

Yahoo `Ticker.calendar` can be used as a **targeted repair source** for a symbol missing from the Nasdaq batch. It should not become a 178-ticker synchronous pre-open loop.

Nasdaq's endpoint is a public website endpoint rather than a formal versioned API contract, so this source should be treated as best-effort and monitored.

---

## 7. Economic calendar: FRED primary, FMP enrichment/fallback

### 7.1 FRED official API

Primary scheduled-date source:

```text
GET https://api.stlouisfed.org/fred/releases/dates
```

The current repository already filters a high/medium-signal release set such as CPI, PPI, Employment Situation, GDP, Retail Sales, Industrial Production, Housing Starts, and Consumer Sentiment.

Persist the normalized future events into existing `calendar_events`.

### 7.2 FMP

Current FMP documentation exposes:

```text
GET https://financialmodelingprep.com/stable/economic-calendar
```

FMP is useful for fields FRED's release-date endpoint does not reliably provide, especially:

- exact event time;
- impact level;
- estimate;
- previous value;
- actual value after release.

The current repository code uses the older `/api/v3/economic_calendar` endpoint. During this refactor, keep the provider adapter boundary and migrate to the current stable endpoint when account access supports it.

### 7.3 Important timestamp detail

FRED release dates are authoritative for dates, but not every release occurs at 08:30 ET. The current generic `13:30 UTC` default is acceptable only as a fallback.

When FMP or an official source provides an exact time, store the exact time. Event-risk blocking depends on hours, not merely calendar dates.

---

## 8. Macro indicators: persist observations separately from macro regime

The current `get_global_context()` fetches macro indicators during the trading run. This should become a batch source.

### 8.1 FRED endpoint

```text
GET https://api.stlouisfed.org/fred/series/observations
```

Current configured series include:

| Signal | FRED series |
|---|---|
| WTI crude | `DCOILWTICO` |
| US Treasury 2Y | `DGS2` |
| US Treasury 10Y | `DGS10` |
| US Treasury 20Y | `DGS20` |
| US high-yield OAS | `BAMLH0A0HYM2` |
| VIX close | `VIXCLS` |

Gold is currently represented by a GLD market-data proxy; after `market_daily_bars` exists, read GLD from the DB instead of issuing a fresh Alpaca daily-bar request.

### 8.2 New table

Use a normalized raw-observation table:

```text
macro_indicator_observations
----------------------------
series_key
provider_series_id
observed_on
value
previous_value
provider
published_at_or_source_time
ingested_at
available_for_decision_at
metadata_json
```

`macro_snapshots` should remain the **derived regime output**. It should not be the only place raw macro inputs exist.

### 8.3 Freshness semantics

FRED is not an intraday market feed. A Treasury series being one publication behind is different from a provider failure.

Track both:

- **observation freshness**: when the source last published a value;
- **ingestion freshness**: when our collector last successfully checked the provider.

A current collector with no new FRED observation is healthy. Do not label the signal as provider-missing merely because `observed_on` is yesterday.

---

## 9. Universe and liquidity: precompute after close

### 9.1 Asset metadata

Current Alpaca endpoint:

```text
GET /v2/assets
```

This data changes slowly. Fetch it daily or weekly and persist:

```text
market_assets
-------------
symbol
name
exchange
asset_class
status
tradable
shortable/easy_to_borrow if used
provider
provider_updated_at
ingested_at
```

Sector and industry should primarily come from the Yahoo fundamental snapshot rather than forcing Alpaca to provide fields it does not own.

### 9.2 Liquidity metrics

Once daily bars are local, compute these locally after every successful market-bar batch:

```text
universe_daily_metrics
----------------------
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

The pre-open universe scanner can then filter using a DB query rather than making market calls for liquidity.

### 9.3 Manual includes/excludes

Existing manual watchlist/include/exclude semantics stay unchanged. They are applied after loading the daily universe baseline.

---

## 10. Company news: frequent ingestion job

News changes quickly enough that once-per-day is insufficient, but it still does not belong in the synchronous decision path.

### 10.1 Primary source: Finnhub

Current endpoint:

```text
GET https://finnhub.io/api/v1/company-news
    ?symbol=AAPL
    &from=YYYY-MM-DD
    &to=YYYY-MM-DD
```

It returns fields already used by the repository: timestamp, headline, summary, source, related company information, and URL.

Finnhub's company-news endpoint is symbol-scoped, so the job should use bounded concurrency and provider-specific quotas rather than launching the whole universe at once.

### 10.2 Fallback: Alpaca News

Current endpoint:

```text
GET https://data.alpaca.markets/v1beta1/news
```

Useful query fields include:

```text
symbols=AAPL,TSLA,...
start=...
end=...
sort=desc
limit<=50
```

Because `symbols` accepts multiple tickers, Alpaca is a useful batch fallback, but it should not be the primary news path if the objective is to preserve Alpaca quota for live market data.

### 10.3 Storage and cadence

Reuse `event_news_items`. Run every 15-30 minutes for:

- active universe;
- watchlist/manual tickers;
- held positions.

Use stable dedupe keys based on provider article ID or canonical URL. Reprocessing the same time window must be safe.

News signal generation then becomes:

```text
SELECT recent decision-visible event_news_items
-> condense / classify if needed
-> build events_news signals
```

No outbound news fetch is required in pre-open or intraday decision code.

---

## 11. Global policy / geopolitical context: store once, not once per ticker

This is a structural issue in the current design. `SourceIngestionService._refresh_social_macro()` fetches one global context and then materializes global items into ticker-scoped rows. A single macro/political headline can therefore be duplicated across the entire universe.

### 11.1 Current source set

The repository currently uses:

- FRED for macro indicators;
- White House public post sitemap for official/policy posts;
- AP World News page for geopolitical headlines.

White House and AP are **web sources**, not formal versioned APIs. They must be treated as best-effort inputs that may change HTML or availability.

### 11.2 New canonical table

Store each global item only once:

```text
global_context_items
--------------------
global_context_item_id
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

Optionally add:

```text
global_context_ticker_links
---------------------------
global_context_item_id
ticker
link_type          # explicit_mention / company_mention / theme_readthrough
relevance_score
created_at
```

### 11.3 Signal generation

At decision time:

```text
recent global_context_items
        +
relevant ticker links/theme exposure
        ->
social_macro signal for TSM
```

This is cleaner than copying one geopolitical article into 178 ticker rows.

The existing `social_macro_items` table can remain for backward compatibility during migration, but new ingestion should ultimately use the normalized global model.

---

## 12. Insider data: keep the existing batch architecture

Insider trading already follows the correct pattern.

Current flow:

```text
SEC EDGAR current-filings Atom/RSS
        -> exact Form 4 / 4-A filtering
        -> filing XML fetch + parse
        -> insider_trades
        -> SignalPipeline reads DB
```

No redesign is needed beyond preserving the current point-in-time availability rules.

The SEC itself exposes current/latest filings and RSS feeds, and the repository already filters broad `type=4` results down to exact ownership Forms `4` and `4/A`.

This is the model the other slow data families should copy.

---

## 13. What must remain live

### 13.1 Premarket price

Use Alpaca multi-symbol historical bars:

```text
GET https://data.alpaca.markets/v2/stocks/bars
symbols=NVDA,TSM,AMD,...
timeframe=1Min
start=<04:00 ET>
end=<decision time>
feed=iex   # typical free-plan stock feed
```

Alpaca's endpoint supports comma-separated symbols and pagination. Pre-open must make a batch request, not one request per ticker.

Premarket gap is computed using:

```text
(latest_premarket_price - previous_close_raw) / previous_close_raw
```

The prior close comes from `market_daily_bars`; only the current premarket price is live.

### 13.2 Intraday bars

Use the same multi-symbol Alpaca bars endpoint with `timeframe=1Min` for only the current intraday scope.

A pre-open run must make **zero** regular-session intraday calls.

### 13.3 Option chain

Only fetch option data after the stock/strategy layer has produced a shortlist.

Current Alpaca endpoint:

```text
GET https://data.alpaca.markets/v1beta1/options/snapshots/{underlying_symbol}
```

The endpoint returns latest trade, quote, and Greeks and supports pagination/filtering by expiration/strike/type.

Important limitation: on a free/no-OPRA setup, Alpaca uses the `indicative` option feed; official documentation describes it as delayed/modified relative to OPRA. Use it for screening/strategy feasibility, not as if it were execution-quality NBBO data.

Expected flow:

```text
178 stocks
   -> DB + premarket signal scoring
   -> 10-20 candidates
   -> 3-8 option-relevant candidates
   -> option chain for only those names
```

---

## 14. Point-in-time and freshness contract

This is not optional. Moving data to DB only improves reliability if replay and freshness semantics remain correct.

### 14.1 Every persisted external fact needs these times

```text
event_time                # when the underlying fact occurred / applies
published_at              # when provider/source published it, if known
ingested_at               # when our job fetched it
available_for_decision_at # earliest time trading is allowed to use it
```

Every decision-side query must enforce:

```sql
available_for_decision_at <= decision_time
```

### 14.2 Recommended freshness defaults

| Family | Fresh | Soft stale behavior | Hard stale behavior |
|---|---|---|---|
| Daily bars | previous completed trading day present | use previous bar if one expected session is missing and flag stale | technical family unavailable after >1-2 missing trading sessions |
| Fundamentals | <=48h on trading days | use last good snapshot | unavailable after ~3-4 trading days |
| Earnings calendar | job checked within 24h | use last known event but flag stale | block earnings-sensitive strategies after ~48h without coverage |
| Economic calendar | job checked within 24h | use last known schedule | risk calendar unavailable after ~48h |
| Company news | <=30m during active monitoring | use recent DB rows but flag stale | news family unavailable after ~90m during active session |
| Global context | <=30m | use recent rows but flag stale | macro/social family degraded after ~90m |
| Asset master | <=7d | use last good | exclude newly uncertain symbols only if materially stale |
| Universe liquidity | previous completed session | use last completed metrics | do not run broad scanner without a recent liquidity baseline |
| Insider | existing coverage-window rule | existing behavior | existing behavior |

These are initial defaults and should be configurable.

### 14.3 Separate three states

Every source family must distinguish:

1. **covered + value/event exists**
2. **covered + no value/event exists**
3. **not covered / provider failed**

Examples:

- `direct_negative_catalyst_type = None` with fresh news coverage means **no negative catalyst found**, not missing data.
- no earnings event in the configured 60-day horizon with a successful Nasdaq batch means **no known event**, not provider failure.
- no Form 4 rows for TSM while the market-wide SEC collector is current means **no recent insider activity**, not missing insider data.

This distinction should flow into `source_freshness_json` and `missing_signals_json` so the LLM does not turn normal absence into a wall of “missing data” warnings.

---

## 15. Batch-job orchestration

### 15.1 Suggested jobs

| Job | Suggested cadence | Writes |
|---|---|---|
| `market_daily_bars_batch` | after market close, once per trading day | `market_daily_bars` |
| `fundamentals_batch` | nightly / after close | `fundamental_snapshots` |
| `asset_master_batch` | daily or weekly | `market_assets` |
| `universe_metrics_compute` | immediately after daily bars | `universe_daily_metrics` |
| `earnings_calendar_batch` | daily | `calendar_events` |
| `economic_calendar_batch` | daily | `calendar_events` |
| `macro_indicator_batch` | daily before pre-open; optional post-close refresh | `macro_indicator_observations` |
| `company_news_batch` | every 15-30 min | `event_news_items` |
| `global_context_batch` | every 15-30 min | `global_context_items` |
| `sec_edgar_form4` | existing schedule | `insider_trades` |
| `preopen_data_health_check` | shortly before pre-open | no source data; verifies freshness/coverage |

Do not run all these jobs inside one monolithic task. A Yahoo failure should not prevent SEC or calendar ingestion.

### 15.2 Reuse ingestion telemetry

Every job should create a `source_ingestion_runs` record with:

```text
source_family
run_type = scheduled_batch
scope_json
provider
as_of
status
coverage_json
error_code / error_message
metadata_json
```

External requests continue to write `provider_request_runs`.

Useful coverage examples:

```json
{
  "tickers_requested": 178,
  "tickers_succeeded": 176,
  "tickers_missing": ["TSM", "XYZ"],
  "rows_written": 176,
  "fallback_used": true
}
```

A successful job with zero relevant events should still record coverage explicitly.

---

## 16. Pre-open workflow after the redesign

The final pre-open path should be simple and deterministic.

### Step 1 - Load universe from DB

Read `market_assets` + `universe_daily_metrics`, then apply current user/manual filters.

### Step 2 - Load slow signal inputs from DB

For each ticker/load in bulk:

- last 252 trading days of `market_daily_bars`;
- latest decision-visible `fundamental_snapshots`;
- upcoming `calendar_events`;
- recent `event_news_items`;
- recent global context + ticker/theme links;
- insider rows / coverage state;
- macro indicator observations.

### Step 3 - Run one live market overlay

Fetch multi-symbol Alpaca premarket minute bars for the selected universe.

### Step 4 - Build signals locally

Compute:

- RSI / SMA / ATR / momentum;
- relative strength vs SPY / QQQ;
- premarket gap;
- valuation/quality signals from stored fundamentals;
- earnings distance;
- catalyst/news signals;
- social/macro signals.

### Step 5 - Score and shortlist

Run the existing strategy/candidate logic.

### Step 6 - Fetch expensive/live enrichments only for shortlist

Examples:

- option chains;
- deeper transcript/event detail if later supported;
- any expensive candidate-specific API.

### Step 7 - Decision and execution

Execution remains separate and uses broker/live state.

---

## 17. Intraday workflow after the redesign

Intraday should reuse the same DB baseline rather than re-ingesting slow sources.

```text
DB baseline from latest successful batches
        +
frequent news/global-context jobs already running
        +
Alpaca batched current intraday bars
        ->
intraday signal refresh
```

The intraday path should not refetch:

- 252d daily history;
- fundamentals;
- earnings calendar;
- economic calendar;
- whole-universe option chains.

---

## 18. Failure and fallback policy

### 18.1 Principle

Fallback must happen in the **ingestion plane**, not by turning the trading run back into a web crawler.

### 18.2 Daily bars

```text
Yahoo batch succeeds -> write DB
Yahoo partially missing -> Alpaca batch only missing symbols
both fail -> keep last good DB data + degraded coverage
```

### 18.3 Fundamentals

```text
Yahoo fails -> keep last good snapshot
pre-open -> read last good + stale flag
```

No 178-symbol emergency fundamental fetch.

### 18.4 News / global context

If one frequent batch fails, use the last successful rows until hard-stale threshold. Trading may degrade confidence but should not lose unrelated technical/fundamental data.

### 18.5 Live Alpaca failure

If the live premarket request fails:

- keep complete DB-backed technical/fundamental/event snapshot;
- set `premarket_gap_pct=None`;
- mark live technical enrichment degraded;
- do not discard the daily technical record.

---

## 19. Database changes

### 19.1 New: `market_daily_bars`

Minimum recommended columns:

```text
id
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

Indexes:

```text
UNIQUE(ticker, trade_date, provider)
INDEX(ticker, trade_date)
INDEX(available_for_decision_at)
```

### 19.2 New: `market_assets`

Keep current active/tradable security metadata outside per-run universe snapshots.

### 19.3 New: `universe_daily_metrics`

Store post-close liquidity and volatility metrics used by scanner eligibility.

### 19.4 New: `macro_indicator_observations`

Store raw FRED observations separately from derived `macro_snapshots`.

### 19.5 New: `global_context_items`

Store policy/geopolitical items once globally. Add `global_context_ticker_links` if precomputed ticker/theme relevance becomes useful.

### 19.6 Reuse existing tables

Do not create replacements for:

```text
fundamental_snapshots
event_news_items
calendar_events
insider_trades
source_ingestion_runs
provider_request_runs
signal_snapshots
```

---

## 20. Migration / implementation order

Do not implement every source in one PR. The safe order is:

### Phase 1 - Remove the biggest Alpaca pressure

1. Add `market_daily_bars`.
2. Add Yahoo daily-bar batch ingestion.
3. Backfill required history.
4. Make technical signals read daily bars from DB.
5. Batch Alpaca premarket prices.
6. Make pre-open make zero intraday calls.

**Exit criterion:** a 178-stock pre-open run performs zero Alpaca historical-daily calls and still produces technical records for all covered tickers.

### Phase 2 - Fundamentals

1. Schedule Yahoo fundamentals ingestion.
2. Persist to existing `fundamental_snapshots`.
3. Remove synchronous `fetch_context()` from broad pre-open ingestion.
4. Add freshness/coverage semantics.

### Phase 3 - Calendars

1. Schedule Nasdaq earnings ingestion into `calendar_events`.
2. Schedule FRED/FMP economic-calendar ingestion into `calendar_events`.
3. Make pre-open read only from the calendar repository.

### Phase 4 - Universe data

1. Persist Alpaca asset master.
2. Compute daily liquidity metrics from DB bars.
3. Make scanner eligibility database-backed.

### Phase 5 - News and global context

1. Schedule company news every 15-30 min.
2. Remove synchronous per-ticker news fetches from decision paths.
3. Add normalized `global_context_items`.
4. Stop copying the same global item to every ticker.

### Phase 6 - Candidate-only expensive data

1. Remove `option_chain` from broad signal ingestion.
2. Add explicit post-shortlist option enrichment.
3. Persist decision-used option snapshot only when useful for audit/replay.

---

## 21. Acceptance criteria

The redesign is complete when all of these are true:

1. A 178-stock pre-open run reads historical bars and fundamentals from PostgreSQL.
2. The initial pre-open phase performs zero Alpaca daily-history calls.
3. The initial pre-open phase performs zero intraday regular-session calls.
4. The initial pre-open phase performs zero whole-universe option-chain calls.
5. Premarket prices are fetched in a multi-symbol Alpaca request/path.
6. Yahoo failure cannot erase otherwise valid DB-backed technical snapshots.
7. Earnings/calendar/news/provider outages are visible through ingestion-run coverage rather than being silently converted to null fields.
8. `available_for_decision_at <= decision_time` is enforced on all DB inputs used for replay or live decisions.
9. “No event/activity” and “provider unavailable” are represented differently.
10. The trading run remains usable when a non-live external provider is temporarily unavailable.

---

## 22. API reference notes

### Yahoo / yfinance

- `yfinance.download`: multi-ticker market-data downloader; supports `interval`, `start`, `end`, `prepost`, `auto_adjust`, and `actions`.
- `yfinance.Ticker.info`: current company/valuation/fundamental metadata.
- `yfinance.Ticker.calendar`: ticker-level event/earnings fallback.
- yfinance is an unofficial wrapper around Yahoo Finance. That is another reason to keep it outside the trading critical path.

Reference: `https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html`

### Alpaca Market Data

- Historical/multi-symbol stock bars: `GET https://data.alpaca.markets/v2/stocks/bars`
- Latest multi-symbol bars: `GET https://data.alpaca.markets/v2/stocks/bars/latest`
- News: `GET https://data.alpaca.markets/v1beta1/news`
- Option chain by underlying: `GET https://data.alpaca.markets/v1beta1/options/snapshots/{underlying_symbol}`

References:

- `https://docs.alpaca.markets/us/reference/stockbars`
- `https://docs.alpaca.markets/us/reference/stocklatestbars-1`
- `https://docs.alpaca.markets/us/reference/news-3`
- `https://docs.alpaca.markets/us/reference/optionchain`

### FRED

- Series observations: `GET https://api.stlouisfed.org/fred/series/observations`
- Release dates: `GET https://api.stlouisfed.org/fred/releases/dates`

References:

- `https://fred.stlouisfed.org/docs/api/fred/series_observations.html`
- `https://fred.stlouisfed.org/docs/api/fred/releases_dates.html`

### Financial Modeling Prep

- Current documented economic calendar: `GET https://financialmodelingprep.com/stable/economic-calendar`

Reference: `https://site.financialmodelingprep.com/developer/docs/stable/economics-calendar`

### Finnhub

- Company news: `GET https://finnhub.io/api/v1/company-news`

Reference: `https://finnhub.io/docs/api/quote` (Finnhub consolidated API documentation includes Company News).

### SEC EDGAR

- Continue using EDGAR latest/current filings Atom/RSS plus filing XML for Form 4/4-A.
- SEC provides public filing search, latest filings, RSS, submissions APIs, and XBRL APIs.

Reference: `https://www.sec.gov/search-filings`

### Nasdaq earnings

Current repository endpoint:

`https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`

Treat it as a best-effort public website endpoint with monitoring and fallback rather than as a formal guaranteed API contract.

### White House / AP

- White House: `https://www.whitehouse.gov/post-sitemap.xml`
- AP World News: `https://apnews.com/world-news`

These are web sources, not formal data APIs. They belong in fault-tolerant frequent ingestion jobs, never in the decision critical path.

---

## 23. Final design rule

The system should answer one question before making an external request:

> **Does this fact need to be fresher than the latest successful batch?**

If the answer is **no**, read PostgreSQL.

If the answer is **yes**, use a batched live API.

For this trading system that means:

```text
PostgreSQL = history + fundamentals + calendars + news + macro + insider + universe
Alpaca live = current price action + current broker state + shortlisted option data
```

That boundary is the main architectural change and should be preserved even if individual providers change later.
