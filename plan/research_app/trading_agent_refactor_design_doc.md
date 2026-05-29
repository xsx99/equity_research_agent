# Research App V2: Trading Agent Refactor Design Doc

## 1. 背景

当前 research app 已经从 watchlist 出发，按 ticker 构造 replayable `input_json`，调用 `ResearchAgent` 生成 `decision/actionability/confidence/invalidators`，并在收盘后用 same-day eval 做快速反馈。这个架构适合做 signal engine，但还不是一个能每天自动选股、自动 paper trade、复盘并把经验回注的 trading system。

V2 的目标是把系统从“用户维护 watchlist 后生成研究结论”升级为“系统每天扫描可交易股票 universe，生成量化信号和策略候选，执行纸上交易，收盘后反思交易质量，并把可复用 learning factor 回注到下一次 trading decision”。宏观环境判断必须作为独立模块存在，只提供市场 regime、风险预算和约束，不和个股策略逻辑混在同一个 agent/prompt 里。

## 2. Goals

1. 每天自动扫描股票 universe，筛选合适的交易标的，不再依赖用户手动添加 watchlist。
2. 增加更系统的 quant signals，包括 momentum、mean reversion、volume/liquidity、volatility、gap、relative strength、event/fundamental/insider 等维度。
3. 引入 versioned trading strategies，由策略层把 signals 转成候选交易意图。
4. 引入 paper trading：每天根据策略和风险规则生成 orders，更新 paper portfolio、positions、trades、PnL。
5. 每天收盘后自动 reflection，归因当天交易表现，并生成结构化 learning factors。
6. 下一次 trading agent 决策时注入 active learning factors，但保留审计、版本和回滚能力。
7. UI 首页改为交易工作台，重点显示当天持仓、当天 trades、收盘反思和 learning factors。
8. 明确分离 `Macro Engine` 与 `Stock Trading Strategy Engine`。

## 3. Non-Goals

- 不接入真实券商下单，V2 只做 paper trading。
- 不做高频或分钟级自动交易。首版以 daily pre-market plan、market-open execution simulation、post-close reflection 为主。
- 不让 LLM 直接执行 broker/order/database side effects。Python orchestration 仍然拥有状态流转和持久化。
- 不把 reflection 生成的数值调参无条件自动应用到生产策略。首版只自动注入已激活的 learning factors，并对高风险变更保留人工批准或阈值门槛。
- 不把宏观新闻直接混入每个 ticker prompt 里做随意推理。宏观只通过结构化 macro snapshot/regime 进入个股策略和交易 agent。

## 4. Recommended Approach

### Option A: Layered Incremental Refactor (Recommended)

在现有 `ResearchPipeline` 旁边新增 `UniverseScanPipeline`、`SignalPipeline`、`TradingPipeline`、`ReflectionPipeline`，逐步把 watchlist-driven research 演进成 trading workflow。每层都保存 replayable snapshot，LLM 只负责解释、决策或反思，数据采集、策略计算、paper execution、risk checks 都在 Python 中完成。

优点：复用当前 repo 的 orchestration、tool registry、Postgres、scheduler、FastAPI UI 和测试模式；失败边界清楚；可以分阶段上线。缺点：需要新增多张表和更多 pipeline 状态。

### Option B: Autonomous Multi-Agent System

把 macro、scanner、trader、critic 都做成会动态 tool-calling 的 agents，由 router 调度。

优点：概念上灵活。缺点：replayability、测试、故障隔离和成本控制都更难，不适合当前单用户 daily trading loop 的首版。

### Option C: Quant-Only Strategy Engine With LLM Commentary

所有交易完全由 rule-based strategy 产生，LLM 只解释结果和写复盘。

优点：最可测、最稳定。缺点：没有充分利用当前 research agent 的结构化 reasoning 能力，learning loop 的表达力也弱。

结论：采用 Option A。保留当前“Python owns orchestration, LLM owns bounded reasoning”的原则，把系统拆成可审计的 daily trading layers。

## 5. Target Architecture

