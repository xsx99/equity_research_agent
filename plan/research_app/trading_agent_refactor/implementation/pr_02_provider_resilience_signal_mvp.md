# Implementation Module PR 2: Provider Resilience and Signal MVP

## PR 2: Provider Resilience + Three-Family Point-in-Time Signal MVP

**Goal:** Build a deterministic pre-market signal path that can be replayed without lookahead across three MVP signal families: technical, fundamental, and events/news. This PR includes provider guardrails, user-editable universe filters, active manual requests, point-in-time signal snapshots, portfolio-intent eligibility, and relationship-backed peer basket construction. No options, no LLM calls, no full transcript parsing, no deep SEC/insider interpretation, and no trading decisions yet.

**Files:**
- Create: `src/trading/manual_requests.py`
- Create: `src/trading/provider_resilience.py`
- Create: `src/trading/point_in_time.py`
- Create: `src/trading/universe.py`
- Create: `src/trading/signals.py`
- Create: `src/trading/signal_sources.py`
- Create: `src/trading/fundamental_signals.py`
- Create: `src/trading/event_news_signals.py`
- Create: `src/trading/pipeline.py`
- Create: `src/trading/repository.py`
- Modify: `src/trading/relationships.py`
- Modify: `src/trading/portfolio_intents.py`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/007_universe_signal_mvp_tables.py`
- Modify: `src/tools/market_data/types.py` if the provider protocol needs universe support
- Modify: `src/tools/market_data/alpaca_provider.py` to add an asset/universe method if needed
- Test: `tests/trading/test_universe.py`
- Test: `tests/trading/test_provider_resilience.py`
- Test: `tests/trading/test_point_in_time.py`
- Test: `tests/trading/test_manual_requests.py`
- Test: `tests/trading/test_signals.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/trading/test_fundamental_signals.py`
- Test: `tests/trading/test_event_news_signals.py`
- Test: `tests/trading/test_relative_strength.py`
- Test: `tests/trading/test_pipeline.py`
- Test: `tests/db/test_trading_models.py`

Implementation notes:

- Add a `UniverseProvider` interface with a test fake and an Alpaca implementation.
- Wrap live provider calls with `ProviderResiliencePolicy`: per-provider/per-endpoint rate limiter, batch fetch where available, exponential backoff with jitter, request budget, cache/freshness gate, circuit breaker, and degraded mode.
- Persist every live-provider attempt or cache decision through `ProviderRequestRun`.
- Unit tests must use fake providers. Provider integration tests should use `vcrpy` cassettes or equivalent recorded fixtures. Live provider smoke tests are opt-in only.
- Include a config fallback `TRADING_UNIVERSE_SYMBOLS` for local/dev tests.
- Implement active `UniverseFilterConfig` loading and updates with user-editable liquidity thresholds, sector/industry include/exclude lists, exchange/asset filters, and manual include/exclude ticker overrides.
- Default to common stocks with configurable minimum price and minimum average dollar volume filters; persist excluded symbols with reasons such as `below_min_price`, `below_min_dollar_volume`, `sector_excluded`, `not_common_stock`, or `manual_exclude`.
- Persist included and excluded symbols with exclusion reasons.
- Add `ManualTickerRequestService` for creating, dismissing, cancelling, and loading active manual requests.
- Merge active manual requests into the signal snapshot job even when the ticker did not pass the scanner ranking threshold.
- Manual requests stay active across trading days until dismissed by the user; update `last_evaluated_at` and latest result fields on each evaluation.
- Manual requests can bypass scanner selection threshold, but not ticker validation, market-data availability, liquidity rules, or later risk checks.
- Support `review_only` and `paper_trade_eligible` request modes.
- Use the PR 1b portfolio-intent helpers/service so `core_holding` eligibility later requires an approved active intent instead of LLM inference.
- Use the PR 1b relationship helpers/service and peer-basket builder for structured peer/theme relationships used by relative-strength and replay attribution.
- Add ORM models and migration for PR 2 operational state only:
  - `UniverseFilterConfig`
  - `UniverseSnapshot`
  - `UniverseSymbol`
  - `ManualTickerRequest`
  - `SourceIngestionRun`
  - `ProviderRequestRun`
  - `FundamentalSnapshot`
  - `EventNewsItem`
  - `SignalSnapshot`
- Create `alembic/versions/007_universe_signal_mvp_tables.py` with `down_revision = "006"`.
- `SignalSnapshot` must include `decision_time`, `available_for_decision_at`, `max_input_available_for_decision_at`, `source_record_refs_json`, `source_available_times_json`, `excluded_future_source_count`, and `point_in_time_passed`.
- `ProviderRequestRun` must include provider, endpoint/source family, cache hit/miss, request count, budget remaining, retry/backoff, latency, status, error code, and circuit state.
- `FundamentalSnapshot` stores latest point-in-time provider or existing normalized fundamental rows: ticker, period/as-of metadata, provider, source refs, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, raw payload reference, and normalized metrics JSON.
- `EventNewsItem` stores headline/calendar/provider-event rows: ticker, optional source ticker, event type, direction/sentiment, importance, headline/summary, provider/source refs, dedupe key, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, and raw payload reference.
- Build signal snapshots from existing daily bars/context and controlled provider/fake-provider source rows across all three MVP families:
  - `technical`: 1d/5d/10d/20d/60d returns, 20/50/200 SMA distance, trend slope, RSI 2/3/14, ATR%, realized volatility percentile, beta proxy vs `SPY`/`QQQ`, drawdown from recent high, distance from 52-week high, relative volume, volume acceleration, dollar volume, gap/premarket gap when available, and relative strength vs `SPY`, `QQQ`, sector/theme ETF, and peer basket.
  - `fundamental`: market-cap bucket, revenue-growth score, margin/profitability trend, quality/profitability score, valuation band or percentile, EV/sales or P/E percentile when available, FCF/profitability proxy when available, short-interest bucket when available, and explicit stale/missing flags.
  - `events_news`: earnings date distance, known event date, own earnings headline result when available, analyst upgrade/downgrade count, price-target revision score, guidance/news flag, customer/order/product/regulatory headline flags, high-signal news counts for 24h/7d, sentiment/direction, catalyst quality score, and direct negative catalyst type.
- Add source-ingestion run metadata for every scheduled or targeted refresh so freshness decisions are replayable.
- Add `SignalSourceRepository` or equivalent adapters that read normalized Postgres-backed sources or fake-provider fixtures for the PR 2 technical, fundamental, and events/news signal set. Deep insider/Form 4, full SEC parsing, full transcripts, options chains, and full macro/sector read-through are deferred until later source-specific PR work.
- Prefer normalized Postgres rows over ad hoc live provider calls. Provider calls are allowed only through controlled refresh/fallback adapters and must record attempted source, freshness, provider request metadata, and degraded-mode state.
- Store source provenance for each signal, including `source`, `source_table` or provider name, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, and missing/stale/unavailable status.
- Store pre-open signal snapshots as the daily baseline with `snapshot_type = "pre_open"`, `decision_time`, `source_freshness_json`, `missing_signals_json`, `stale_signals_json`, `source_record_refs_json`, `source_available_times_json`, `max_input_available_for_decision_at`, `excluded_future_source_count`, and `point_in_time_passed`.
- Implement source freshness SLA config for each source family. Low-frequency fields can be carried forward when inside SLA; stale required fields must downgrade or block candidate outputs.
- Verify point-in-time behavior with tests that insert one available source row and one future source row, then assert the future row is excluded from the snapshot.
- Cover the point-in-time exclusion separately for technical market bars, `FundamentalSnapshot`, and `EventNewsItem` rows so each MVP signal family proves it cannot leak future data.
- Defer deep insider/Form 4, full SEC parsing, full earnings-call transcript interpretation, option-chain fields, and full macro/sector read-through to later slices; represent them as explicit missing fields in PR 2 snapshots.
- Add relative-strength fields vs `SPY`, `QQQ`, sector/theme ETF when configured, and peer basket when available.
- Add catalyst quality fields and direct-negative-catalyst fields only from structured event/news source rows; otherwise mark them missing without asking the LLM to infer values.
- Add option-chain placeholder fields as explicitly missing unless a provider exists.
- Store missing signals explicitly.
- Mark manual request results as `blocked_by_missing_data` when required market data cannot be fetched.
- Use no LLM calls.

Stop after PR 2 for review/merge.

---

