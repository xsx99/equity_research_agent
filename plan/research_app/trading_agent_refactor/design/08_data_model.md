# Design Module 08: Data Model

## 12. Data Model Additions

Proposed new tables:

| Table | Purpose |
| --- | --- |
| `source_ingestion_runs` | Audit metadata for scheduled/targeted source refreshes: source family, run type, scope, provider, coverage, as-of time, status, latency, and error metadata |
| `provider_request_runs` | Per-provider request budget, cache/freshness gate, rate-limit, retry/backoff, circuit-breaker, degraded-mode, latency, and error metadata |
| `universe_filter_configs` | User-editable active universe filter profile, including liquidity thresholds, sector/industry include/exclude lists, exchange/asset filters, manual include/exclude overrides, version, and active flag |
| `universe_snapshots` | One row per daily universe refresh |
| `universe_symbols` | Symbols included/excluded in a universe snapshot with reason |
| `manual_ticker_requests` | User-pinned tickers that must be evaluated until dismissed, including reason, mode, status, last evaluation metadata, and linked result |
| `portfolio_intents` | User-approved core holding and portfolio-intent config: approved ticker/ETF, target/max weight, add/trim rules, thesis invalidators, allowed tactical interactions, lifecycle status |
| `ticker_relationships` | Directed source ticker to target ticker relationships such as peer, customer, supplier, competitor, sector leader, ETF/component, theme leader, or theme constituent, with source/confidence/validity metadata |
| `peer_baskets` | Versioned decision-time peer baskets used for relative strength, attribution, and outcome evaluation |
| `theme_taxonomy` | User-maintained theme hierarchy used for read-through, risk exposure, peer basket construction, and UI grouping |
| `fundamental_snapshots` | Point-in-time fundamental and valuation source rows with ticker, period/as-of metadata, provider/source refs, normalized metrics JSON, raw payload reference, and availability timestamps |
| `event_news_items` | Point-in-time headline, calendar, and provider-event rows with event type, optional source ticker, sentiment/direction, importance, dedupe key, provider/source refs, raw payload reference, and availability timestamps |
| `social_macro_items` | Point-in-time normalized social/policy rows derived from global context, with category, sentiment/direction, importance score, mention metadata, dedupe key, provider/source refs, and availability timestamps |
| `macro_snapshots` | One macro snapshot/regime per run/day |
| `macro_readthrough_events` | Structured peer/sector-leader earnings read-through events with source ticker, scope, mechanism, direction, affected theme/relationship, transcript/release provenance, and validity window |
| `calendar_events` | Normalized future macro, economic, Fed, earnings, market-structure, and option-relevant events with source/provider provenance, scheduled time, event type, global importance, affected ticker/theme metadata, and raw payload reference |
| `portfolio_event_risk_assessments` | Per event portfolio relevance and risk score: affected positions/candidates/options, sector/theme mapping, holding-period lookahead reason, risk mechanism, suggested action type, and hide/show decision |
| `signal_snapshots` | Per ticker per day pre-open baseline quant features and normalized signal JSON, including source freshness, missing/stale fields, `snapshot_type`, `decision_time`, `source_record_refs`, `available_for_decision_at`, and no-lookahead audit fields |
| `strategy_definitions` | Versioned strategy metadata, required signals, horizon, scoring config, invalidators |
| `strategy_proposals` | Proposed new strategies or revisions derived from reflection/learning, including lifecycle status and evidence |
| `strategy_evaluation_results` | Shadow/experimental performance and promotion/retirement evidence for strategy definitions |
| `strategy_runs` | One candidate-scoring batch per day |
| `candidate_scores` | Ranked ticker candidates by strategy, horizon, explicit `candidate_status`, evidence, and macro compatibility |
| `watch_candidates` | Retained non-trade outcomes linked to `candidate_scores`, including watch type, result status, watch reason, and selection context without any fake trade expression bucket |
| `trade_classifications` | Portfolio-pool trade identity, expression bucket, intended horizon, and exit-policy metadata for each trade-path candidate/position decision |
| `trading_decisions` | Trading agent decisions and context snapshot |
| `option_strategy_decisions` | Paper-only option strategy actions such as open/close/roll/adjust/avoid-event for whitelisted long call, long put, credit spread, long straddle, and long strangle strategies, with required strategy-level option metadata |
| `option_strategy_legs` | Per-leg option details for single-leg and multi-leg paper option strategies, including call/put, side, quantity, strike, expiry, Greeks, price, and liquidity fields |
| `risk_hedge_decisions` | Paper-only risk-manager hedge overlay decisions such as open/close/adjust hedge with risk-reduction rationale and hedge cost |
| `paper_option_orders` | Staged/submitted/filled/rejected simulated option orders |
| `paper_option_positions` | Current simulated option strategy and leg state, including calls, puts, spreads, multi-leg structures, and assignment-capable short options |
| `option_risk_snapshots` | Current leg-based option exposure, portfolio Greeks, max loss, margin requirement, buying-power effect, margin model profile/source, hedge overlay risk, and worst-case-assigned exposure snapshots when relevant |
| `intraday_signal_scans` | Hourly intraday refresh metadata, status, provider coverage, ticker scope, and error state |
| `intraday_signal_snapshots` | Per ticker intraday refreshed values, carried-forward baseline fields, source freshness status, and deltas vs pre-open baseline and previous intraday snapshot |
| `news_alerts` | Normalized positive/negative news alerts with severity, sentiment, dedupe key, affected tickers/positions |
| `intraday_rebalance_decisions` | Alert-driven hold/reduce/exit/add/open_new proposals and final risk-gated outcome |
| `risk_appetite_profiles` | User-facing risk preset selection such as `conservative`, `balanced`, or `aggressive`, with profile version and optional advanced override metadata |
| `risk_limit_configs` | Versioned generated risk limits and factor exposure caps produced by `RiskConfigResolver` from a risk appetite preset; persisted for audit/replay rather than edited as the primary UI config |
| `position_sizing_decisions` | Deterministic sizing inputs, applied caps, final target weight/quantity |
| `portfolio_risk_snapshots` | Portfolio-level gross/net exposure, active risk appetite, generated risk config id/version, unified margin-account risk, and factor exposures before/after proposed trades and after fills |
| `portfolio_risk_intents` | Persisted `PortfolioHedgePlanner` lookahead intent with aggregate risk state, position actions, hedge proposals, binding constraints, and optional linkage to the current risk snapshot |
| `risk_factor_exposures` | Normalized per-position and portfolio exposures by factor type/name |
| `paper_orders` | Staged/submitted/filled/rejected paper orders; stock rows mirror Alpaca paper broker state and include broker/client order identifiers |
| `paper_executions` | Broker-reported stock fills and simulated option fills when applicable |
| `paper_positions` | Current paper position state; PR 6 stock rows are synced from Alpaca paper positions |
| `portfolio_snapshots` | Unified paper margin account state: NAV/net liquidation value, account equity, cash balance, buying power, excess liquidity, margin requirements, margin model profile/source, exposure, and PnL; PR 6 stock account fields are synced from Alpaca paper account payloads |
| `historical_replay_runs` | Deterministic replay batches with decision-time filters, snapshot version, outcome horizon policy, and replay status |
| `candidate_outcome_evaluations` | Per candidate/trade/watch/strategy outcome rows with horizon, benchmarks, peer basket snapshot, alpha, MFE/MAE, regime, catalyst type, and interim/final status |
| `daily_reflections` | Post-close reflection JSON |
| `learning_factors` | Structured lessons with status/version/scope, defaulting to candidate/observation unless risk-tightening or explicitly promoted |
| `learning_factor_applications` | Join table showing which decision used which learning factor |
| `llm_usage_events` | Per LLM/API call telemetry: provider, model, pipeline, run id, token counts, estimated cost, latency, retry/error state, validation/fallback state, prompt/schema version |