```text
UniverseProvider
      |
      v
UniverseScanPipeline -> tradable universe + liquidity/quality filters
      |
      v
SignalPipeline -> per-ticker quant_signal_snapshot
      |                         ^
      |                         |
MacroPipeline -> macro_snapshot + market_regime
      |                         |
      v                         |
StrategyPipeline -> candidate_scores by strategy
      |
      v
TradingPipeline -> proposed trading_decisions
      |
      v
PositionSizer + RiskManager -> approved/reduced/rejected decisions
      |
      v
PaperBroker -> paper_orders -> paper_executions
      |
      v
PortfolioPipeline -> positions + portfolio_snapshots + trade PnL
      |
      v
ReflectionPipeline -> daily_reflections -> learning_factors
      |
      v
Next trading run receives active learning_factors
```

### Component Boundaries

| Component | Responsibility | LLM? | Persistence |
| --- | --- | --- | --- |
| `UniverseProvider` | Load daily tradable US equity universe from market data provider, normalize tickers, apply exchange/asset filters | No | `universe_symbols`, `universe_snapshots` |
| `MacroPipeline` | Fetch rates, VIX, credit spreads, commodities, broad index trend, economic calendar; produce market regime | Optional bounded summary using Gemini Flash | `macro_snapshots` |
| `SignalPipeline` | Compute deterministic per-ticker quant features and normalized signal values | No | `signal_snapshots` |
| `StrategyPipeline` | Match each ticker to versioned strategy definitions, score strategy fit, attach strategy horizon, and create ranked candidates | Mostly no; optional strategy explanation | `strategy_runs`, `candidate_scores` |
| `TradingPipeline` | Combine candidates, macro regime, risk rules, positions, learning factors; produce structured trading decisions | Yes, Gemini Flash bounded decision schema | `trading_decisions`, `paper_orders` |
| `PositionSizer` | Convert approved trade intent into target quantity/weight using volatility, liquidity, strategy budget, macro budget, and factor exposure constraints | No | `position_sizing_decisions` |
| `RiskManager` | Enforce portfolio-level risk limits, factor exposure concentration limits, correlation clusters, and hard reject/reduce rules | No | `portfolio_risk_snapshots`, `risk_factor_exposures` |
| `PaperBroker` | Simulate fills, slippage, commissions, rejects, and order status transitions | No | `paper_orders`, `paper_executions` |
| `PortfolioPipeline` | Maintain positions, cash, exposure, realized/unrealized PnL | No | `paper_positions`, `portfolio_snapshots` |
| `ReflectionPipeline` | Analyze day results, compare thesis vs outcome, extract learning factors | Yes, highest-quality configured model | `daily_reflections`, `learning_factors` |

### Model Routing Policy

Most daily LLM calls should optimize for cost, latency, and predictable structured output. Reflection is the exception because it is the highest-leverage reasoning step: it reviews portfolio outcomes, rejected candidates, macro context, risk constraints, and learning-factor impact, then writes lessons that will affect future trading behavior.

Model defaults:

| Runtime Path | Default Model Policy | Reason |
| --- | --- | --- |
| Macro summary, if used | `gemini-2.5-flash` or current Gemini Flash equivalent | Short bounded summary; most logic remains deterministic. |
| Trading decisions | `gemini-2.5-flash` or current Gemini Flash equivalent | Needs fast structured decisions from already-computed candidates/signals. |
| Candidate explanations | `gemini-2.5-flash` or current Gemini Flash equivalent | UI explanation only; candidate scoring remains deterministic. |
| Research audit runs | `gemini-2.5-flash` or current Gemini Flash equivalent unless explicitly overridden | Cost-efficient audit/research path. |
| Post-close reflection | Highest-quality configured model, e.g. `REFLECTION_MODEL_NAME` pointing to the strongest available reasoning model | Reflection generates learning factors that feed back into future trading. |

Config should keep these separate:

- `DEFAULT_FAST_MODEL_NAME`: default non-reflection model, initially Gemini Flash.
- `TRADING_MODEL_NAME`: optional override for `TradingPipeline`; defaults to `DEFAULT_FAST_MODEL_NAME`.
- `RESEARCH_MODEL_NAME`: optional override for legacy/research audit runs; defaults to `DEFAULT_FAST_MODEL_NAME`.
- `REFLECTION_MODEL_NAME`: required for production reflection, set to the highest-quality model available in the deployment.

If `REFLECTION_MODEL_NAME` is not configured, reflection may run in degraded mode with the fast model for local development, but production should surface a warning because lower-quality reflection can pollute the learning loop.

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

Macro does not rank individual stocks. It can constrain risk, block strategy tags, reduce gross exposure, or annotate the day as unsuitable for certain strategies.

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

### Strategy Catalog

The first production strategy set should be stored as versioned strategy definitions. The morning scanner evaluates every eligible universe symbol against these definitions, then emits `(ticker, strategy_id, horizon, score, evidence)` candidates. A ticker can match multiple strategies, but the trading layer must choose one primary strategy per action so attribution and learning remain clean.

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

## 7. Quant Signals

Signals should be deterministic Python outputs and stored before any LLM call. Each signal includes `value`, `direction`, `z_score/percentile` when available, `lookback`, `source`, and `computed_at`.

### Signal Groups

| Group | Example Signals |
| --- | --- |
| Momentum / Trend | 5d/20d/60d returns, price vs SMA/EMA, trend slope, new high distance |
| Mean Reversion | RSI 2/3/14, distance from VWAP/SMA, short-term reversal score |
| Volume / Liquidity | relative volume, dollar volume, volume acceleration, spread proxy, liquidity eligibility |
| Volatility / Risk | ATR%, realized volatility, gap size, intraday range, beta proxy, drawdown from recent high |
| Relative Strength | return vs SPY, sector-relative return, rank within sector |
| Event / Calendar | earnings date distance, post-earnings window, economic calendar risk day |
| Insider / SEC | net insider value, cluster buys, sale concentration, officer/director weight |
| News / Sentiment | high-signal news count, analyst rating events, guidance, filing/news freshness |
| Fundamentals | valuation bands, short interest, market cap/liquidity quality filters |

首版不需要一次实现所有信号，但 schema 要允许增量添加。缺失信号必须显式保存为 `null` 或 `status=missing`，不能在 prompt 中伪造。

### Required Signal Families For Strategy Matching

The signal schema should explicitly support the strategy catalog above:

- Catalyst signals: `fresh_catalyst_type`, `catalyst_published_at`, `catalyst_strength_score`, `beat_raise_flag`, `guidance_revision_score`, `analyst_revision_count`.
- Gap/VWAP signals: `opening_gap_pct`, `premarket_gap_pct`, `vwap_reclaim`, `vwap_hold`, `opening_range_high_break`, `opening_range_low_break`, `gap_fill_pct_remaining`.
- Breakout/base signals: `resistance_break_score`, `base_duration_days`, `price_near_52w_high_pct`, `new_high_break`, `breakout_volume_confirmed`.
- Trend/pullback signals: `trend_slope_20d`, `price_vs_sma_20`, `price_vs_sma_50`, `pullback_depth_pct`, `support_reclaim_score`, `selling_volume_dry_up`.
- Volatility compression signals: `atr_pct`, `realized_volatility_percentile`, `range_compression_percentile`, `squeeze_score`, `range_break_direction`.
- Relative strength signals: `rs_vs_spy_20d`, `rs_vs_sector_20d`, `sector_rank_percentile`, `rotation_score`.
- Mean reversion signals: `rsi_2`, `rsi_3`, `rsi_14`, `distance_from_sma_20_pct`, `capitulation_volume_score`, `reversal_triggered`.
- Short squeeze signals: `short_interest_pct_float`, `days_to_cover`, `borrow_fee_proxy`, `float_rotation_proxy`, `squeeze_pressure_score`.
- Sympathy signals: `leader_ticker`, `leader_catalyst_type`, `peer_link_strength`, `industry_move_pct`, `laggard_confirmation_score`.
- Event timing signals: `earnings_in_days`, `known_event_date`, `pre_event_runup_score`, `event_risk_flag`.

