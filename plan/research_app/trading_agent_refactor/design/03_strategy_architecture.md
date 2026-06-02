# Design Module 03: Strategy Architecture

## 6. Macro vs Stock Strategy Separation

Macro and stock strategy are separate namespaces and separate pipeline outputs.

### Macro Engine

Runs once per trading day before candidate scoring. It produces a market-level snapshot:

- `risk_regime`: `risk_on`, `neutral`, `risk_off`, `stressed`
- `volatility_regime`: `low`, `normal`, `elevated`, `extreme`
- `rates_regime`: `falling`, `stable`, `rising`, `inverted_pressure`
- `breadth_regime`: `broad_participation`, `narrow_leadership`, `weak_breadth`
- `macro_risk_budget_multiplier`: numeric multiplier such as `0.25`, `0.5`, `1.0`
- `blocked_strategy_tags`: e.g. block high beta long momentum during stressed risk-off sessions
- `macro_summary`: short text for UI and LLM context
- `macro_invalidators`: market-level conditions that should force risk reduction
- `sector_theme_readthrough`: structured macro/sector/theme context from peer, customer, supplier, competitor, or sector-leader earnings

Macro does not rank individual stocks. It can constrain risk, block strategy tags, reduce gross exposure, or annotate the day as unsuitable for certain strategies.

Peer and sector-leader earnings belong in this macro/sector/theme context, even though they are assembled by `SignalPipeline` as a source family. They are not direct target-company signals. A peer earnings read-through can affect theme risk budget, strategy eligibility, required confirmation, and risk notes, but it must not set a target ticker's `fresh_catalyst_type` or `direct_negative_catalyst_type` unless the target company itself produced the catalyst.

By contrast, the target company's own earnings release, guidance, earnings-call transcript, and post-earnings analyst revisions are ticker-level company signals. They belong in that ticker's `quant_signal_snapshot` and can set direct catalyst fields such as `fresh_catalyst_type = "own_earnings_beat_raise"` or `direct_negative_catalyst_type = "own_earnings_guide_down"` when the structured evidence supports it.

### Portfolio-Aware Event Calendar

Macro and earnings calendars should be normalized into a portfolio-aware event calendar rather than shown as a raw calendar feed. Source examples include economic calendars such as MarketWatch-style macro calendars and earnings calendars such as Nasdaq-style earnings calendars, but the implementation should use provider adapters and persist normalized rows before UI rendering.

Supported event types:

- macroeconomic releases: CPI, PCE, jobs, GDP, retail sales, ISM/PMI, claims, housing, consumer confidence
- Fed and rates events: FOMC, minutes, Chair/governor speeches, Treasury auctions when available
- market structure events: market holidays, index rebalances, major ETF/index changes when available
- own-company earnings: earnings date/time, expected report window, guidance events, transcript availability
- related-company earnings: peer, customer, supplier, competitor, or sector-leader earnings that can create sector/theme read-through
- option-relevant events: earnings-through-expiry, macro events before expiry, known event dates inside the option holding window

Earnings handling is embedded in the normal event-calendar refresh and signal snapshot assembly:

- Target-company earnings always stay in the target ticker's own signal snapshot. If the reporting ticker is the same as the evaluated ticker, the release, guidance, transcript, and post-earnings analyst revisions are direct company signals.
- The event calendar checks prior-night and upcoming releases for portfolio names, top candidates, active manual review tickers, core holdings, and their configured peer/customer/supplier/competitor/sector-leader relationships.
- Full transcripts are only required for high-value source tickers: direct peers, sector leaders, major customers/suppliers, or cases where the release and price reaction conflict. Otherwise, use structured release/headline/financial-table data first.
- Related-company earnings are stored as macro/sector/theme context with provenance. They must not be treated as the target ticker's own catalyst.
- Target-ticker confirmation is required before read-through affects trade eligibility: relative strength vs peers/theme, price/volume confirmation, and no target-specific contradictory signal.
- Bearish peer read-through should normally reduce size, pause adds, tighten option/event risk, or produce catalyst-watch/risk-review. It should not create a high-confidence single-name bearish trade without target-specific confirmation.

