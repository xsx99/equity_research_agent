# Design Module 05: Workflows and Decision Contracts

## 8. Daily Workflow

All scheduled times are in `America/New_York`.

| Time | Job | Output |
| --- | --- | --- |
| 07:00 | Universe refresh | tradable symbols and exclusions |
| 07:15 | Macro snapshot + event calendar refresh | `macro_snapshots`, normalized `calendar_events`, portfolio-scored `portfolio_event_risk_assessments`, and prior-night/early-morning sector-theme read-through context |
| 07:30 | Pre-market signal computation | `signal_snapshots` for the universe, including own-event timing and macro/sector/theme read-through exposure context |
| 08:15 | Strategy matching and candidate scoring | `candidate_scores` with strategy, horizon, evidence, invalidators |
| 08:45 | Trading decision generation | `trading_decisions` with selected action and downstream risk decision inputs |
| 09:30 | Alpaca paper open execution | broker-backed stock `paper_orders`, `paper_executions`, synced open positions |
| Hourly 10:00-15:00 | Intraday signal refresh + news scan | `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts`, possible rebalance proposals |
| Immediately after material signal change or critical/high alert | Intraday rebalance | approved/reduced/rejected `intraday_rebalance_decisions`, possible paper orders |
| 15:55 | Optional risk check | approved close/rebalance decisions if enabled |
| 16:05 | Portfolio mark | Alpaca-synced `portfolio_snapshots`, trade PnL |
| 16:20 | Daily reflection | `daily_reflections` |
| 16:40 | Learning factor update | `learning_factors`, next-run context |
| 16:50 | Strategy evolution | `strategy_proposals`, candidate/shadow strategy updates |

Manual runs remain available for debugging, but scheduled daily flow is the primary product path.

### Universe Filter Policy

The scanned universe should be a configurable subset of US listed common stocks, not every listed name by default. The active universe filter should be user-editable from the UI and persisted as a versioned config.

Default filter dimensions:

- minimum price, e.g. `min_price`
- minimum average dollar volume, e.g. `min_avg_dollar_volume`
- allowed or excluded sectors/industries
- exchange and asset-type eligibility, with common stock as the default asset type
- optional manual include/exclude ticker overrides

`UniverseProvider` should persist both included and excluded symbols with explicit exclusion reasons such as `below_min_price`, `below_min_dollar_volume`, `sector_excluded`, `not_common_stock`, or `manual_exclude`. Manual ticker requests can force evaluation outside scanner selection, but they still cannot bypass data availability, liquidity/tradability, or risk checks unless a future explicit override mode is designed.

Morning workflow semantics:

1. Scan the configured universe before the open using the active liquidity and sector filter, then compute all available pre-market/daily signals.
2. Refresh the normalized event calendar and score each upcoming event against current positions, active candidates, manual review tickers, core holdings, option expiries, strategy horizons, and factor exposures.
3. Match each symbol against tactical strategies and strategy expression buckets. Each match carries its own strategy horizon, required evidence, eligible trade identities, and invalidators.
4. Build benchmark and peer-basket context for each candidate so relative strength is measured against the right opportunity set, not only `SPY`.
5. Rank candidate scores by strategy fit, catalyst quality, relative strength, signal quality, macro compatibility, liquidity, event risk, confidence calibration, and learning-factor adjustments.
6. Select trade-path `selected_trades` and, when needed, separate `watch_candidates` for each ticker/action namespace under consideration.
7. Classify only selected trade-path candidates plus existing positions into a portfolio-pool trade identity before any order decision.
8. Build a tactical option plan only when the selected expression bucket and `trade_identity = "tactical_option_trade"` make an option expression eligible.
9. Pass only the selected candidates plus current positions and paper option positions into `TradingPipeline`.
10. `TradingPipeline` proposes an action, thesis, invalidators, suggested size, horizon, instrument expression, and trade identity.
11. Deterministic risk constraints and portfolio budget decide whether the proposed action becomes an approved Alpaca paper stock order request, a staged tactical paper option order, is reduced, or is rejected.
12. Separately, a pure `PortfolioHedgePlanner` may emit `portfolio_risk_intents` with deterministic `reduce`, `block_open`, `force_reduce`, and hedge proposals for the next `1-5` trading days. `RiskManager` remains the final owner of paper-only `risk_hedge_overlay` actions and only materializes them after residual post-approval exposure is known.