## 8. Daily Workflow

All scheduled times are in `America/New_York`.

| Time | Job | Output |
| --- | --- | --- |
| 07:00 | Universe refresh | tradable symbols and exclusions |
| 07:15 | Macro snapshot | `macro_snapshots` with regime and risk budget multiplier |
| 07:30 | Pre-market signal computation | `signal_snapshots` for the universe |
| 08:15 | Strategy matching and candidate scoring | `candidate_scores` with strategy, horizon, evidence, invalidators |
| 08:45 | Trading decision generation | `trading_decisions` with selected action and staged `paper_orders` |
| 09:30 | Paper open execution | `paper_executions`, open positions |
| 15:55 | Optional risk check | staged close/rebalance decisions if enabled |
| 16:05 | Portfolio mark | `portfolio_snapshots`, trade PnL |
| 16:20 | Daily reflection | `daily_reflections` |
| 16:40 | Learning factor update | `learning_factors`, next-run context |

Manual runs remain available for debugging, but scheduled daily flow is the primary product path.

Morning workflow semantics:

1. Scan the configured universe before the open and compute all available pre-market/daily signals.
2. Match each symbol against the strategy catalog. Each match carries its own strategy horizon, required evidence, and invalidators.
3. Rank candidates by strategy fit, signal quality, macro compatibility, liquidity, and learning-factor adjustments.
4. Pass only the top candidates plus current positions into `TradingPipeline`.
5. `TradingPipeline` proposes an action, target size, and horizon.
6. Deterministic risk constraints and portfolio budget decide whether the proposed action becomes a staged paper order, is reduced, or is rejected.

The final morning output is not just a ranked list. It is a trade plan: selected ticker, selected strategy, horizon, action, target exposure, risk budget used, and explicit reason if a high-scoring candidate was skipped.

## 9. Trading Decision Contract

The trading agent receives:

- active candidates with full signal snapshots and strategy scores
- macro snapshot/regime
- current paper portfolio and open positions
- risk config
- active learning factors relevant to strategy/ticker/sector/regime
- recent trade outcomes for the same strategy or ticker

It returns one JSON object per candidate or position:

```json
{
  "ticker": "AAPL",
  "decision": "enter_long",
  "strategy_id": "relative_strength_breakout_v1",
  "confidence": 0.72,
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
- `enter_short` (optional; can be disabled in config)
- `hold`
- `reduce`
- `exit`
- `no_trade`

Risk checks run before order creation. If risk checks fail, no paper order is created even if the LLM decision is actionable.

`time_horizon` should come from the selected strategy definition, not from a global default. The trading agent may shorten or skip a trade if risk conditions conflict with the strategy horizon, but it should not silently rewrite the strategy's typical horizon without recording a reason.

### Risk Constraint and Budget Decision

The final action is computed in two stages:

1. `TradingPipeline` proposes `decision`, `target_weight`, `time_horizon`, and thesis.
2. `RiskManager` applies deterministic constraints and returns `approved`, `reduced`, or `rejected`.

Risk decision fields:

- `portfolio_cash_available`
- `gross_exposure_before` and `gross_exposure_after`
- `strategy_budget_remaining`
- `macro_budget_multiplier`
- `factor_exposure_before` and `factor_exposure_after`
- `remaining_factor_budget_by_type`
- `binding_factor_limits`
- `position_limit_check`
- `liquidity_check`
- `stale_signal_check`
- `learning_factor_adjustments`
- `final_action`: `create_order`, `reduce_size_create_order`, or `reject`
- `risk_rejection_reason`

## 10. Paper Trading and Risk

### Paper Broker Rules

- Default execution model: market-on-open for planned entries, close price for end-of-day exits.
- Slippage model: configurable bps by liquidity bucket.
- Commission model: configurable flat or zero.
- Fill rejection if price, volume, or market data is missing.
- All fills are persisted; order state transitions are auditable.

### Position Management

Position sizing is deterministic and happens after the trading agent proposes a trade. The trading agent may suggest `target_weight`, but `PositionSizer` owns the final size. The sizing algorithm should combine:

- strategy candidate score
- trading decision confidence
- strategy-level risk budget
- macro risk budget multiplier
- ticker volatility / ATR%
- liquidity and dollar-volume capacity
- current cash and gross/net exposure
- current exposure to the same risk factors
- active learning factors that tighten sizing rules

Initial sizing rule:

```text
base_weight = strategy_budget * candidate_score * confidence * macro_risk_budget_multiplier
vol_adjusted_weight = base_weight * target_volatility / ticker_realized_volatility
liquidity_capped_weight = min(vol_adjusted_weight, max_liquidity_participation_weight)
final_weight = min(liquidity_capped_weight, remaining_factor_budget, single_name_limit)
```

The exact formula can evolve, but every sizing decision must persist inputs, caps applied, and final size. If a trade is reduced because of risk, the UI should show the binding constraint.

### Portfolio Risk Factor Model

`RiskManager` should maintain a portfolio risk snapshot before order staging, after order staging, and after fills. The purpose is to avoid a portfolio that looks diversified by ticker count but is concentrated in the same underlying risk.

Risk factors to track:

| Factor Type | Exposure Examples | Why It Matters |
| --- | --- | --- |
| Single name | ticker weight, beta-adjusted ticker weight | Prevent one position dominating PnL. |
| Sector / industry | GICS sector, industry group, theme cluster | Avoid all trades being the same sector bet. |
| Strategy | gap, breakout, earnings drift, squeeze, mean reversion | Avoid one strategy regime dominating the book. |
| Horizon bucket | intraday, 1-3d, 1-2w, 2w-3m | Avoid liquidity/risk mismatch across holding periods. |
| Direction | long, short, gross, net | Control net market exposure and leverage. |
| Market beta | SPY beta, high-beta basket proxy | Avoid hidden market beta concentration. |
| Volatility | high ATR%, realized vol percentile | Avoid all positions being high-vol names. |
| Liquidity | dollar volume bucket, spread proxy | Avoid crowding into hard-to-exit positions. |
| Momentum / reversal | high momentum, oversold, squeeze pressure | Avoid correlated factor trades across names. |
| Event/catalyst | earnings, analyst revision, regulatory, M&A, macro event | Avoid too many event-risk trades on the same day. |
| Macro sensitivity | rates-sensitive, oil-sensitive, USD-sensitive, credit-sensitive | Keep macro factor exposure aligned with macro regime. |
| Correlation cluster | rolling return correlation or sector/theme cluster | Catch hidden concentration across related tickers. |

Factor exposures should be approximate in V2. A robust simple model is better than a fragile complex one: start with sector/industry, strategy, horizon, direction, beta proxy, volatility bucket, liquidity bucket, and event type, then add rolling-correlation clusters once enough market data is available.

### Initial Risk Rules

- Max position weight per ticker.
- Max daily new positions.
- Max gross exposure and max long/short exposure.
- Minimum dollar volume and price filters.
- Macro risk budget multiplier applies before sizing.
- Strategy-level caps, e.g. max 3 trades per strategy per day.
- Sector and industry exposure caps.
- Strategy exposure caps, e.g. max total exposure in `gap_and_go_v1` or all gap strategies.
- Horizon bucket caps, especially for longer horizon swing trades.
- Event exposure caps, e.g. max earnings-related exposure per day.
- High-volatility bucket cap.
- Low-liquidity bucket cap.
- Market beta-adjusted exposure cap.
- Correlation cluster cap so related tickers do not create hidden concentration.
- No averaging down in V2 unless explicitly added later.
- No trading around missing or stale signal snapshots.

### Risk Limits and Actions

Risk limits should distinguish soft warnings from hard blocks:

- Soft warning: allow order but mark the portfolio as near limit.
- Size reduction: reduce order until exposure fits the remaining factor budget.
- Hard reject: no order is created.
- Forced reduce/exit: only for existing positions that violate hard limits after market movement or stale risk data.

Example risk-limit config:

```json
{
  "max_single_name_weight": 0.08,
  "max_sector_weight": 0.30,
  "max_strategy_weight": 0.25,
  "max_horizon_bucket_weight": {
    "intraday": 0.35,
    "1d-2w": 0.45,
    "2w-3m": 0.35
  },
  "max_event_type_weight": {
    "earnings": 0.20,
    "short_squeeze": 0.15
  },
  "max_high_vol_bucket_weight": 0.25,
  "max_low_liquidity_weight": 0.10,
  "max_beta_adjusted_net_exposure": 0.80,
  "max_correlation_cluster_weight": 0.25
}
```

The risk manager must persist both accepted and rejected decisions. Rejected trades are important training data for reflection because the system should learn whether risk constraints protected the portfolio or blocked good opportunities.

## 11. Reflection and Learning Loop

Reflection runs after the portfolio is marked to close. It receives:

- morning macro snapshot
- strategy candidates and scores
- trading decisions and rejected decisions
- paper orders/executions
- end-of-day PnL, benchmark return, sector return
- per-trade MFE/MAE if available
- invalidators and whether they triggered
- prior learning factors used

Reflection should evaluate the portfolio, not just individual research calls. The main questions are:

- Did the selected strategies perform as expected for their horizons?
- Did risk constraints prevent losses or block profitable opportunities?
- Were skipped candidates better than selected trades?
- Did macro regime constraints help or hurt?
- Was the portfolio too concentrated in any sector, strategy, horizon, beta, volatility, liquidity, event, macro, or correlation factor?
- Did factor concentration explain more PnL than ticker selection?
- Did active learning factors improve decisions, overfit, or become stale?

The reflection output is structured:

```json
{
  "trade_date": "2026-05-28",
  "portfolio_summary": {
    "realized_pnl": 123.45,
    "unrealized_pnl": -12.34,
    "benchmark_return": 0.004
  },
  "what_worked": ["Avoided high beta longs during elevated volatility."],
  "what_failed": ["Chased opening gap without enough volume confirmation."],
  "attribution": [
    {
      "strategy_id": "gap_reversal_v1",
      "result": "negative",
      "root_cause": "entry_too_early",
      "evidence": ["MAE exceeded planned risk before signal confirmation"]
    }
  ],
  "learning_factors": [
    {
      "type": "candidate_filter",
      "scope": "strategy",
      "strategy_id": "gap_reversal_v1",
      "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
      "recommendation": "downgrade candidate unless volume confirms in first 30 minutes",
      "confidence": 0.66,
      "activation_policy": "auto_context"
    }
  ]
}
```

The next trading run must adapt to active learning factors by injecting them into candidate scoring and trading decision context. Adaptation means:

- candidate scores can be adjusted by strategy-scoped learning factors
- trading prompt context includes relevant active lessons for strategy/ticker/sector/regime
- risk manager can apply approved learning factors that tighten constraints
- every applied learning factor is persisted through `learning_factor_applications`
- later reflections evaluate whether the learning factor helped, hurt, or should be retired

### Learning Factor Lifecycle

| Status | Meaning |
| --- | --- |
| `candidate` | Newly generated by reflection, not used yet |
| `active` | Injected into trading agent context |
| `suppressed` | Stored but not injected |
| `retired` | No longer relevant |

Initial policy:

- Textual reminders and candidate filters can become `active` automatically if confidence is high enough and no risk rule is weakened.
- Numeric sizing/risk changes require explicit approval or repeated evidence over multiple days.
- Every trading decision stores which learning factors were injected so impact can be evaluated later.

## 12. Data Model Additions

Proposed new tables:

| Table | Purpose |
| --- | --- |
| `universe_snapshots` | One row per daily universe refresh |
| `universe_symbols` | Symbols included/excluded in a universe snapshot with reason |
| `macro_snapshots` | One macro snapshot/regime per run/day |
| `signal_snapshots` | Per ticker per day quant features and normalized signal JSON |
| `strategy_definitions` | Versioned strategy metadata, required signals, horizon, scoring config, invalidators |
| `strategy_runs` | One candidate-scoring batch per day |
| `candidate_scores` | Ranked ticker candidates by strategy, horizon, evidence, macro compatibility |
| `trading_decisions` | Trading agent decisions and context snapshot |
| `risk_limit_configs` | Versioned portfolio risk limits and factor exposure caps |
| `position_sizing_decisions` | Deterministic sizing inputs, applied caps, final target weight/quantity |
| `portfolio_risk_snapshots` | Portfolio-level gross/net exposure and factor exposures before/after proposed trades and after fills |
| `risk_factor_exposures` | Normalized per-position and portfolio exposures by factor type/name |
| `paper_orders` | Staged/submitted/filled/rejected paper orders |
| `paper_executions` | Simulated fills |
| `paper_positions` | Current position state |
| `portfolio_snapshots` | Daily portfolio NAV, exposure, cash, PnL |
| `daily_reflections` | Post-close reflection JSON |
| `learning_factors` | Structured lessons with status/version/scope |
| `learning_factor_applications` | Join table showing which decision used which learning factor |

Existing tables remain useful:

- `watchlists` becomes a manual override list, not the source of truth for daily scan.
- `research_runs` and `research_outputs` can remain as explanatory research artifacts, but trading decisions should use dedicated `trading_decisions` rows so research/eval history does not get overloaded.
- `eval_results` remains for research output scoring; trade/portfolio scoring should move to paper trading tables.

### Strategy Definition Shape

`strategy_definitions.config_json` should be expressive enough to store the strategy catalog without code changes for every threshold tweak:

```json
{
  "strategy_id": "gap_and_go_v1",
  "display_name": "Gap-and-Go",
  "typical_horizon": "intraday-3d",
  "core_thesis": "Overnight information continues as momentum.",
  "required_signals": ["opening_gap_pct", "vwap_hold", "opening_range_high_break", "relative_volume"],
  "optional_signals": ["fresh_catalyst_type", "sector_rank_percentile"],
  "risk_tags": ["gap_risk", "momentum"],
  "macro_blocked_regimes": ["stressed"],
  "scoring_rules": {
    "min_opening_gap_pct": 0.02,
    "min_relative_volume": 1.5
  },
  "invalidators": ["loses VWAP", "fails opening range high", "relative volume fades"]
}
```

This keeps strategy identity, horizon, and signal requirements in data. Python strategy evaluators can still implement the scoring math, but the DB row is the audit source for what version was active on a given trade date.

## 13. UI Design

Default page should become a daily trading dashboard instead of a research run list.

### Primary Navigation

- `Today`
- `Portfolio`
- `Trades`
- `Candidates`
- `Reflections`
- `Research`
- `Watchlist` or `Overrides`

### `/today`

Above the fold:

- trade date and job status timeline
- current NAV, day PnL, benchmark return, gross exposure, cash
- macro regime panel, clearly labeled as macro-only
- risk budget, factor exposure usage, and blocked strategy tags

Main sections:

1. `Current Positions`
   - ticker, side, quantity, average price, last/close price, day PnL, total PnL, strategy, horizon, factor tags, holding age, invalidator status
2. `Today's Trades`
   - time, ticker, action, proposed size, final size, fill price, strategy, horizon, decision confidence, order status, reject/reduction reason