### Peer and Theme Relationship Graph

Read-through relationships must come from structured data, not free-form LLM inference. V2 should add a lightweight relationship graph with:

- `ticker_relationships`: directed relationships such as peer, customer, supplier, competitor, sector leader, ETF/component, theme leader, or theme constituent
- `peer_baskets`: versioned baskets used for relative strength, attribution, and decision-time peer comparison
- `theme_taxonomy`: AI infrastructure, memory, networking, cloud software, cyber, obesity drugs, energy, aerospace/defense, and other user-maintained themes

Each relationship should store source, confidence, valid date range, relation strength, and whether it can be used for read-through, benchmark attribution, candidate generation, or UI grouping. Examples:

- `NVDA` as AI accelerator/AI capex leader for semiconductor and AI infrastructure baskets
- `MU` and `SNDK` as memory/storage peers or theme constituents
- `LITE` and `AAOI` as optical/networking read-through names

The relationship graph is only an input to deterministic relative-strength and read-through logic. It should not let the LLM freely decide that any headline on one company is a catalyst for another company.

Every event shown in the UI must carry a portfolio relevance record:

- `event_importance`: `critical`, `high`, `medium`, or `low`
- `portfolio_risk_level`: `critical`, `high`, `medium`, `low`, or `none`
- `affected_tickers`, `affected_positions`, `affected_option_strategies`
- `affected_sector`, `affected_industry`, and `affected_theme`
- `risk_mechanism`: e.g. direct earnings gap risk, rates sensitivity, inflation sensitivity, AI capex read-through, memory cycle, software multiple risk, option IV/event risk
- `lookahead_reason`: why this event is inside the display window
- `suggested_action_type`: `monitor`, `pause_adds`, `reduce_before_event`, `avoid_event_option`, `review_after_event`, or `none`

The UI should not display every low-importance calendar item. Events with low global importance and no mapped portfolio/candidate/theme exposure should be hidden by default, while still remaining persisted for audit if ingested.

Lookahead window policy:

- intraday and 1-3 day tactical trades: show only same-day and next 5 trading days unless a `critical` macro or own-earnings event is known.
- tactical stock trades up to 3 months: show relevant high/critical events through the intended holding horizon, plus medium events for affected tickers/themes.
- tactical option trades: show all relevant events through expiry plus a small buffer, especially earnings-through-expiry and macro events that can move IV or assignment risk.
- core holdings: show high/critical macro events and own/major-peer earnings for the next 3-6 months; hide routine low-impact releases unless they map to a concentrated risk factor.
- watch-only and manual review tickers: show upcoming own earnings and high-relevance theme/peer events only while the review request or catalyst-watch window is active.

### Stock Trading Strategy Engine

Runs per ticker or per candidate batch. It only uses ticker-level signals plus the already computed macro regime as a constraint. Strategy definitions should not fetch macro data themselves.

Examples:

- `insider_accumulation_momentum_v1`
- `relative_strength_breakout_v1`
- `post_earnings_drift_v1`
- `oversold_reversal_liquid_largecap_v1`
- `volume_shock_continuation_v1`
- `gap_reversal_v1`

Each strategy has explicit inputs, thresholds, candidate scoring, risk tags, holding assumption, and invalidators.

### Relative-Strength Catalyst Policy

V2 should optimize for the pattern that evals showed actually has edge: bullish catalyst plus relative strength confirmation. A bullish stock is not actionable just because the news sounds positive. It becomes actionable when:

- the catalyst is company-specific or tightly theme-specific, such as earnings beat-and-raise, guidance raise, analyst revision cluster, high-signal AI/semiconductor/order/customer news, or confirmed capital rotation
- the stock is outperforming the right benchmark, such as `SMH`/`SOXX` for semiconductors, `QQQ` for growth/AI software, or a configured peer basket
- price and volume confirm the thesis through relative volume, breakout, constructive pullback, VWAP hold/reclaim, or base breakout
- invalidators are concrete and close enough to be traded

