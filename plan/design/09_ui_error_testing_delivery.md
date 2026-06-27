# Design Module 09: UI, Error Handling, Testing, and Delivery

## 13. UI Design

Default page should become a tabbed daily trading workstation instead of a research run list. The UI should optimize for repeated operating workflows: check current exposure, inspect today’s decisions, understand risk, review skipped candidates, and audit learning/cost.

### Primary Navigation

- `Today` / Trading Workstation
- `Portfolio`
- `Trades`
- `Candidates`
- `Strategies`
- `Reflections`
- `Ops & Cost`
- `Research`
- `Watchlist` or `Overrides`

### `/today`

The `/today` page should be the main workstation with top-level tabs. Above the tabs, show a compact status header:

- trade date and job status timeline
- current NAV, day PnL, benchmark return, gross exposure, cash balance, buying power, margin used, and excess liquidity
- critical/high alerts and material signal-change count
- macro regime, clearly labeled as macro-only
- risk budget, factor exposure usage, and blocked strategy tags
- current LLM/API cost estimate for the day

Tabs:

1. `Overview`
   - Compact operator summary: NAV, day PnL, cash balance, buying power, margin used, excess liquidity, gross/net exposure, risk budget used, critical alerts, material signal changes, open action items, and job status.
   - This tab should answer: “Do I need to pay attention right now?”

2. `Portfolio`
   - Current stock positions, paper option strategies/legs, core vs tactical pools, hedge overlays, unified margin-account state, exposure, unrealized/realized PnL.
   - Include trade identity, selected strategy, holding age, invalidator status, current risk tags, option Greeks/max loss/margin requirement/buying-power effect, and worst-case assigned exposure for assignment-capable option strategies.

3. `Trades`
   - Every same-day trade decision, including executed trades, rejected trades, reductions, exits, whitelisted option strategy opens/closes/rolls/adjustments, and no-trade decisions that reached `TradingPipeline`.
   - Each row shows time, ticker, action, instrument, trade identity, selected strategy, expression bucket, proposed size, final size, fill/order status, confidence, and reject/reduction reason.
   - Every trade row must open a detail view with the complete audit trail:
     - multi-source signal snapshot
     - intraday signal deltas if relevant
     - multi-strategy candidate scores
     - selected primary strategy and expression bucket
     - trade identity and instrument plan
     - LLM decision JSON and prompt/schema version
     - confidence basis and calibration bucket
     - risk manager approval/reduction/rejection details
     - paper order/fill state
     - exit plan and invalidators
     - post-close outcome once available

4. `Risk & Macro`
   - Macro regime, macro risk budget multiplier, blocked strategy tags, macro invalidators, and economic-calendar risk.
   - Active risk appetite preset, generated risk config version, and binding constraints, with detailed generated limits hidden behind an advanced/debug view.
   - Upcoming portfolio-relevant events: macro releases, Fed/rates events, own-company earnings, related-company earnings read-through, option expiry/event-through-expiry risks, and market-structure events.
   - Each event row shows date/time, event type, importance, portfolio risk level, affected ticker/position/option strategy, affected sector/theme, risk mechanism, lookahead reason, and suggested action type.
   - Hide low-importance events by default when they do not map to current holdings, top candidates, manual review tickers, option expiries, or concentrated sector/theme exposures.
   - The event lookahead window is dynamic: it extends through each position's intended holding period or option expiry, and farther for high/critical macro or core-holding events.
   - Portfolio risk exposures by sector/industry, theme, strategy, horizon, direction, beta, volatility, liquidity, event/catalyst type, macro sensitivity, and correlation cluster.
   - Paper options risk view: show option strategies, legs, Greeks, max loss, margin requirement, buying-power effect, hedge overlays, and assignment view for assignment-capable short option legs.
   - Show binding limits and which proposed trades were reduced or rejected by each limit.

5. `Candidates`
   - Active universe filter controls: min price, min average dollar volume, included/excluded sectors or industries, exchange/asset eligibility, and manual include/exclude ticker overrides.
   - Bot-selected candidates that were not traded, manually pinned tickers, `catalyst_watch`, and `ordinary_watch`.
   - Split scanner-selected from manual-only candidates.
   - Manual ticker requests stay active until dismissed; show a dismiss action and latest evaluation timestamp/result.
   - Show why skipped: missing/stale data, no catalyst, weak relative strength, poor price/volume confirmation, macro size reduction, risk block, `review_only` mode, or options metadata missing.
   - Each candidate should be drillable to the same signal/strategy/risk context used by the trade detail view, even when no order was created.