3. `Candidate Scanner`
   - ranked candidates, strategy, horizon, score, top signals, why selected, why rejected
4. `Risk Exposure`
   - sector/industry exposure, strategy exposure, horizon bucket exposure, beta-adjusted exposure, volatility/liquidity buckets, event exposure, correlation clusters, binding limits
5. `Post-Close Reflection`
   - what worked, what failed, strategy attribution, concrete evidence
6. `Learning Factors`
   - new factors, active factors used today, status, scope, confidence, source reflection

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
- Missing provider data should degrade the relevant signal to missing, not fabricate values.
- Candidate scoring skips tickers without minimum required signals.
- Trading decisions must persist full context snapshots: candidate signals, macro snapshot id, portfolio snapshot id, risk config version, strategy version, learning factors used.
- Paper orders must be idempotent per `trade_date + ticker + strategy_id + decision_type`.
- A failed ticker must not abort the whole universe scan.
- Reflection failure must not mutate learning factors.

## 15. Testing and Smoke Tests

Unit tests:

- signal computations
- universe filters
- macro regime classification
- strategy candidate scoring
- risk checks
- factor exposure calculation
- concentration limit enforcement
- position sizing and size-reduction reasons
- paper order state transitions
- portfolio PnL calculations
- learning factor activation rules
- web route rendering for today/trades/reflections