Performance evaluation must therefore compare each trade against:

- `SPY`, for broad market context
- `QQQ`, for growth/tech beta
- sector/theme ETFs such as `SMH` or `SOXX` when relevant
- decision-time peer baskets built from sector, industry, theme, market cap, catalyst type, and the alternative candidates available when the decision was made

The key attribution question is not only whether the stock went up over the selected strategy's intended holding period. It is whether the selected stock outperformed the appropriate benchmark and a reasonable peer basket from the same decision-time opportunity set, measured over that strategy horizon and any strategy-specific interim review checkpoints.

### Pipeline-Embedded Bearish Evidence Handling

This is a learned constraint that must be embedded across the normal trading workflow, not a standalone bearish-trading function. Bearish evidence affects strategy eligibility, confidence calibration, sizing, risk approval, reflection, and UI explanations at the points where those decisions already happen.

Bearish output is lower trust than bullish catalyst output until proven otherwise. The normal pipelines should treat bearish evidence in tiers:

| Bearish Evidence Type | Allowed Use |
| --- | --- |
| Direct company-level negative catalyst, e.g. guide-down, accounting issue, failed trial, regulatory action, major customer loss, dilutive offering | May trigger `reduce`, `exit`, `no_trade`, or low-budget bearish/short paper strategy if enabled and price/volume confirm. |
| Sector/theme breakdown with the ticker showing relative weakness vs peers | May reduce position size, reject new longs, or close weak trades. |
| Macro risk-off, VIX, rates, oil, geopolitical risk, broad index weakness | Position sizing and risk-budget input only; not enough for single-name bearish trade. |
| Valuation high, RSI high, stock extended | Risk warning, reduced size, stricter entry, or catalyst-watch; not a high-confidence bearish trade by itself. |

This policy directly addresses the eval failure mode where the model built a long macro chain from “risk-off” to “high-beta semiconductor likely down tomorrow” even while the industry and stock trend stayed strong.

Implementation ownership:

- `StrategyPipeline` downgrades or rejects macro-only bearish strategy matches before they become tradable candidates.
- `PrimaryStrategySelector` and confidence calibration keep macro-only bearish narratives from becoming high-confidence single-name trades.
- `TradingPipeline` may include bearish context in the thesis and invalidators, but cannot convert macro-only context into a standalone short proposal.
- `PositionSizer` and `RiskManager` use bearish context to reduce, block, or tighten exposure.
- `ReflectionPipeline` measures whether bearish/risk-off handling improved outcomes or suppressed strong-trend names.

### Portfolio Pools and Trade Identity

This is also a learned constraint, not an independent strategy by itself. `trade_identity` means portfolio pool / exposure purpose. It answers: what role does this exposure play in the portfolio, which risk budget owns it, which holding-period and exit rules apply, and how should reflection grade it?

`trading_strategy` is different. A strategy explains why a ticker is interesting and what signals/invalidation rules define the opportunity. A strategy can map to different trade identities depending on portfolio context. For example, `trend_pullback_v1` can support adding to an approved core holding, while `earnings_drift_v1` usually maps to a tactical stock trade. Risk-manager option hedges are not alpha strategies and should not be mixed into tactical option-trade performance.

Every trade decision, watch decision, and risk hedge overlay must carry a `trade_identity` before sizing or order simulation:

| Trade Identity | Portfolio Role | Allowed Instruments | Typical Horizon | Owner / Evaluation Policy |
| --- | --- | --- | --- | --- |
| `core_holding` | Long-term ownership pool | Stock | Multi-month to multi-year | Managed by core portfolio rules and risk budget. Bot may recommend pause add, add on pullback, trim for risk budget, or thesis review; it should not liquidate core holdings because of one short-term signal. |
| `tactical_stock_trade` | Intraday to 3-month alpha trade | Stock | Intraday to 3 months | Requires selected strategy, explicit catalyst or technical setup, relative strength, price/volume confirmation, and concrete invalidators. Evaluated against the selected strategy horizon. |
| `tactical_option_trade` | Paper option expression for tactical ideas | Paper/simulated long calls, long puts, call/put credit spreads, long straddles, and long strangles | Intraday to 8 weeks unless strategy-specific rules override | Used when an option better expresses direction, convexity, income, defined risk, volatility, or entry timing than common stock. Requires leg-level metadata, Greeks, max loss, margin requirement, buying-power effect, event risk, and assignment plan when relevant. Evaluated separately from stock confidence. |
| `risk_hedge_overlay` | Portfolio-level hedge owned by risk manager | Paper/simulated option hedge or other overlay | While the risk condition is active | Created by `RiskManager`, not by stock-picking strategies. Evaluated by risk reduction, hedge cost, and hedge PnL, not by strategy win rate. |
| `watch_only` | No-order candidate or manual watch item | None by default | Event window or N/A | Used for `catalyst_watch` and `ordinary_watch` states. Reflection tracks missed opportunities and false alarms, but no order is created. |

The trade identity decides which risk budget applies, which holding-period assumptions are valid, and which exit rules reflection should grade against. Core holdings must have a separate decision pool from tactical trades. Tactical option trades must be separated from risk hedge overlays, even though both can use options, because the former is an alpha/expression choice and the latter is portfolio insurance.

`catalyst_watch` and `ordinary_watch` should be stored as `watch_type` or result status under `trade_identity = "watch_only"`, not as separate trade identities.

Do not encode the instrument choice inside the strategy name. A strategy should describe the edge, e.g. `strong_theme_no_clear_near_term_entry_v1` or `valuation_repair_quality_software_v1`. An expression bucket should describe the implementation, e.g. `defined_risk_directional_option`, `defined_risk_income_spread`, `volatility_event_option`, or `long_stock`. Trade identity then decides which portfolio pool owns the exposure, e.g. `tactical_option_trade`, `core_holding`, `tactical_stock_trade`, or `watch_only`.

Core holdings need a separate upstream intent config. `core_holding` is a trade identity, not permission to invent a long-term holding. A ticker can be classified as `core_holding` only when an active `portfolio_intent` approves it. The intent config should store:

- approved ticker or ETF, e.g. `GOOGL`, `SMH`, `VOO`
- intent type, e.g. `core_growth`, `core_index`, `core_theme`, or `core_cash_like`
- target weight and max weight
- add rules, such as add-on-pullback, add-on-thesis-confirmation, or scheduled contribution
- trim rules, such as overweight, thesis deterioration, concentration cap, or risk-budget pressure
- thesis invalidators that trigger review or forced de-risking
- whether tactical signals may add, pause adds, trim, or only produce review notes

This prevents the bot from guessing core holdings from the current portfolio or from LLM preference. Tactical trades can still use the same ticker, but they must remain in a separate `tactical_stock_trade` or `tactical_option_trade` pool with separate sizing, exit, and reflection.

Implementation ownership:

- `TradeClassifier` assigns the field after primary strategy selection and before sizing.
- `TradingPipeline` uses the field when proposing action, horizon, thesis, invalidators, and suggested size.
- `OptionsStrategyLayer` only builds a paper tactical option expression when the selected expression bucket and `trade_identity = "tactical_option_trade"` make that expression eligible.
- `RiskManager` owns `risk_hedge_overlay` creation, adjustment, and closure. Hedge overlays can use the same paper option broker, but they are persisted and evaluated separately from tactical option trades.
- `PositionSizer` and `RiskManager` apply the pool-specific budget, concentration, hedge, and exit constraints.
- `PortfolioState` persists the identity with open positions, open/pending paper order audit rows, paper option positions, and closed trades.
- `ReflectionPipeline` grades each trade against the holding period and exit rules implied by its identity.