The final morning output is not just a ranked list. It is a trade plan: selected ticker, selected strategy, horizon, action, target exposure, risk budget used, and explicit reason if a high-scoring candidate was skipped.

### Manual Ticker Review / Pinned Review

Users can manually pin tickers that were not selected by the scanner and ask the trading bot to evaluate whether they are tradable. This is a forced-evaluation path, not a trade override path.

Manual review supports two modes:

| Mode | Meaning | Trading Impact |
| --- | --- | --- |
| `review_only` | Fetch data, compute signals, classify, and explain whether the ticker is actionable | Never creates paper orders. |
| `paper_trade_eligible` | Run the same evaluation as `review_only`, then allow a paper order only if strategy, confidence, sizing, and risk gates all pass | Can create paper orders, but only through normal `TradingPipeline`, `PositionSizer`, and `RiskManager`. |

Manual request flow:

```text
User pins ticker + reason + mode
      |
      v
manual_ticker_requests
      |
      v
ManualTickerReviewPipeline validates ticker and data availability
      |
      v
SignalPipeline computes same signal snapshot schema
      |
      v
StrategyPipeline scores against the same strategy catalog
      |
      v
PrimaryStrategySelector chooses either `selected_trades` or explicit `watch_candidates`
      |
      v
TradeClassifier assigns portfolio-pool trade identity only for `selected_trades`
      |
      v
TradingPipeline returns trade / catalyst_watch / ordinary_watch / no_trade / blocked_by_risk
```

Manual review outputs should include:

- `selection_source`: `manual_request`
- `manual_request_id`
- user-entered `reason`
- `request_mode`: `review_only` or `paper_trade_eligible`
- `result_status`: `actionable_trade`, `catalyst_watch`, `ordinary_watch`, `no_trade`, `blocked_by_risk`, `blocked_by_missing_data`
- the same benchmark/peer, confidence, risk, and invalidator fields used for scanner-selected candidates

Manual tickers can bypass the scanner ranking threshold, but they cannot bypass:

- minimum data availability
- liquidity and tradability checks
- relative-strength and catalyst quality scoring
- bearish signal policy
- paper options required metadata
- leg-based option risk and assignment risk when relevant
- portfolio concentration limits

Manual ticker requests should stay active across trading days until the user dismisses them. They should be re-evaluated in each relevant pre-open run and intraday active-manual-request refresh. The default request should not expire at end of day.

Manual request outcomes are important reflection inputs. The system should later compare user-pinned tickers against bot-selected candidates to learn whether the scanner missed valid opportunities or correctly ignored weak ideas.

### Intraday Signal Refresh, News Scan, and Rebalance

During regular trading hours, the system runs an hourly intraday refresh. It should scan news and refresh all signal families that can materially change intraday for portfolio-relevant tickers. The initial scope should include:

- open paper positions
- tickers with open/pending paper order audit rows or same-day trades
- top active candidates from the morning scan
- active manual/pinned review tickers
- high-impact market/sector news from the provider feed

If provider limits allow, the scan can also query broader universe signals/news, but the first production path should prioritize portfolio-relevant names so it can react quickly without excessive API usage.

Hourly refresh starts with a freshness plan rather than a full rerun of all source pipelines:

1. Determine the intraday scope: open positions, same-day trades, open/pending paper order audit rows, top morning candidates, manual requests, option positions, and critical/high event exposures.
2. Load each ticker's pre-open baseline `signal_snapshot_id` and previous intraday snapshot if available.
3. Evaluate source freshness requirements by source family and ticker/event scope.
4. Run required inline refreshes within a time budget: market price/volume, intraday relative strength, latest scoped news/events, and open option marks.
5. Run targeted on-demand refreshes only when relevant: SEC filings for positions/candidates, own earnings transcript when expected/reported, peer read-through for mapped relationships.
6. Carry forward low-frequency baseline fields when the source is still inside its freshness SLA.
7. Persist explicit `fresh`, `stale`, `missing`, `failed`, or `not_required` source status for every signal family used in the intraday snapshot.

Hourly refresh should update:

- intraday price/volume/liquidity signals: VWAP hold/reclaim, opening range break, relative volume, spread proxy, gap fade/fill, intraday range, ATR-relative move
- relative strength signals: ticker vs `SPY`, `QQQ`, sector/theme ETF, and peer basket since open and since prior close
- option signals for open paper option positions and eligible candidates: per-leg mark, Greeks, IV move if available, DTE, breakeven distance, max loss, spread width, margin requirement, buying-power effect, and assignment-risk delta when short options are present
- news/event signals: new company news, target-company earnings releases/transcripts/guidance, analyst revisions, filings, direct negative catalyst flags, high-impact market/sector news, and peer/sector-leader earnings read-through updates
- low-frequency source freshness: insider/SEC/fundamentals/earnings-calendar records should be checked for newly available rows or staleness, not blindly recomputed from scratch each hour

Each hourly run stores an `intraday_signal_snapshot` with signal deltas vs the morning snapshot and previous intraday snapshot. Rebalance should trigger from material signal changes even when no new headline exists. Intraday refresh should not recompute the full morning candidate ranking by default; it should preserve the morning score and add current state, material-change flags, and rebalance reasons.

Each scan also produces normalized `news_alerts` when new events are detected:

```json
{
  "ticker": "ASAN",
  "alert_type": "earnings_beat_raise",
  "sentiment": "positive",
  "severity": "high",
  "source": "benzinga",
  "published_at": "2026-05-29T11:28:00-04:00",
  "title": "Asana shares higher after better-than-expected results and raised guidance",
  "summary": "Beat-and-raise guidance is a strong positive catalyst.",
  "strategy_relevance": ["earnings_drift_v1", "gap_and_go_v1"],
  "affected_positions": ["position_uuid"],
  "dedupe_key": "ASAN|earnings_beat_raise|2026-05-29T11:28",
  "action_required": true
}
```

Severity rules:

- `critical`: event directly invalidates an open position thesis or creates immediate gap/liquidity risk.
- `high`: material positive/negative company event likely to affect current position or top candidate.
- `medium`: relevant but not enough to force immediate action.
- `low`: store for context only.

Allowed intraday rebalance actions:

- `hold`: alert acknowledged, no order.
- `reduce`: cut exposure because risk/thesis changed.
- `exit`: close position because invalidator triggered.
- `add`: increase exposure only if positive news confirms the active strategy, risk budget remains available, and factor concentration stays within limits.
- `open_new`: disabled by default for V2 unless the alert is critical/high and the ticker was already a morning candidate or approved override.
- `close_option_strategy`: close paper option strategy because thesis, event risk, option risk, or assignment risk changed.
- `roll_option_strategy`: roll one or more option legs only if the replacement structure improves risk and still passes leg-based option checks.
- `adjust_option_strategy`: add/remove/resize legs when it improves the risk profile and remains within max-loss/Greeks/margin/buying-power requirements.
- `avoid_event_option`: block any new, rolled, or adjusted option strategy when event risk is not explicitly acceptable.

Intraday rebalance is still gated:

1. `HourlySignalRefreshPipeline` refreshes intraday signal snapshots, computes deltas, dedupes news/events, and classifies alerts.
2. `IntradayRebalancePipeline` proposes action with signal/news evidence and urgency.
3. `PositionSizer` recalculates target size.
4. `RiskManager` applies factor exposure and concentration limits.
5. `PaperStockBroker` submits approved stock paper orders to Alpaca paper trading; the option broker simulates approved whitelisted option orders until a broker-backed option path is explicitly designed.