Smoke tests:

- standalone market data smoke for universe + signal computation
- standalone DB smoke for writing signal/candidate/order/portfolio rows
- standalone DB smoke for writing portfolio risk snapshots and risk factor exposures
- optional live paper-trade dry run that uses a tiny ticker set and does not consume large API quota

Implementation must continue to use `source ~/.venv/bin/activate` before Python commands and must verify Postgres data directory is on persistent disk for deployment work.

## 16. Phased Delivery

### Phase 1: Foundation

- Add data model for universe, signals, macro snapshots, strategy definitions, candidate scores.
- Implement universe refresh and deterministic signal snapshots.
- Seed the initial strategy catalog with core signals and typical horizons.
- Add candidate scanner UI.

### Phase 2: Paper Trading

- Add trading decisions, paper orders, executions, positions, portfolio snapshots.
- Implement position sizing, risk checks, factor exposure caps, budget allocation, and paper broker.
- Replace homepage with `/today` trading dashboard.

### Phase 3: Reflection

- Add post-close reflection agent and `daily_reflections`.
- Generate learning factors with lifecycle statuses.
- Show reflection and learning factors in UI.

### Phase 4: Learning Injection

- Inject active learning factors into `TradingPipeline`.
- Persist learning factor applications.
- Evaluate whether factors improved strategy outcomes.