Legacy tables are optional:

- `watchlists` becomes a manual override list, not the source of truth for daily scan.
- Manual watchlist/pinned symbols create `manual_ticker_requests`; they are evaluated through the same signal/strategy/risk path as scanner candidates.
- `research_runs` and `research_outputs` are not required in the V2 trading critical path. If they still provide useful UI explanation, audit, or legacy compatibility value, keep them as optional archival research artifacts. Otherwise they can be deprecated after migration.
- `eval_results` is not required for trade/portfolio scoring. If retained, it should only score research-output quality, prompt quality, or legacy evals. Strategy win rate, alpha, PnL, drawdown, option attribution, and portfolio risk outcomes should live in the paper trading and strategy evaluation tables.
- New V2 tables are the source of truth for trading behavior. Do not add compatibility writes to legacy research/eval tables unless a current UI or migration task explicitly needs them.

For PR 6 stock paper trading, Alpaca paper trading is the external execution/account source of truth. The local V2 tables remain the application audit and replay source: persist deterministic `client_order_id`, broker order id, broker status/reject reason, fill details from broker-reported filled state, and account/position snapshots from broker sync. Do not reconstruct live stock cash, buying power, or open stock quantity from a separate local simulated ledger when broker sync data is available.

### Strategy Definition Shape

`strategy_definitions.config_json` should be expressive enough to store the strategy catalog without code changes for every threshold tweak:

```json
{
  "strategy_id": "gap_and_go_v1",
  "display_name": "Gap-and-Go",
  "strategy_layer": "tactical_pattern",
  "typical_horizon": "intraday-3d",
  "core_thesis": "Overnight information continues as momentum.",
  "required_signals": ["opening_gap_pct", "vwap_hold", "opening_range_high_break", "relative_volume"],
  "optional_signals": ["fresh_catalyst_type", "sector_rank_percentile"],
  "risk_tags": ["gap_risk", "momentum"],
  "macro_blocked_regimes": ["stressed"],
  "lifecycle_status": "active",
  "source": "seed",
  "parent_strategy_id": null,
  "scoring_rules": {
    "min_opening_gap_pct": 0.02,
    "min_relative_volume": 1.5
  },
  "invalidators": ["loses VWAP", "fails opening range high", "relative volume fades"]
}
```

This keeps strategy identity, horizon, and signal requirements in data. Python strategy evaluators can still implement the scoring math, but the DB row is the audit source for what version was active on a given trade date.

Discovered strategies use the same `strategy_definitions` shape once promoted from proposal to catalog entry. They differ only by `source`, `lifecycle_status`, parent/revision metadata, and risk budget limits.

Strategy expression buckets use the same table with `strategy_layer = "expression_bucket"` and include fields such as `default_trade_identity`, `allowed_trade_identities`, `allowed_instruments`, `allowed_option_strategy_types`, `required_option_leg_fields`, `required_assignment_fields`, `earnings_policy`, and `default_exit_policy`. They should not duplicate portfolio-pool semantics or strategy thesis. Names such as `strong_theme_no_clear_near_term_sell_put` are intentionally avoided because they mix the alpha pattern with the instrument expression.

`candidate_scores` should also persist an explicit `candidate_status` such as `actionable`, `watch`, or `blocked` so the matcher contract distinguishes trade eligibility from retained non-trade outcomes before selection.