### Paper Options Strategy Layer

The options layer is V2 paper/simulation-only. It is leg-based and must not be limited to puts. It serves two separate portfolio pools:

- tactical option trades, generated from selected strategies and `trade_identity = "tactical_option_trade"`
- risk hedge overlays, generated by `RiskManager` and `trade_identity = "risk_hedge_overlay"`

These must remain separate in attribution. Tactical option trades are evaluated by the selected option expression, e.g. directional long call/put, defined-risk credit spread, or long straddle/strangle. Hedge overlays are evaluated by risk reduction, hedge cost, and hedge PnL.

For tactical option trades, it must support these generic actions:

- `open_option_strategy`: open a single-leg or multi-leg paper option strategy
- `close_option_strategy`: close an existing paper option strategy
- `roll_option_strategy`: close one or more existing legs and open replacement legs when the new risk is acceptable
- `adjust_option_strategy`: add, remove, or resize legs while keeping the strategy inside risk limits
- `avoid_event_option`: block opening, rolling, or holding an option strategy through earnings or another event when the event risk exceeds the strategy rule

The initial V2 option strategy whitelist should include only:

- `long_call`
- `long_put`
- `put_credit_spread`
- `call_credit_spread`
- `long_straddle`
- `long_strangle`

Standalone short puts, covered calls, collars, debit spreads, naked short options, short straddles, short strangles, and custom multi-leg structures are outside the initial whitelist. If the LLM or strategy layer proposes a non-whitelisted `option_strategy_type`, the option layer must reject it or downgrade the candidate to `catalyst_watch`.

Every option strategy decision must record:

- `option_strategy_type`
- `underlying_ticker`
- `legs`: array of option legs with `option_type`, `side`, `quantity`, `strike`, `expiry`, `dte`, `delta`, `gamma`, `theta`, `vega`, `iv_rank` or `iv_percentile`, `bid`, `ask`, `mid`, and chosen price
- `net_debit_or_credit`
- `max_loss`
- `max_profit` when definable
- `breakevens`
- `margin_requirement`
- `buying_power_effect`
- `margin_model_profile`, `margin_model_version`, and `margin_requirement_source`
- `strategy_pairing_method` for multi-leg strategies
- `portfolio_delta`, `portfolio_gamma`, `portfolio_theta`, and `portfolio_vega`
- `earnings_date` and event-through-expiry flags
- `profit_target_pct`
- `max_loss_or_adjustment_rule`
- `roll_conditions`
- `close_conditions`

For assignment-capable strategies, especially credit spreads with short option legs, the decision must also record:

- `assignment_notional`
- `margin_requirement`
- `buying_power_effect`
- `underlying_exposure`
- `assignment_plan`

For risk hedge overlays, `RiskManager` may generate paper-only actions such as `open_hedge`, `close_hedge`, and `adjust_hedge`. These actions can be single-leg or multi-leg option strategies, should use the same paper option order simulation layer, and should not be counted in tactical strategy win rate.

Options confidence should be calibrated separately from stock confidence. A strong theme without a near-term stock entry can justify an option expression, but a long call, long put, credit spread, long straddle, or long strangle should not inherit the same confidence score as a confirmed common-stock breakout. Hedge overlays should not receive alpha confidence; they should carry risk-reduction rationale, expected hedge cost, and invalidation/closure conditions.

### Strategy Catalog

The first production strategy set should be stored as versioned strategy definitions. The morning scanner evaluates every eligible universe symbol against these definitions, then emits `(ticker, strategy_id, horizon, score, evidence)` candidates. A ticker can match multiple strategies, but `PrimaryStrategySelector` must choose one primary tactical strategy and one expression bucket before any trade decision so attribution and learning remain clean.

The seed catalog has two layers:

- trading strategies that explain why a ticker is interesting, including broad tactical patterns and narrower learned playbooks
- strategy expression buckets that decide how the system should express the idea