### Phase 5: Strategy Expansion

- Add more strategy definitions and signal groups.
- Add macro-aware strategy blocking and risk-budget adjustment.
- Add richer attribution across ticker, strategy, sector, and macro regime.

## 17. Acceptance Criteria

1. A scheduled run can scan a configured US equity universe without relying on watchlist entries.
2. The system stores replayable quant signal snapshots for every scanned candidate.
3. Macro snapshot/regime is stored separately from stock strategy inputs.
4. Strategy pipeline evaluates the initial strategy catalog and stores strategy-specific candidate score, evidence, invalidators, and typical horizon.
5. The morning trade plan selects ticker, strategy, horizon, action, target exposure, and risk budget used before the market opens.
6. Trading pipeline creates paper orders only after risk checks and budget allocation pass.
7. Position sizing records base size, volatility adjustment, liquidity cap, remaining factor budget, final size, and binding constraints.
8. Portfolio risk snapshots show factor exposure by sector, strategy, horizon, beta, volatility, liquidity, event type, macro sensitivity, and correlation cluster.
9. Risk manager reduces or rejects trades that would make the portfolio too concentrated in any configured risk factor.
10. Paper portfolio shows positions, trades, exposure, and day PnL.
11. Post-close reflection analyzes portfolio returns, selected trades, rejected candidates, macro constraints, factor concentration, and learning-factor impact.
12. Active learning factors are visible in UI, injected into later trading decisions, and tracked through `learning_factor_applications`.
13. `/today` shows current positions, today trades, strategy/horizon, risk factor exposure, reflection, learning factors, and macro regime without requiring the user to inspect raw JSON.
14. Existing research run audit pages continue to work.

## 18. Open Questions

1. Universe scope: all US listed common stocks, or only a liquidity-filtered subset such as price > $5 and dollar volume > configurable threshold?
2. Long-only first, or include short paper trades from V2?
3. Holding period: strictly intraday close-out, 1-5 day swing paper trades, or both with separate strategy tags?
4. Should learning factors auto-activate immediately, or require approval for the first few weeks?
5. Should manual watchlist symbols always bypass universe filters, or only appear as pinned candidates?