This loop must persist rejected and no-action alerts. They are important for reflection: the system should learn whether it ignored useful news, overreacted to noise, or correctly protected the portfolio.

## 9. Trading Decision Contract

The trading agent receives:

- selected candidates with full signal snapshots, candidate score context, primary strategy, expression bucket, and portfolio-pool trade identity
- manual request context for user-pinned tickers, including mode, reason, and source
- macro snapshot/regime
- current unified paper margin account and open stock/option positions
- risk config
- active risk-tightening or validated learning factors relevant to strategy/ticker/sector/regime, plus non-behavior-changing candidate/observation lessons as labeled soft context
- recent trade outcomes for the same strategy or ticker

It returns one JSON object per candidate or position:

```json
{
  "ticker": "AAPL",
  "decision": "enter_long",
  "strategy_id": "strong_theme_catalyst_continuation_v1",
  "expression_bucket_id": "long_stock",
  "trade_identity": "tactical_stock_trade",
  "instrument_type": "stock",
  "selection_source": "scanner",
  "manual_request_id": null,
  "confidence": 0.72,
  "confidence_basis": {
    "calibration_bucket": "bullish_catalyst_relative_strength",
    "historical_win_rate": 0.58,
    "historical_alpha_vs_peer_basket": 0.012
  },
  "benchmark_context": {
    "primary_benchmark": "QQQ",
    "sector_or_theme_benchmark": "SMH",
    "peer_basket_id": "semis_ai_large_mid_2026_05_29"
  },
  "target_weight": 0.05,
  "max_loss_pct": 0.025,
  "time_horizon": "2w-3m",
  "entry_plan": "market_open",
  "exit_plan": "close_or_invalidator",
  "thesis": "Strong relative momentum with confirming volume under neutral macro regime.",
  "key_signals": ["sector_relative_strength", "relative_volume", "trend_slope"],
  "risk_checks": ["liquidity_ok", "macro_budget_ok", "position_limit_ok"],
  "invalidators": ["SPY breaks below prior close by more than 1%", "relative volume fades below 0.8x"],
  "learning_factors_used": ["lf_2026_05_01_momentum_chasing_filter"]
}
```

Allowed decisions:

- `enter_long`
- `enter_short` (optional; disabled by default, and never allowed from macro-only bearish evidence)
- `hold`
- `reduce`
- `exit`
- `no_trade`
- `open_option_strategy`
- `close_option_strategy`
- `roll_option_strategy`
- `adjust_option_strategy`
- `avoid_event_option`

Risk checks run before order creation. If risk checks fail, no paper order is created even if the LLM decision is actionable.

Risk hedge actions are not returned by `TradingPipeline`. If portfolio-level risk needs an option hedge, `RiskManager` generates `open_hedge`, `close_hedge`, or `adjust_hedge` under `trade_identity = "risk_hedge_overlay"` and sends approved paper-only hedge orders through the option simulation layer.

For option decisions, the trading decision must include a leg-based `option_plan` object with `option_strategy_type`, all legs, net debit/credit, Greeks, max loss, max profit where definable, breakevens, margin requirement, buying-power effect, earnings/event dates, roll/close/adjust conditions, and assignment plan when relevant. Missing option-chain data should produce `no_trade` or `catalyst_watch`, not a fabricated option plan.

`time_horizon` should come from the selected strategy definition, not from a global default. The trading agent may shorten or skip a trade if risk conditions conflict with the strategy horizon, but it should not silently rewrite the strategy's typical horizon without recording a reason.

Confidence must be calibrated by historical pattern quality. Bullish catalyst plus relative strength can earn high confidence when past evidence supports it. Macro-only bearish, valuation-only bearish, RSI-only bearish, or “stock is extended” reasoning must remain low confidence and should normally map to risk warning, smaller size, no trade, or watch.