The 15 tactical strategies below are the initial broad pattern catalog. They are not a fixed universe of possible strategies. Reflection and learning can create new strategy proposals when repeated evidence shows a pattern that is not well captured by the existing catalog.

| Strategy | Strategy ID | Core Signals To Check | Typical Horizon | Thesis |
| --- | --- | --- | --- | --- |
| Catalyst Breakout | `catalyst_breakout_v1` | Fresh high-signal catalyst; post-catalyst volume expansion; price breaking a key level; close above prior resistance; news/filing timestamp freshness | 2 days-4 weeks | New information reprices the stock. |
| Gap-and-Go | `gap_and_go_v1` | Pre-market/opening gap; holds VWAP; breaks opening range high; relative volume confirmation; no immediate gap fade | Intraday-3 days | Overnight information continues as momentum. |
| Gap Fade / Gap Fill | `gap_fade_fill_v1` | Large opening gap; failure to hold VWAP; opening range breakdown; weak relative volume after initial spike; gap fill distance | Intraday-2 days | Opening reaction overextended. |
| Volatility Compression Breakout | `volatility_compression_breakout_v1` | Multi-day narrow range; falling realized volatility/ATR%; Bollinger/Keltner squeeze; volume expansion on breakout; range high break | 1-6 weeks | Compressed volatility releases into trend. |
| Base Breakout | `base_breakout_v1` | Strong stock consolidation; constructive base duration; resistance breakout/new high; volume confirmation; relative strength vs sector/SPY | 2-8 weeks | Second-stage trend begins after consolidation. |
| Trend Pullback | `trend_pullback_v1` | Established uptrend; pullback to support/SMA/VWAP; lower selling volume; RSI reset without trend break; bounce confirmation | 1-8 weeks | Trend continues after internal digestion. |
| Post-Catalyst Pullback | `post_catalyst_pullback_v1` | Prior positive catalyst; controlled pullback into gap/support; gap not fully broken; volume dries on pullback; reclaim trigger | 1-6 weeks | Better second entry after catalyst repricing. |
| Earnings Drift | `earnings_drift_v1` | Earnings beat and raise; positive guidance; post-earnings gap not fully filled; analyst revisions; stable/improving margin narrative | 2 weeks-3 months | Post-earnings expectations continue to drift upward. |
| Analyst Revision Momentum | `analyst_revision_momentum_v1` | EPS/target price estimate increases; multiple analyst upgrades/revisions; post-earnings revision cluster; price confirmation | 1-3 months | Valuation model is being revised upward. |
| Sympathy Trade | `sympathy_trade_v1` | Peer/industry leader catalyst; supply-chain or sector linkage; lagging related stock; sector breadth confirmation; no direct negative news | 2 days-4 weeks | Logic propagates from stock A to stock B. |
| Relative Strength Rotation | `relative_strength_rotation_v1` | Asset/sector/ticker outperforming benchmark; improving relative strength rank; institutional rotation proxy; liquidity confirmation | 2 weeks-3 months | Capital rotates into the stronger asset or group. |
| Pre-Catalyst Run-up | `pre_catalyst_runup_v1` | Known upcoming event; rising volume before event; positive estimate/news drift; price strength into event; options/volatility expansion if available | 3 days-4 weeks | Traders position before the event. |
| Failed Breakdown / Reclaim | `failed_breakdown_reclaim_v1` | Break below support; quick reclaim above support/VWAP; short-term reversal volume; trapped shorts signal; close back inside range | 2 days-3 weeks | Failed breakdown creates reversal squeeze. |
| Oversold Bounce | `oversold_bounce_v1` | Extreme short-term oversold RSI/distance from mean; capitulation volume; stabilization/reclaim trigger; no unresolved major negative catalyst | 1 day-2 weeks | Short-term oversold move mean reverts. |
| Short Squeeze Breakout | `short_squeeze_breakout_v1` | High short interest; rising borrow/fee if available; positive catalyst; volume surge; breakout through resistance; days-to-cover/liquidity risk | 1 day-2 weeks | Crowded short positioning is forced to cover. |

