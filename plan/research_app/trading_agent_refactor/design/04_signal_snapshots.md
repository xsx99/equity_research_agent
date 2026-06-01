# Design Module 04: Signal Snapshots and Point-in-Time Data

## 7. Signal Snapshots

Signals should be deterministic Python outputs and stored before any LLM call. Each signal includes `value`, `direction`, `z_score/percentile` when available, `lookback`, `source`, `source_table` or provider name, freshness metadata, `computed_at`, and point-in-time availability metadata.

`SignalPipeline` is the V2 replacement for the current version's per-ticker research context assembly. It should not be limited to price/technical indicators. For each ticker it should assemble a replayable `quant_signal_snapshot` from:

- market bars and quote/liquidity data
- normalized insider trading / Form 4 / SEC-derived rows already stored in Postgres
- normalized news, analyst rating, guidance, filing, and catalyst/event rows already stored in Postgres
- fundamentals and valuation data already stored in Postgres
- earnings calendar and known event data
- target-company earnings release, guidance, transcript, and post-earnings analyst revision signals when the source ticker equals the snapshot ticker
- option-chain derived fields when available
- macro/sector/theme read-through events derived from peer, customer, supplier, competitor, or sector-leader earnings releases and transcripts
- existing research/global-context artifacts when they are already persisted and have explicit freshness/source metadata

Provider calls are allowed only as controlled refresh/fallback steps, not as hidden prompt-time lookups. If Postgres has stale or missing data, the snapshot must record the missing/stale status and the source that was attempted.

Peer earnings read-through is a SignalPipeline source family, but it is classified with macro/sector/theme context rather than company-specific ticker signals. It can be attached to a ticker snapshot only as exposure context, e.g. "this ticker is exposed to a positive AI capex read-through from a peer/leader earnings call." It should not by itself become a target-company catalyst.

Own-company earnings are different. If the snapshot ticker is the reporting company, the release/transcript/guidance data is direct company evidence and should populate the ticker's own catalyst, fundamental, event, and analyst-revision signals.

### Signal Groups

| Group | Example Signals |
| --- | --- |
| Momentum / Trend | 5d/20d/60d returns, price vs SMA/EMA, trend slope, new high distance |
| Mean Reversion | RSI 2/3/14, distance from VWAP/SMA, short-term reversal score |
| Volume / Liquidity | relative volume, dollar volume, volume acceleration, spread proxy, liquidity eligibility |
| Volatility / Risk | ATR%, realized volatility, gap size, intraday range, beta proxy, drawdown from recent high |
| Relative Strength | return vs SPY, QQQ, sector ETF, theme ETF, peer basket; rank within sector/theme/peer group |
| Event / Calendar | earnings date distance, post-earnings window, economic calendar risk day |
| Own Earnings / Guidance | own earnings beat/miss, revenue/EPS surprise, guidance raise/cut, segment growth, margin change, transcript sentiment, post-earnings analyst revision |
| Macro / Sector Read-through | peer or sector-leader earnings read-through direction, mechanism, source tickers, relationship type, affected theme, validity window, target confirmation requirement |
| Insider / SEC | net insider value, cluster buys, sale concentration, officer/director weight, recent Form 4 freshness |
| News / Sentiment | high-signal news count, analyst rating events, guidance, filing/news freshness, catalyst quality score, direct negative catalyst flags |
| Fundamentals | valuation bands, growth/margin quality, short interest, market cap/liquidity quality filters |
| Options | option chain availability, delta, IV rank/percentile, premium, breakeven, DTE, earnings-through-expiry flag |
| Confidence Calibration | historical win rate/alpha by strategy, expression bucket, trade identity, direction, catalyst type, sector/theme, and market regime |

MVP signal surface should cover three families, not only technicals:

1. `technical`: OHLCV/quote-derived momentum, trend, mean-reversion, volume/liquidity, volatility, gap, and relative-strength signals.
2. `fundamental`: latest point-in-time fundamental/valuation summary signals such as market-cap bucket, revenue growth, margin/profitability quality, valuation band/percentile, FCF/profitability proxy, short-interest bucket when available, and explicit stale/missing flags.
3. `events_news`: headline/calendar/provider-event level signals such as earnings date proximity, own earnings headline result when available, analyst upgrade/downgrade or price-target revision, guidance/news flags, customer/order/regulatory/product headlines, high-signal news counts, sentiment/direction, and direct negative catalyst flags.

MVP does not need every future signal. It should avoid full transcript parsing, full SEC/insider interpretation, option-chain strategy signals, and full macro/sector read-through until their source families are implemented. Missing signals must be stored explicitly as `null` or `status=missing`; the prompt must not fabricate them.

Signal source rules:

- Prefer normalized Postgres tables over ad hoc live fetches so every trading decision is replayable.
- Preserve source provenance per signal, e.g. `market_bars`, `insider_transactions`, `sec_filings`, `news_articles`, `fundamental_snapshots`, `earnings_events`, `earnings_transcripts`, `option_chain_snapshots`, or `research_context`.
- Store `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at` where relevant. Use `filing_date`, `as_of`, or provider observation time as source-specific supporting fields, not as substitutes for decision availability.
- Separate raw inputs from derived scores. For example, persist raw insider transactions elsewhere, then store derived fields such as `insider_net_buy_value_90d` and `insider_cluster_buy_count_90d` in `signal_snapshots`.
- Do not let the LLM infer missing insider/news/fundamental facts. Missing facts remain missing signals.

### Point-In-Time and No-Lookahead Contract

Every source record and every derived signal snapshot must be replayable as of a specific decision time. The system must distinguish:

- `event_time`: when the underlying market/company/economic event happened
- `published_at`: when the source made the event public
- `ingested_at`: when the system stored the source row
- `available_for_decision_at`: the earliest time this row or signal was eligible to influence a trading decision after publication delay, ingestion delay, provider delay, and freshness gates

Pre-market decisions may only use source rows and derived signals where `available_for_decision_at <= decision_time`. Intraday rebalance decisions use the same rule with the rebalance timestamp. Backtests, replay, reflection, and strategy evolution must load snapshots through this decision-time filter instead of querying the latest normalized source tables.

Derived signals inherit the maximum `available_for_decision_at` of their required inputs. If any required input is missing, stale, or not yet decision-available, the derived signal must be marked missing/stale/unavailable rather than computed from future information. This applies especially to earnings, analyst revisions, SEC filings, news, option chains, and revised macro/economic data.

Each `signal_snapshot` should persist:

- `decision_time`
- `available_for_decision_at`
- `snapshot_type`
- `source_record_refs`
- `source_available_times`
- `max_input_available_for_decision_at`
- `excluded_future_source_count`
- `point_in_time_passed`

Historical replay must be able to rebuild or verify the same candidate set from these fields without using later corrections, revised datasets, or post-decision source rows.

### Source Ingestion, Baseline, and Freshness

Source ingestion jobs are part of the system data layer, not separate trading functions. Their job is to keep raw/normalized Postgres rows fresh enough for `SignalPipeline` and `HourlySignalRefreshPipeline` to build replayable snapshots. Each ingestion run should persist source name, run type, scope, coverage, `started_at`, `completed_at`, `as_of`, status, attempted provider, and error metadata.

Recommended source cadence:

| Source Family | Normal Cadence | Intraday Treatment |
| --- | --- | --- |
| Insider / Form 4 | Daily early-morning plus post-close catch-up | Usually freshness check only; no hourly full refresh unless a targeted filing source supports it. |
| SEC material filings | Pre-open and post-close catch-up | Targeted hourly check for open positions, top candidates, and manual requests. |
| Fundamentals / raw valuation | Daily pre-open for active universe; broader universe weekly or rolling | Carry forward if within freshness SLA; do not hourly refresh full fundamentals. |
| Valuation derived from price | Pre-open from latest price and fundamentals | Recompute only if price move materially changes valuation band and strategy needs it. |
| Earnings calendar / event calendar | Daily pre-open and post-close | Refresh same-day event status and relevant portfolio events; do not rescrape irrelevant calendar rows hourly. |
| Own earnings release / transcript | Event/news ingestion around expected report time | Targeted polling when a portfolio/candidate/manual ticker is expected to report or has just reported. |
| Peer / sector-leader read-through | Event-calendar and news/transcript ingestion for mapped relationships | Targeted refresh only for relevant peer/customer/supplier/competitor/leader events. |
| News / analyst events | Pre-open, hourly intraday, post-close | Hourly scoped refresh for positions, same-day trades, top candidates, manual requests, and high-impact sector/macro news. |
| Market bars / quotes | Daily bars after close; current quotes during trading day | Required for hourly intraday snapshots and relative-strength deltas. |
| Technical signals | Computed by `SignalPipeline` from market data | Pre-open full universe; intraday scoped recompute only for portfolio-relevant tickers. |
| Option chains / marks | Pre-open/after open where available; mark open option positions | Hourly for open option positions and option-eligible candidates; missing required option data blocks option opens/rolls. |

Every provider adapter must run behind a resilience wrapper:

- per-provider and per-endpoint rate limiter
- batch fetch API where available
- exponential backoff with jitter for transient failures
- request budget per run and per trading day
- cache/freshness gate before making external calls
- circuit breaker that opens after repeated provider failures or rate-limit responses
- degraded mode that marks affected source families stale/missing while allowing unrelated pipeline stages to continue

The wrapper should persist `provider_request_runs` with provider, endpoint/source family, scope, cache hit/miss, request count, budget remaining, latency, retry count, status, error code, and circuit-breaker state. A provider outage should not block the whole universe scan when required minimum data from other sources remains available.

Pre-open snapshots are the daily baseline. They should be persisted as `snapshot_type = "pre_open"` and include all available source families, source freshness status, missing/stale fields, and the universe/manual-request context that caused the ticker to be evaluated.

Intraday snapshots must not overwrite the pre-open baseline. They reuse the same canonical signal schema, but store only refreshed intraday values, carried-forward baseline values, and deltas:

```text
signal_snapshots
  snapshot_type = "pre_open"
  signal_snapshot_id = baseline_signal_snapshot_id

intraday_signal_snapshots
  baseline_signal_snapshot_id
  previous_intraday_snapshot_id
  refreshed_signals
  carried_forward_from_baseline
  delta_vs_baseline
  delta_vs_previous
  source_freshness
```

Intraday source precedence:

- High-frequency fields override the baseline when refreshed: price, volume, VWAP/opening range, gap state, intraday relative strength, option marks/Greeks/IV, and fresh news/events.
- Low-frequency fields are carried forward from baseline unless a new row is detected: insider, most fundamentals, most SEC-derived summaries, and routine event-calendar fields.
- Any carried-forward field must be explicitly marked as `carried_forward_from_baseline` so the UI and rebalance logic do not mistake it for newly refreshed data.
- New target-company events, e.g. own earnings release, transcript, analyst action, or material SEC filing, become intraday deltas and can invalidate or upgrade the morning thesis.
- Related-company events remain macro/sector/theme read-through context and require target-ticker confirmation before affecting trade eligibility.

Freshness gates:

- Required high-frequency data missing or stale for an open position should block new adds and may limit actions to `hold`, `reduce`, or `exit`.
- Missing option chain, leg pricing, Greeks, max-loss, margin, or buying-power data should block opening or rolling paper option strategies.
- Low-frequency data within its SLA may be carried forward; outside its SLA it must be marked stale and can downgrade candidates to `catalyst_watch`, `ordinary_watch`, or `blocked_by_missing_data`.
- Missing direct-negative-catalyst checks should prevent high-confidence bearish actions.

### Required Signal Families For Strategy Matching

The signal schema should explicitly support the strategy catalog above:

- Catalyst signals: `fresh_catalyst_type`, `catalyst_published_at`, `catalyst_strength_score`, `beat_raise_flag`, `guidance_revision_score`, `analyst_revision_count`, `direct_negative_catalyst_type`.
- Own earnings signals: `own_earnings_reported_at`, `own_earnings_event_type`, `own_eps_surprise_pct`, `own_revenue_surprise_pct`, `own_guidance_revision_score`, `own_segment_growth_score`, `own_margin_change_score`, `own_transcript_available`, `own_transcript_sentiment_score`, `own_earnings_call_key_topics`, `own_post_earnings_analyst_revision_count`.
- Insider / SEC signals: `insider_net_buy_value_30d`, `insider_net_buy_value_90d`, `insider_cluster_buy_count_90d`, `officer_buy_flag`, `director_buy_flag`, `sale_concentration_score`, `recent_form4_filing_at`, `sec_filing_event_type`.
- News / analyst signals: `high_signal_news_count_24h`, `high_signal_news_count_7d`, `analyst_upgrade_count_30d`, `analyst_downgrade_count_30d`, `price_target_revision_score`, `guidance_news_flag`, `customer_order_news_flag`, `regulatory_news_flag`, `news_freshness_minutes`.
- Fundamental signals: `revenue_growth_score`, `margin_trend_score`, `valuation_percentile`, `ev_sales_percentile`, `fcf_margin_score`, `quality_score`, `short_interest_pct_float`, `market_cap_bucket`.
- Gap/VWAP signals: `opening_gap_pct`, `premarket_gap_pct`, `vwap_reclaim`, `vwap_hold`, `opening_range_high_break`, `opening_range_low_break`, `gap_fill_pct_remaining`.
- Breakout/base signals: `resistance_break_score`, `base_duration_days`, `price_near_52w_high_pct`, `new_high_break`, `breakout_volume_confirmed`.
- Trend/pullback signals: `trend_slope_20d`, `price_vs_sma_20`, `price_vs_sma_50`, `pullback_depth_pct`, `support_reclaim_score`, `selling_volume_dry_up`.
- Volatility compression signals: `atr_pct`, `realized_volatility_percentile`, `range_compression_percentile`, `squeeze_score`, `range_break_direction`.
- Relative strength signals: `rs_vs_spy_20d`, `rs_vs_qqq_20d`, `rs_vs_sector_20d`, `rs_vs_theme_etf_20d`, `rs_vs_peer_basket_20d`, `sector_rank_percentile`, `peer_rank_percentile`, `rotation_score`.
- Macro/sector/theme read-through signals: `readthrough_source_tickers`, `readthrough_scope`, `readthrough_direction`, `readthrough_strength_score`, `readthrough_mechanisms`, `readthrough_relationship_types`, `readthrough_affected_theme`, `readthrough_valid_until`, `needs_target_price_confirmation`, `target_confirmation_status`.
- Mean reversion signals: `rsi_2`, `rsi_3`, `rsi_14`, `distance_from_sma_20_pct`, `capitulation_volume_score`, `reversal_triggered`.
- Short squeeze signals: `short_interest_pct_float`, `days_to_cover`, `borrow_fee_proxy`, `float_rotation_proxy`, `squeeze_pressure_score`.
- Sympathy signals: `leader_ticker`, `leader_catalyst_type`, `peer_link_strength`, `industry_move_pct`, `laggard_confirmation_score`.
- Event timing signals: `earnings_in_days`, `known_event_date`, `pre_event_runup_score`, `event_risk_flag`.
- Options signals: option-chain availability; candidate `option_strategy_type`; per-leg call/put, side, strike, expiry, DTE, delta/gamma/theta/vega, IV rank/percentile, bid/ask/mid, volume/open interest; strategy-level net debit/credit, max loss, max profit, breakevens, margin requirement, buying-power effect, event-through-expiry flag, and assignment exposure when short options are present.
- Confidence calibration signals: `historical_strategy_win_rate`, `historical_strategy_alpha_vs_benchmark`, `historical_direction_win_rate`, `historical_catalyst_type_alpha`, `confidence_calibration_bucket`.