6. `Learning & Strategies`
   - Learning factors, active/suppressed/retired status, source reflection, scope, confidence, and whether they tightened candidate scoring or risk.
   - Strategy catalog with lifecycle: active, shadow, experimental, retired.
   - Strategy performance table:
     - trade count and sample size
     - win rate
     - total PnL and average PnL
     - average alpha vs `SPY`, `QQQ`, sector/theme ETF, and peer basket where available, measured over each strategy's configured holding horizon
     - max drawdown
     - performance by market regime
     - bullish vs bearish split
     - common rejection/invalidator patterns

7. `Ops & Cost`
   - LLM/API usage by pipeline, model, run, and trade date.
   - Show prompt tokens, completion tokens, total tokens, estimated cost, latency, retry count, errors, model name, prompt/schema version, and provider.
   - Include market/news/options provider usage where available so API rate-limit and cost issues are visible.
   - This is operational telemetry, not trading learning; keep it separate from `Learning & Strategies`.

The old section-level dashboard cards should become tab contents:

- Live alerts and material signal changes appear in `Overview`, with drill-down links into `Trades`, `Candidates`, or `Risk & Macro`.
- Current positions, paper option strategies, option legs, and hedge overlays appear in `Portfolio`.
- Today's trades and complete trade audit trails appear in `Trades`.
- Candidate scanner and pinned review appear in `Candidates`.
- Risk exposure and macro regime appear in `Risk & Macro`.
- Post-close reflection, learning factors, and strategy evolution appear in `Learning & Strategies`.
- LLM/API usage and costs appear in `Ops & Cost`.

### `/macro`

Macro page should be separate from stock pages:

- macro indicators and observation dates
- market regime history
- economic calendar events
- macro risk budget history
- strategy tags affected by macro

### `/research`

Keep the current research run UI for drill-down and audit, but make it secondary. Research details can link to the trading decision that used them, if any.

## 14. Error Handling and Replayability

- Every pipeline run stores `started_at`, `finished_at`, `status`, and `error_message`.
- Every source record and signal snapshot stores `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at` where applicable; decisions may only use rows whose availability time is at or before the decision timestamp.
- Replay, backtest, reflection, and strategy evolution must load decision-time snapshots instead of latest source rows.
- Missing provider data should degrade the relevant signal to missing, not fabricate values.
- Provider adapters must enforce rate limits, cache/freshness gates, request budgets, exponential backoff, and circuit breakers; provider outages should enter degraded mode instead of blocking unrelated source families.
- Candidate scoring skips tickers without minimum required signals.
- Candidate scoring must separate `ordinary_watch` from `catalyst_watch` as a watch type under `trade_identity = "watch_only"` so high-volatility catalyst opportunities are not lost in neutral output.
- Manual ticker requests that fail ticker validation, data availability, or liquidity checks should return `blocked_by_missing_data` or `no_trade`; they should not create partial fabricated snapshots.
- Active manual ticker requests should continue to be evaluated until dismissed by the user; dismissal should stop future scheduled evaluations but preserve historical results.
- `review_only` manual requests must never create paper orders even when the trading decision is actionable.
- Strategy proposals must not mutate active strategy definitions directly. They create candidate/shadow strategy definitions through explicit lifecycle transitions.
- Macro-only bearish context must not create single-name bearish trades; if it affects a candidate, the persisted decision should show risk-budget reduction or no-trade reason.
- Option decisions with missing option-chain, leg pricing, Greeks, earnings/event date, max-loss/margin-requirement/buying-power, or assignment-risk inputs where relevant must be rejected or downgraded to watch.
- Intraday signal snapshots must preserve deltas vs the morning signal snapshot and previous hourly snapshot.
- News alerts must be deduped by ticker/event/source/time window so repeated headlines do not trigger repeated rebalances.
- Intraday rebalance decisions must persist the triggering `news_alert_id`, proposed action, final action, and risk decision.
- Trading decisions must persist full context snapshots: candidate signals, macro snapshot id, portfolio snapshot id, risk config version, strategy version, decision timestamp, source availability metadata, and learning factors used.
- Option decisions must persist full option strategy metadata, per-leg metadata, option-risk snapshot, and assignment-risk snapshot where relevant.
- Paper orders must be idempotent per `trade_date + ticker + strategy_id + decision_type`.
- A failed ticker must not abort the whole universe scan.
- Invalid LLM JSON, Pydantic validation failure, or schema drift must trigger bounded retry and then safe fallback; failed parsing must not mutate portfolio state, strategy definitions, or learning factors.
- Reflection failure must not mutate learning factors.
- Intraday signal/news refresh failure must not block portfolio marking or post-close reflection.