The eval-derived strategy playbooks below are also strategy-layer definitions. They keep thesis and expected edge separate from the instrument used to express the idea.

| Strategy Playbook | Strategy ID | Core Signals To Check | Typical Horizon | Thesis |
| --- | --- | --- | --- | --- |
| Strong Theme Catalyst Continuation | `strong_theme_catalyst_continuation_v1` | Clear bullish catalyst, theme alignment, relative strength vs benchmark/peers, volume/price confirmation | Intraday-3 months | Best candidates are theme leaders with fresh catalysts and confirmed near-term continuation. |
| Strong Theme No Clear Near-Term Entry | `strong_theme_no_clear_near_term_entry_v1` | Strong theme, acceptable underlying quality/liquidity, relative strength still intact, but no clean common-stock trigger or poor entry timing | 2-8 weeks | The underlying is interesting, but the common-stock entry is not clean enough yet. |
| Valuation Repair Quality Software | `valuation_repair_quality_software_v1` | Quality software name, improving valuation/margin/growth narrative, stabilizing estimates, relative strength improving from a depressed base | 2-12 weeks | Valuation repair can create positive drift, but timing and entry quality determine the expression. |
| Core Accumulation On Pullback | `core_accumulation_on_pullback_v1` | Approved core holding, thesis intact, pullback into defined support or risk budget availability | Multi-month+ | Add to core only when the pullback improves risk/reward and portfolio concentration allows it. |

The strategy expression buckets below are also stored in the strategy catalog so attribution and risk budgets are explicit. They are not trade identities and they should not contain the alpha thesis. They map selected strategy evidence to the eligible portfolio pool and instrument expression.

| Strategy Expression Bucket | Expression Bucket ID | Default Trade Identity | Required Context | Typical Horizon | Expression Thesis |
| --- | --- | --- | --- | --- | --- |
| Long Stock | `long_stock` | `tactical_stock_trade` | Near-term continuation is confirmed; stock entry has acceptable risk/reward and liquidity | Intraday-3 months | Own the common stock when direct directional exposure is the cleanest expression. |
| Directional Long Option | `defined_risk_directional_option` | `tactical_option_trade` | Directional catalyst or setup exists, and option convexity or explicit premium-defined max loss is preferable to common stock | Intraday-4 weeks | Express directional views through long calls or long puts only. |
| Credit Spread | `defined_risk_income_spread` | `tactical_option_trade` | Premium is attractive, direction/range thesis is clear, and capped-risk short premium is preferable to standalone short options | 2-8 weeks | Express short-premium views only through put credit spreads or call credit spreads with explicit max loss. |
| Volatility Event Option | `volatility_event_option` | `tactical_option_trade` | Direction is uncertain, event volatility is material, and long-vol premium risk is acceptable | Intraday-4 weeks | Express event volatility through long straddles or long strangles only. |
| Core Stock Accumulation | `core_stock_accumulation` | `core_holding` | Approved core holding and portfolio risk budget allow adding stock exposure | Multi-month+ | Add to a core position through stock only when the core-pool rules approve it. |

Example mapping:

- `strong_theme_catalyst_continuation_v1` + `long_stock` -> `trade_identity = "tactical_stock_trade"`
- `strong_theme_no_clear_near_term_entry_v1` + `defined_risk_income_spread` -> `trade_identity = "tactical_option_trade"`
- event-driven uncertain direction setup + `volatility_event_option` -> `trade_identity = "tactical_option_trade"`
- `valuation_repair_quality_software_v1` + `defined_risk_income_spread` -> `trade_identity = "tactical_option_trade"`
- `core_accumulation_on_pullback_v1` + `core_stock_accumulation` -> `trade_identity = "core_holding"`

### Strategy Lifecycle