### LLM Output Validation and Safe Fallback

Every LLM output that can affect trading state must pass Pydantic validation before any downstream write or state transition. This applies to:

- trading decisions
- intraday news/event classifications when they can trigger a rebalance proposal
- intraday rebalance decisions
- reflection JSON
- learning factor extraction
- strategy proposal synthesis

The orchestrator owns the retry and fallback policy:

1. Render prompt with a versioned schema id/version.
2. Call the model and persist raw output.
3. Parse and validate through the matching Pydantic schema.
4. If validation fails, retry with the validation error and a compact repair prompt.
5. If retry still fails, persist the failure and return a safe fallback.

Safe fallbacks:

| Pipeline | Fallback |
| --- | --- |
| Trading decision | `no_trade` for new exposure; `hold` or deterministic risk-manager action for existing positions |
| Intraday classification | `classification_failed`, no rebalance trigger unless deterministic hard-risk rules fire |
| Intraday rebalance | `hold` or deterministic reduce/exit if hard risk rails require it |
| Reflection | `reflection_failed`; do not create or mutate learning factors |
| Learning factor extraction | persist observation text only, no active factor |
| Strategy proposal synthesis | `proposal_failed`; do not create strategy definitions |

Validated parsed output, raw output, validation errors, retry count, fallback action, schema id/version, and prompt id/version must be persisted for audit. A parse error must never mutate portfolio state, strategy definitions, or learning factors.

### Risk Constraint and Budget Decision

The final action is computed in two stages:

1. `TradingPipeline` proposes `decision`, `suggested_target_weight`, `time_horizon`, instrument expression, thesis, and invalidators.
2. `RiskManager` applies deterministic constraints and returns `approved`, `reduced`, or `rejected`.

`RiskManager` should consume an explicit `PortfolioContext` / `RiskContext` object rather than directly depending on `PaperStockBroker` internals. The context contains account equity, cash, buying power, existing positions, current exposure, margin requirement, factor exposure, open strategy exposure, and latest portfolio/risk snapshots when available. This lets the risk manager be tested with fixtures and lets `PortfolioPipeline` map Alpaca paper account/position sync results into the same contract without rewriting risk logic.

Risk decision fields:

- `account_equity`
- `cash_balance`
- `buying_power_before` and `buying_power_after`
- `excess_liquidity_before` and `excess_liquidity_after`
- `total_margin_requirement_before` and `total_margin_requirement_after`
- `stock_margin_requirement_before` and `stock_margin_requirement_after`
- `option_margin_requirement_before` and `option_margin_requirement_after`
- `gross_exposure_before` and `gross_exposure_after`
- `strategy_budget_remaining`
- `macro_budget_multiplier`
- `factor_exposure_before` and `factor_exposure_after`
- `worst_case_assigned_exposure_before` and `worst_case_assigned_exposure_after`
- `remaining_factor_budget_by_type`
- `binding_factor_limits`
- `option_assignment_notional`
- `margin_requirement`
- `risk_appetite`
- `effective_risk_config_id`
- `risk_config_resolver_version`
- `margin_model_profile`
- `margin_model_version`
- `margin_requirement_source`: `simulated_formula`, `broker_observed`, or `manual_override`
- `estimated_initial_margin_requirement` and `estimated_maintenance_margin_requirement`
- `broker_reported_margin_requirement` when imported from a broker or broker calculator
- `house_requirement_pct`, `reg_t_requirement_pct`, and conservative add-ons when applicable
- `strategy_pairing_method` for multi-leg options when margin depends on paired legs
- `buying_power_effect`
- `position_limit_check`
- `liquidity_check`
- `stale_signal_check`
- `learning_factor_adjustments`
- `final_action`: `create_order`, `reduce_size_create_order`, or `reject`
- `risk_rejection_reason`