## 15. Testing and Smoke Tests

Testing must be deterministic by default:

- Unit tests use fake providers and fixture source rows. They must not hit live market/news/LLM APIs.
- Integration tests that exercise provider adapters use `vcrpy` cassettes or equivalent recorded fixtures.
- Live API smoke tests are separate, opt-in, tiny-scope, and must not block ordinary CI.
- Historical replay tests should run offline from fixture snapshots and verify that future source rows are excluded by `available_for_decision_at`.

Unit tests:

- signal computations
- point-in-time/no-lookahead availability filtering
- provider rate limit, backoff, circuit breaker, cache/freshness gate, and degraded-mode behavior
- universe filters
- portfolio intent loading and core-holding eligibility
- ticker relationship graph, peer basket construction, and theme taxonomy lookups
- manual ticker request validation, dismissal, active-request loading, mode handling, and source attribution
- macro regime classification
- strategy candidate scoring
- trade identity classification
- relative-strength benchmark and peer-basket attribution
- confidence calibration by strategy, expression bucket, trade identity, and direction
- bearish signal gating so macro-only bearish evidence cannot create a single-name short
- risk checks
- paper option strategy decision validation
- leg-based option risk and assignment exposure calculation
- news alert dedupe and severity classification
- intraday signal delta detection and material-change thresholds
- intraday rebalance action gating
- factor exposure calculation
- concentration limit enforcement
- position sizing and size-reduction reasons
- paper order state transitions
- portfolio PnL calculations
- historical replay and outcome evaluator horizon attribution
- LLM Pydantic validation, retry, and safe fallback behavior
- learning factor activation rules
- strategy proposal validation and duplicate detection
- strategy lifecycle transition rules
- web route rendering for today/trades/reflections

Smoke tests:

- standalone market data smoke for universe + signal computation
- standalone smoke for a tiny manual ticker request in `review_only` mode
- standalone intraday signal/news refresh smoke for a tiny fixed ticker set or fixture mode
- standalone historical replay smoke from fixed fixture snapshots
- standalone DB smoke for writing signal/candidate/order/portfolio rows
- standalone DB smoke for writing portfolio risk snapshots and risk factor exposures
- standalone DB smoke for writing paper option decisions, option legs, strategy-level option risk, and assignment-risk snapshots
- optional live provider/API smoke tests for market/news/options providers using tiny ticker sets, request budgets, and explicit opt-in flags
- optional live paper-trade dry run that uses a tiny ticker set and does not consume large API quota

Implementation must continue to use `source ~/.venv/bin/activate` before Python commands and must verify Postgres data directory is on persistent disk for deployment work.

## 16. Phased Delivery

### Phase 1: Verifiable Signal and Replay MVP

- Add data model for universe, point-in-time source records, signals, macro snapshots, strategy definitions, candidate scores, portfolio intents, relationships, and outcome evaluation.
- Add provider resilience wrappers, fake-provider test adapters, and source availability metadata.
- Implement user-editable liquidity/sector universe filters, universe refresh, and deterministic signal snapshots.
- Add manual ticker request ingestion, dismissal handling, and pinned-review signal snapshots.
- Seed the initial strategy catalog with tactical strategies plus strategy expression buckets.
- Add trade identity taxonomy and confidence-calibration fields.
- Add core-holding eligibility from `portfolio_intents`.
- Add peer/theme relationship graph for read-through and benchmark attribution.
- Add strategy matching and candidate scoring.
- Add historical replay/outcome evaluator before paper trading.

### Phase 2: Paper Stock Trading