Every strategy definition has a lifecycle. The seed strategies start as `active`. Strategies discovered from learning must move through staged gates:

| Status | Meaning | Trading Impact |
| --- | --- | --- |
| `candidate` | Proposed by reflection/strategy evolution, stored for review and future shadow scoring | Not used for trade decisions. |
| `shadow` | Evaluated during scans and scored like an active strategy, but cannot create paper orders | Used to collect evidence only. |
| `experimental` | Can create paper orders with small capped budget and stricter risk limits | Limited paper trading only. |
| `active` | Normal strategy budget and candidate ranking rules apply | Full paper trading eligibility. |
| `retired` | No longer considered by scanner | Kept for audit. |

Promotion policy:

- `candidate -> shadow`: allowed automatically if required signals are computable and the proposal has a non-duplicative thesis.
- `shadow -> experimental`: requires repeated positive shadow evidence or explicit approval.
- `experimental -> active`: requires enough paper-trade evidence, acceptable drawdown, and no concentration/risk violations.
- Any strategy can be retired if reflection finds persistent underperformance, overfitting, or excessive factor concentration.

### Strategy Discovery From Learning

`StrategyEvolutionPipeline` runs after reflection and learning factor update. Its job is to cluster repeated learning factors, rejected-candidate evidence, and portfolio attribution into possible new strategies.

Inputs:

- daily reflections
- learning factors and their later impact
- selected and rejected candidates
- strategy performance by market regime
- risk factor concentration outcomes
- skipped candidates that would have worked
- repeated signal combinations not covered by active strategy definitions

Output schema:

```json
{
  "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
  "display_name": "Post-Gap VWAP Reclaim",
  "source": "reflection_learning",
  "source_reflection_ids": ["reflection_2026_05_29"],
  "core_thesis": "Stocks that initially fail a gap but reclaim VWAP with renewed relative volume often continue intraday.",
  "typical_horizon": "intraday-3d",
  "required_signals": ["opening_gap_pct", "vwap_reclaim", "relative_volume", "opening_range_reclaim"],
  "optional_signals": ["fresh_catalyst_type", "sector_rank_percentile"],
  "scoring_rules": {
    "min_opening_gap_pct": 0.02,
    "min_relative_volume_after_reclaim": 1.2
  },
  "risk_tags": ["gap_risk", "intraday_momentum"],
  "macro_blocked_regimes": ["stressed"],
  "invalidators": ["re-loses VWAP", "relative volume fades", "market breadth deteriorates"],
  "evidence_summary": "Observed in 5 rejected candidates and 2 winning discretionary-like patterns.",
  "lifecycle_status": "candidate"
}
```

Duplicate control:

- Compare required signals, thesis, horizon, and risk tags against existing strategies.
- If overlap is high, create a proposed revision to the existing strategy instead of a new strategy.
- Persist rejected proposals with a duplicate or insufficient-evidence reason for audit.

New strategy safety:

- Newly discovered strategies do not bypass risk management.
- Newly discovered strategies start with smaller budgets and stricter concentration caps.
- The scanner should be able to run active and shadow strategies together, but only active/experimental strategies can generate paper orders.
- Strategy promotion/retirement decisions are stored and visible in UI.

### Strategy Matching Output

`StrategyPipeline` should persist one row per `(strategy_run_id, ticker, strategy_id)` that passes basic eligibility. The score is not a trading action yet; it is a candidate-quality measure.

Required candidate fields:

- `strategy_id` and `strategy_version`
- `ticker`
- `candidate_score` from `0` to `1`
- `typical_horizon`
- `core_signal_evidence`: structured values that caused the match
- `missing_required_signals`
- `invalidators`
- `risk_tags`, e.g. `high_gap_risk`, `low_liquidity`, `earnings_event`, `high_beta`
- `macro_compatibility`: `allowed`, `reduced_size`, or `blocked`
- `selection_reason`
- `rejection_reason`, if not tradable after filters