- Add trading decisions, paper orders, executions, positions, portfolio snapshots.
- Implement Pydantic-validated LLM output, retry, and safe fallback.
- Implement position sizing, risk checks, factor exposure caps, budget allocation, and paper stock broker.
- Replace homepage with a minimal `/today` candidate/trade dashboard.

### Phase 3: Paper Options and Assignment Risk

- Add paper/simulation-only option strategy decisions, option legs, paper option positions, and lifecycle state for single-leg and multi-leg option strategies.
- Evaluate leg-based option risk for every option strategy, and current plus worst-case assigned portfolio before approving assignment-capable short-option structures.
- Extend `/today` with option risk, legs, and assignment-risk views.

### Phase 4: Intraday Signal Refresh, News Alerts, and Rebalance

- Add hourly intraday signal scan metadata, intraday signal snapshots, and normalized alert tables.
- Refresh intraday price/volume/relative-strength/options/news signals for open positions, top candidates, and pinned review tickers.
- Classify positive/negative high-impact events for open positions and top candidates.
- Trigger intraday rebalance proposals for material signal changes or critical/high alerts.
- Gate every alert-driven action through `PositionSizer`, `RiskManager`, and `PaperStockBroker` / option paper broker.
- Persist no-action/rejected alerts for post-close reflection.

### Phase 5: Reflection

- Add post-close reflection agent and `daily_reflections`.
- Generate learning factors with lifecycle statuses.
- Reflect on benchmark/peer-basket outperformance, bullish vs bearish signal quality, and confidence calibration.
- Reflect on paper option outcomes, leg-based option risk decisions, hedge overlay effectiveness, and assignment-risk decisions.
- Show reflection and learning factors in UI.

### Phase 6: Learning Injection

- Inject only active, validated or risk-tightening learning factors into `TradingPipeline`.
- Keep candidate/observation learning factors as soft context only.
- Persist learning factor applications.
- Evaluate whether factors improved strategy outcomes.

### Phase 7: Strategy Evolution

- Generate new strategy proposals from repeated reflection/learning patterns.
- Add candidate/shadow strategy lifecycle states.
- Run shadow strategies during scans without allowing them to place paper orders.
- Promote strategies to experimental/active only when evidence and risk checks pass.
- Show strategy proposals and lifecycle status in UI.

### Phase 8: Strategy Expansion

- Add more strategy definitions and signal groups.
- Add macro-aware strategy blocking and risk-budget adjustment.
- Add richer attribution across ticker, strategy, sector, and macro regime.
- Add richer operational telemetry for LLM/API usage and provider costs if the basic `Ops & Cost` tab shows recurring bottlenecks.

## 17. Acceptance Criteria

1. A scheduled run can scan a configured US common-stock universe using user-editable liquidity and sector filters without relying on watchlist entries.
2. The system stores point-in-time replayable quant signal snapshots for every scanned candidate, including source refs, decision timestamp, and `available_for_decision_at` audit fields.
3. Provider access uses rate limits, cache/freshness gates, request budgets, backoff, circuit breakers, and degraded mode.
4. A user can pin a ticker for `review_only` or `paper_trade_eligible` manual evaluation even if the scanner did not select it.
5. Manual ticker review uses the same signal snapshot, strategy matching, trade classification, confidence calibration, and risk path as scanner candidates.
6. `review_only` manual requests never create paper orders, and `paper_trade_eligible` requests only create paper orders after normal risk checks pass.
7. Macro snapshot/regime is stored separately from stock strategy inputs.
8. Core-holding classification requires an approved `portfolio_intent`; the bot does not infer core holdings from current positions or LLM preference.
9. Peer/theme read-through and peer-basket attribution use structured `ticker_relationships`, `peer_baskets`, and `theme_taxonomy`.
10. Strategy pipeline evaluates the initial strategy catalog and stores strategy-specific candidate score, evidence, invalidators, and strategy-determined holding horizon.
11. Historical replay/outcome evaluator measures trades, rejected candidates, watch items, and shadow strategies over each strategy horizon against `SPY`, `QQQ`, sector/theme ETF, and decision-time peer basket.
12. The morning trade plan selects ticker, strategy, expression bucket, trade identity, horizon, action, target exposure, and risk budget used before the market opens.
13. Paper execution creates stock paper orders only after Pydantic-validated LLM output, retry/fallback handling, risk checks, and budget allocation pass; `TradingPipeline` itself persists decisions, not broker side effects.
14. Position sizing records base size, volatility adjustment, liquidity cap, remaining factor budget, final size, and binding constraints.
15. Portfolio risk snapshots show factor exposure by sector, strategy, horizon, beta, volatility, liquidity, event type, macro sensitivity, correlation cluster, leg-based option risk, and assignment exposure where relevant.
16. Risk manager reduces or rejects trades that would make current portfolio risk, option strategy risk, or worst-case assigned portfolio too concentrated in any configured risk factor.
17. Paper portfolio shows broker-synced stock positions, trades, exposure, and day PnL.
18. Paper options layer is initially limited to `long_call`, `long_put`, `put_credit_spread`, `call_credit_spread`, `long_straddle`, and `long_strangle`, and records generic `open_option_strategy`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy`, and `avoid_event_option` actions with strategy type, per-leg call/put side, strike, expiry, DTE, Greeks, IV rank, price, net debit/credit, max loss, breakevens, margin requirement, buying-power effect, event dates, and assignment data when relevant.
19. Macro-only bearish context cannot create high-confidence single-name bearish trades; it can only reduce size, block strategy tags, or add risk warnings unless direct company-level negative evidence exists.
20. Confidence displays and persistence distinguish historically strong bullish catalyst patterns from weak bearish/macro narratives.
21. Watch output distinguishes `ordinary_watch` from `catalyst_watch` as `watch_type` under `trade_identity = "watch_only"`.
22. Hourly intraday refresh creates signal snapshots, material signal-change deltas, and deduped positive/negative alerts for open positions, same-day trades, top candidates, active manual review tickers, and high-impact market/sector events.
23. Critical/high alerts can trigger immediate risk-gated `hold/reduce/exit/add` rebalance decisions, with `open_new` disabled by default unless the ticker was already a morning candidate or override.
24. Post-close reflection analyzes portfolio returns, replay outcome rows, benchmark/peer-basket returns, selected trades, rejected candidates, manual ticker requests, intraday alerts, rebalance outcomes, macro constraints, factor concentration, paper option decisions, confidence calibration, and learning-factor impact.
25. Strategy evolution can create new strategy proposals from repeated learning patterns without being limited to the initial seed strategies.
26. New strategies enter `candidate` or `shadow` status first, and cannot create paper orders until promoted to `experimental` or `active`.
27. New learning factors default to `candidate` or `observation`; only risk-tightening factors may become automatically active, and expansionary factors require shadow/test evidence before promotion.
28. Unit tests run against fake providers/brokers, integration tests use recorded cassettes, and live provider or Alpaca paper smoke tests are opt-in and non-blocking for ordinary CI.
29. `/today` is a tabbed trading workstation with `Overview`, `Portfolio`, `Trades`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, and `Ops & Cost` tabs.
30. Trade detail views show complete audit trails: signal snapshots, strategy scores, selected strategy, trade identity, LLM decision JSON, risk decision, order/fill state, exit plan, invalidators, and post-close outcome.
31. `Ops & Cost` shows LLM/API usage, model/provider, tokens, estimated cost, latency, retry/error state, validation/fallback state, prompt/schema version, and provider request budget/circuit-breaker state by pipeline and run.
32. Existing research run audit pages continue to work.

## 18. Resolved Design Decisions

1. Universe scope: use a user-editable US common-stock universe with liquidity filters and sector/industry include/exclude filters. Do not scan every listed name by default.
2. Common-stock paper trading is long-only in V2. Do not add direct short-stock paper trades behind a flag.
3. Alpaca paper trading is the PR 6 stock execution/account source of truth; local paper stock tables are audit/reconciliation mirrors, not an independent live stock ledger.
4. Holding period is determined automatically by the selected trading strategy definition. There is no global intraday-only or swing-only horizon.
5. New learning factors default to `candidate` or `observation`; only risk-tightening factors may become automatically active, while expansionary changes must be represented as strategy/config proposals or promoted after shadow/test evidence.
6. Manual ticker requests stay active until manually dismissed. They do not expire at end of day by default.
7. The first verifiable MVP is universe -> point-in-time signal snapshot -> strategy scoring -> historical replay/outcome evaluator; paper trading, options, intraday, reflection, and strategy evolution follow after that edge-validation path exists.
