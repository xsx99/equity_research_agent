# Research App V2: Trading Agent Refactor Design Doc

## 1. 背景

当前 research app 已经从 watchlist 出发，按 ticker 构造 replayable `input_json`，调用 `ResearchAgent` 生成 `decision/actionability/confidence/invalidators`，并在收盘后用 same-day eval 做快速反馈。这个架构适合做 signal engine，但还不是一个能每天自动选股、自动 paper trade、复盘并把经验回注的 trading system。

V2 的目标是把系统从“用户维护 watchlist 后生成研究结论”升级为“系统每天扫描可交易股票 universe，生成量化信号和策略候选，执行纸上交易，收盘后反思交易质量，并把可复用 learning factor 回注到下一次 trading decision”。宏观环境判断必须作为独立模块存在，只提供市场 regime、风险预算和约束，不和个股策略逻辑混在同一个 agent/prompt 里。

500+ eval 的核心结论是：当前 trading agent 更像 bullish catalyst scanner，而不是成熟自动交易系统。它在财报 beat-and-raise、上调评级、AI/半导体主题、资金追逐、放量突破等明确 catalyst 场景下有可优化的短期延续性；但 bearish 信号质量明显差，尤其容易把宏观 risk-off、VIX、油价、美债、地缘政治等长逻辑链误转成单票做空信号。V2 必须把这个经验固化为设计约束：宏观主要用于仓位和风险预算，不直接决定单票 bearish。

## 2. Goals

1. 每天自动扫描股票 universe，筛选合适的交易标的，不再依赖用户手动添加 watchlist。
2. 增加更系统的 quant signals，包括 momentum、mean reversion、volume/liquidity、volatility、gap、relative strength、event/fundamental/insider 等维度。
3. 引入 versioned trading strategies，由策略层把 signals 转成候选交易意图。
4. 允许系统从 reflection/learning 中归纳新的 trading strategy，并把新 strategy 加入 versioned strategy catalog；初始 15 个策略只是 seed set，不是上限。
5. 引入 paper trading：每天根据策略和风险规则生成 orders，更新 paper portfolio、positions、trades、PnL。
6. 常规交易时段每小时扫描新闻，盘前和盘后再额外扫描一次，识别高影响正面/负面事件，并在风险约束下立即触发调仓或退出。
7. 每天收盘后自动 reflection，归因当天交易表现，并生成结构化 learning factors 和 strategy proposals。
8. 下一次 trading agent 决策时注入 active learning factors，并让 active/shadow strategies 参与下一轮扫描，但保留审计、版本和回滚能力。
9. UI 首页改为交易工作台，重点显示当天持仓、当天 trades、live alerts、收盘反思、learning factors 和 strategy evolution。
10. 明确分离 `Macro Engine` 与 `Stock Trading Strategy Engine`。
11. 先验证相对行业、主题、同类股票和成交量/价格结构，再找明确个股，最后决定是否交易。
12. 每个交易必须先归类为核心仓、实验性的卫星仓、卖put等等trade identity，并由这个身份决定仓位、持有周期、退出规则和反思口径。
13. 增加 paper/simulation-only options strategy layer，至少支持 `sell_put`、`close_put`、`roll_put`、`avoid_earnings_put`、`put_assignment_plan`。
14. Risk manager 必须用 worst-case assigned portfolio 评估 short put 风险，而不是只看当前股票仓位，同时注意宏观经济calendar和earnings calendar，防止event risk。
15. Confidence 必须按历史 pattern 和策略桶校准，不能因为叙事完整或宏观理由多就给高分。
16. 支持用户手动 pin ticker 让 trading bot 强制评估，但 manual request 只代表“必须评估”，不代表“允许交易”。

## 3. Non-Goals

- 不接入真实券商下单，V2 只做 paper trading。
- 不做高频或分钟级自动交易。首版以 daily pre-market plan、market-open execution simulation、post-close reflection 为主。
- 不让 LLM 直接执行 broker/order/database side effects。Python orchestration 仍然拥有状态流转和持久化。
- 不把 reflection 生成的数值调参无条件自动应用到生产策略。首版只自动注入已激活的 learning factors，并对高风险变更保留人工批准或阈值门槛。
- 不让新生成的 strategy 直接扩大组合风险。自动发现的 strategy 必须先进入 candidate/shadow lifecycle，并受更小的 strategy/risk budget 约束。
- 不让新闻情绪单独绕过风险管理。Intraday 新闻只能触发有审计的 rebalance proposal，最终仍由 `RiskManager` 和 `PaperBroker` 执行。
- 不把宏观新闻直接混入每个 ticker prompt 里做随意推理。宏观只通过结构化 macro snapshot/regime 进入个股策略和交易 agent。
- 不因为宏观 risk-off、估值高、RSI 高、VIX 上升等单独理由生成单票做空或高 confidence bearish trade。除非有直接公司级负面 catalyst 和价格/成交量确认，否则 bearish 结论只能作为风险提示、减仓或暂停加仓依据。
- 不让短线 catalyst 信号直接驱动核心仓卖出。核心仓由独立的风险预算、加仓/暂停加仓规则和 thesis invalidation 管理。
- Options layer 在 V2 只做 paper/simulation，不接入真实期权下单。默认假设可以用保证金sell naked put。
- 不让手动 pin 的 ticker 绕过 liquidity、missing data、risk manager、short-put assignment risk 或 bearish gating。手动 pin 只是 evaluation source，不是 trade approval。

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
ManualTickerReviewPipeline -> pinned/manual review symbols
      |
      v
SignalPipeline -> per-ticker multi-source signal_snapshot
      |                         ^
      |                         |
MacroPipeline -> macro_snapshot + market_regime
      |                         |
      v                         |
StrategyPipeline -> multi-strategy candidate_scores
      |
      v
PrimaryStrategySelector + TradeClassifier -> selected strategy + trade identity
      |
      v
OptionsStrategyLayer -> instrument plan, if option expression is eligible
      |
      v
TradingPipeline -> proposed trading decisions + thesis + suggested sizing
      |
      v
PositionSizer + RiskManager -> approved/reduced/rejected final action, including worst-case assignment checks
      |
      v
PaperBroker -> paper_orders / paper_option_orders -> paper_executions
      |
      v
PortfolioPipeline -> positions + portfolio_snapshots + trade PnL
      |
      v
HourlySignalRefreshPipeline -> intraday_signal_snapshots + news_alerts -> intraday_rebalance_decisions
      |
      v
PositionSizer + RiskManager -> approved/reduced/rejected intraday actions
      |
      v
PaperBroker -> intraday paper_orders -> paper_executions
      |
      v
ReflectionPipeline -> daily_reflections -> learning_factors
      |
      v
StrategyEvolutionPipeline -> strategy_proposals -> strategy_definitions
      |
      v
Next trading run receives active learning_factors
```

### Component Boundaries

| Component | Responsibility | LLM? | Persistence |
| --- | --- | --- | --- |
| `UniverseProvider` | Load daily tradable US equity universe from market data provider, normalize tickers, apply exchange/asset filters | No | `universe_symbols`, `universe_snapshots` |
| `ManualTickerReviewPipeline` | Accept user-pinned tickers for forced evaluation, validate basic eligibility, attach request reason/mode, and merge them into signal/strategy evaluation without granting trade approval | No | `manual_ticker_requests`, `universe_symbols`, `signal_snapshots` |
| `MacroPipeline` | Fetch rates, VIX, credit spreads, commodities, broad index trend, economic calendar; produce market regime | Optional bounded summary using Gemini Flash | `macro_snapshots` |
| `SignalPipeline` | Build deterministic per-ticker signal snapshots from market bars plus normalized Postgres-backed insider, SEC, news, fundamentals, event/earnings calendar, options, and existing research context data; refresh provider data only through controlled adapters when needed | No | `signal_snapshots` |
| `StrategyPipeline` | Match each ticker to versioned strategy definitions, score every eligible `(ticker, strategy_id)` pair, attach strategy horizon/evidence, and create ranked candidate scores | Mostly no; optional strategy explanation | `strategy_runs`, `candidate_scores` |
| `PrimaryStrategySelector` | Choose one primary tactical strategy and one strategy bucket per ticker/action so attribution, trade identity, and risk budgeting stay clean | No | `trade_classifications`, `trading_decisions` context |
| `TradeClassifier` | Assign trade identity before any order decision: core holding, catalyst stock, theme sell-put, valuation repair sell-put, or watch/catalyst-watch | No | `trade_classifications` or embedded in `trading_decisions` |
| `OptionsStrategyLayer` | Create paper-only instrument plans only when an option expression is eligible, including strike/expiry/DTE/delta/IV/premium/breakeven/assignment risk fields | Mostly no; optional explanation | `option_strategy_decisions`, `paper_option_orders`, `paper_option_positions` |
| `TradingPipeline` | Combine selected strategy, trade identity, instrument plan, macro regime, portfolio state, risk config, and learning factors; produce proposed trading decisions, thesis, invalidators, and suggested sizing | Yes, Gemini Flash bounded decision schema | `trading_decisions`, `paper_orders` |
| `PositionSizer` | Convert approved trade intent into target quantity/weight using volatility, liquidity, strategy budget, macro budget, and factor exposure constraints | No | `position_sizing_decisions` |
| `RiskManager` | Enforce portfolio-level risk limits, factor exposure concentration limits, correlation clusters, short-put assignment exposure, and hard reject/reduce rules | No | `portfolio_risk_snapshots`, `risk_factor_exposures`, `option_risk_snapshots` |
| `PaperBroker` | Simulate fills, slippage, commissions, rejects, and order status transitions | No | `paper_orders`, `paper_executions` |
| `PortfolioPipeline` | Maintain positions, cash, exposure, realized/unrealized PnL | No | `paper_positions`, `portfolio_snapshots` |
| `HourlySignalRefreshPipeline` | Refresh intraday signal snapshots hourly for portfolio-relevant tickers, including price/volume, relative strength, VWAP/gap, option marks, news, and freshness checks for low-frequency sources | Optional Gemini Flash bounded classifier only for news/event classification after deterministic filters | `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts` |
| `IntradayRebalancePipeline` | Convert material signal changes and critical/high-impact alerts into reduce/exit/add/hold proposals for existing positions or active candidates | Yes, Gemini Flash bounded decision schema; risk manager remains final gate | `intraday_rebalance_decisions`, `paper_orders` |
| `ReflectionPipeline` | Analyze day results, compare thesis vs outcome, extract learning factors | Yes, highest-quality configured model | `daily_reflections`, `learning_factors` |
| `StrategyEvolutionPipeline` | Convert repeated learning patterns into new strategy proposals, shadow-test them, and promote/retire strategy definitions | Yes for proposal synthesis; deterministic lifecycle gates | `strategy_proposals`, `strategy_definitions`, `strategy_evaluation_results` |

### Model Routing Policy

Most daily LLM calls should optimize for cost, latency, and predictable structured output. Reflection is the exception because it is the highest-leverage reasoning step: it reviews portfolio outcomes, rejected candidates, macro context, risk constraints, and learning-factor impact, then writes lessons that will affect future trading behavior.

Model defaults:

| Runtime Path | Default Model Policy | Reason |
| --- | --- | --- |
| Macro summary, if used | `gemini-2.5-flash` or current Gemini Flash equivalent | Short bounded summary; most logic remains deterministic. |
| Trading decisions | `gemini-2.5-flash` or current Gemini Flash equivalent | Needs fast structured decisions from already-computed candidates/signals. |
| Intraday news classification and rebalance decisions | `gemini-2.5-flash` or current Gemini Flash equivalent | Needs low-latency structured event classification and action proposals. |
| Candidate explanations | `gemini-2.5-flash` or current Gemini Flash equivalent | UI explanation only; candidate scoring remains deterministic. |
| Research audit runs | `gemini-2.5-flash` or current Gemini Flash equivalent unless explicitly overridden | Cost-efficient audit/research path. |
| Post-close reflection | Highest-quality configured model, e.g. `REFLECTION_MODEL_NAME` pointing to the strongest available reasoning model | Reflection generates learning factors that feed back into future trading. |
| Strategy proposal synthesis | Highest-quality configured model, usually the same `REFLECTION_MODEL_NAME` | New strategies change future candidate generation, so quality matters more than latency. |

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
- same-day peer baskets built from sector, industry, theme, market cap, and catalyst type

The key attribution question is not only whether the stock went up. It is whether the selected stock outperformed a reasonable basket of similar alternatives available the same day.

### Bearish Signal Policy

Bearish output is lower trust than bullish catalyst output until proven otherwise. The system should treat bearish evidence in tiers:

| Bearish Evidence Type | Allowed Use |
| --- | --- |
| Direct company-level negative catalyst, e.g. guide-down, accounting issue, failed trial, regulatory action, major customer loss, dilutive offering | May trigger `reduce`, `exit`, `no_trade`, or low-budget bearish/short paper strategy if enabled and price/volume confirm. |
| Sector/theme breakdown with the ticker showing relative weakness vs peers | May reduce position size, reject new longs, or close weak trades. |
| Macro risk-off, VIX, rates, oil, geopolitical risk, broad index weakness | Position sizing and risk-budget input only; not enough for single-name bearish trade. |
| Valuation high, RSI high, stock extended | Risk warning, reduced size, stricter entry, or catalyst-watch; not a high-confidence bearish trade by itself. |

This policy directly addresses the eval failure mode where the model built a long macro chain from “risk-off” to “high-beta semiconductor likely down tomorrow” even while the industry and stock trend stayed strong.

### Trade Identity and Portfolio Pools

Every trade decision must carry a `trade_identity` before sizing:

| Trade Identity | Instrument | Typical Horizon | Sizing / Exit Policy |
| --- | --- | --- | --- |
| `core_holding` | Stock | Multi-month to multi-year | Managed outside the short-term catalyst pool. Bot may recommend pause add, add on pullback, trim for risk budget, or thesis review; it should not liquidate core holdings because of one short-term signal. |
| `catalyst_common_stock` | Stock | Intraday to 1-3 months | Requires explicit catalyst, relative strength, volume/price confirmation, and concrete invalidators. |
| `strong_theme_sell_put` | Cash-secured short put | 2-8 weeks | Used when theme/stock is strong but near-term entry is unclear; requires acceptable assignment plan and worst-case portfolio fit. |
| `valuation_repair_sell_put` | Cash-secured short put | 2-8 weeks | Used for quality software or similar names where valuation repair is plausible but common-stock timing is weak. |
| `catalyst_watch` | No order by default | Event window | Direction uncertain but big move potential is high; shown for human review and later reflection. |
| `ordinary_watch` | No order | N/A | Insufficient actionability; stored for context only. |

The trade identity decides which risk budget applies, which holding-period assumptions are valid, and which exit rules reflection should grade against. Core holdings must have a separate decision pool from short-term catalyst trades.

### Paper Options Strategy Layer

The options layer is V2 paper/simulation-only. It must support these strategy actions:

- `sell_put`: open a cash-secured short put when assignment would be acceptable under the strategy bucket and risk budget
- `close_put`: close an existing paper short put when profit target, risk limit, catalyst invalidator, or earnings rule triggers
- `roll_put`: close the current short put and open a replacement strike/expiry only when the new assignment risk is acceptable
- `avoid_earnings_put`: block opening or rolling short puts through earnings when the event risk exceeds the strategy rule
- `put_assignment_plan`: document what happens if assignment occurs, including whether shares become core, catalyst stock, or immediate reduce/exit candidate

Every short put decision must record:

- `underlying_ticker`
- `strike`
- `expiry`
- `dte`
- `delta`
- `iv_rank` or `iv_percentile`
- `premium`
- `breakeven`
- `assignment_notional`
- `cash_secured_amount`
- `underlying_exposure`
- `earnings_date`
- `assignment_plan`
- `profit_target_pct`
- `max_loss_or_adjustment_rule`
- `roll_conditions`
- `close_conditions`

Options confidence should be calibrated separately from stock confidence. A strong theme without a near-term stock entry can justify `sell_put`, but it should not inherit the same confidence score as a confirmed catalyst stock breakout.

### Strategy Catalog

The first production strategy set should be stored as versioned strategy definitions. The morning scanner evaluates every eligible universe symbol against these definitions, then emits `(ticker, strategy_id, horizon, score, evidence)` candidates. A ticker can match multiple strategies, but `PrimaryStrategySelector` must choose one primary tactical strategy and one strategy bucket before any trade decision so attribution and learning remain clean.

The seed catalog has two layers:

- tactical pattern strategies that explain why a ticker is interesting
- portfolio/option strategy buckets that decide how the system should express the idea

The 15 tactical strategies below are the initial pattern catalog. They are not a fixed universe of possible strategies. Reflection and learning can create new strategy proposals when repeated evidence shows a pattern that is not well captured by the existing catalog.

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

The portfolio/option strategy buckets below are also stored in the strategy catalog so attribution and risk budgets are explicit:

| Strategy Bucket | Strategy ID | Required Context | Typical Horizon | Thesis |
| --- | --- | --- | --- | --- |
| Strong Theme Catalyst Long Stock | `strong_theme_catalyst_long_stock` | Clear bullish catalyst, theme alignment, relative strength vs benchmark/peers, volume/price confirmation | Intraday-3 months | Best expression is common stock because near-term continuation is confirmed. |
| Strong Theme No Clear Near-Term Sell Put | `strong_theme_no_clear_near_term_sell_put` | Strong theme and acceptable underlying, but no clean near-term stock entry; IV/premium attractive; assignment acceptable | 2-8 weeks | Get paid to wait for a strong theme at a better effective entry. |
| Valuation Repair Quality Software Sell Put | `valuation_repair_quality_software_sell_put` | Quality software name, improving valuation/margin/growth narrative, no near-term common-stock trigger; assignment acceptable | 2-8 weeks | Valuation repair can support cash-secured put premium while avoiding weak timing. |
| Core Accumulation On Pullback | `core_accumulation_on_pullback` | Approved core holding, thesis intact, pullback into defined support or risk budget availability | Multi-month+ | Add to core only when the pullback improves risk/reward and portfolio concentration allows it. |

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

## 7. Signal Snapshots

Signals should be deterministic Python outputs and stored before any LLM call. Each signal includes `value`, `direction`, `z_score/percentile` when available, `lookback`, `source`, `source_table` or provider name, freshness metadata, and `computed_at`.

`SignalPipeline` is the V2 replacement for the current version's per-ticker research context assembly. It should not be limited to price/technical indicators. For each ticker it should assemble a replayable `quant_signal_snapshot` from:

- market bars and quote/liquidity data
- normalized insider trading / Form 4 / SEC-derived rows already stored in Postgres
- normalized news, analyst rating, guidance, filing, and catalyst/event rows already stored in Postgres
- fundamentals and valuation data already stored in Postgres
- earnings calendar and known event data
- option-chain derived fields when available
- existing research/global-context artifacts when they are already persisted and have explicit freshness/source metadata

Provider calls are allowed only as controlled refresh/fallback steps, not as hidden prompt-time lookups. If Postgres has stale or missing data, the snapshot must record the missing/stale status and the source that was attempted.

### Signal Groups

| Group | Example Signals |
| --- | --- |
| Momentum / Trend | 5d/20d/60d returns, price vs SMA/EMA, trend slope, new high distance |
| Mean Reversion | RSI 2/3/14, distance from VWAP/SMA, short-term reversal score |
| Volume / Liquidity | relative volume, dollar volume, volume acceleration, spread proxy, liquidity eligibility |
| Volatility / Risk | ATR%, realized volatility, gap size, intraday range, beta proxy, drawdown from recent high |
| Relative Strength | return vs SPY, QQQ, sector ETF, theme ETF, peer basket; rank within sector/theme/peer group |
| Event / Calendar | earnings date distance, post-earnings window, economic calendar risk day |
| Insider / SEC | net insider value, cluster buys, sale concentration, officer/director weight, recent Form 4 freshness |
| News / Sentiment | high-signal news count, analyst rating events, guidance, filing/news freshness, catalyst quality score, direct negative catalyst flags |
| Fundamentals | valuation bands, growth/margin quality, short interest, market cap/liquidity quality filters |
| Options | option chain availability, delta, IV rank/percentile, premium, breakeven, DTE, earnings-through-expiry flag |
| Confidence Calibration | historical win rate/alpha by strategy bucket, direction, catalyst type, sector/theme, and market regime |

首版不需要一次实现所有信号，但 schema 要允许增量添加。缺失信号必须显式保存为 `null` 或 `status=missing`，不能在 prompt 中伪造。

Signal source rules:

- Prefer normalized Postgres tables over ad hoc live fetches so every trading decision is replayable.
- Preserve source provenance per signal, e.g. `market_bars`, `insider_transactions`, `sec_filings`, `news_articles`, `fundamental_snapshots`, `earnings_events`, `option_chain_snapshots`, or `research_context`.
- Store `as_of`, `published_at`, `filing_date`, or equivalent freshness fields where relevant.
- Separate raw inputs from derived scores. For example, persist raw insider transactions elsewhere, then store derived fields such as `insider_net_buy_value_90d` and `insider_cluster_buy_count_90d` in `signal_snapshots`.
- Do not let the LLM infer missing insider/news/fundamental facts. Missing facts remain missing signals.

### Required Signal Families For Strategy Matching

The signal schema should explicitly support the strategy catalog above:

- Catalyst signals: `fresh_catalyst_type`, `catalyst_published_at`, `catalyst_strength_score`, `beat_raise_flag`, `guidance_revision_score`, `analyst_revision_count`, `direct_negative_catalyst_type`.
- Insider / SEC signals: `insider_net_buy_value_30d`, `insider_net_buy_value_90d`, `insider_cluster_buy_count_90d`, `officer_buy_flag`, `director_buy_flag`, `sale_concentration_score`, `recent_form4_filing_at`, `sec_filing_event_type`.
- News / analyst signals: `high_signal_news_count_24h`, `high_signal_news_count_7d`, `analyst_upgrade_count_30d`, `analyst_downgrade_count_30d`, `price_target_revision_score`, `guidance_news_flag`, `customer_order_news_flag`, `regulatory_news_flag`, `news_freshness_minutes`.
- Fundamental signals: `revenue_growth_score`, `margin_trend_score`, `valuation_percentile`, `ev_sales_percentile`, `fcf_margin_score`, `quality_score`, `short_interest_pct_float`, `market_cap_bucket`.
- Gap/VWAP signals: `opening_gap_pct`, `premarket_gap_pct`, `vwap_reclaim`, `vwap_hold`, `opening_range_high_break`, `opening_range_low_break`, `gap_fill_pct_remaining`.
- Breakout/base signals: `resistance_break_score`, `base_duration_days`, `price_near_52w_high_pct`, `new_high_break`, `breakout_volume_confirmed`.
- Trend/pullback signals: `trend_slope_20d`, `price_vs_sma_20`, `price_vs_sma_50`, `pullback_depth_pct`, `support_reclaim_score`, `selling_volume_dry_up`.
- Volatility compression signals: `atr_pct`, `realized_volatility_percentile`, `range_compression_percentile`, `squeeze_score`, `range_break_direction`.
- Relative strength signals: `rs_vs_spy_20d`, `rs_vs_qqq_20d`, `rs_vs_sector_20d`, `rs_vs_theme_etf_20d`, `rs_vs_peer_basket_20d`, `sector_rank_percentile`, `peer_rank_percentile`, `rotation_score`.
- Mean reversion signals: `rsi_2`, `rsi_3`, `rsi_14`, `distance_from_sma_20_pct`, `capitulation_volume_score`, `reversal_triggered`.
- Short squeeze signals: `short_interest_pct_float`, `days_to_cover`, `borrow_fee_proxy`, `float_rotation_proxy`, `squeeze_pressure_score`.
- Sympathy signals: `leader_ticker`, `leader_catalyst_type`, `peer_link_strength`, `industry_move_pct`, `laggard_confirmation_score`.
- Event timing signals: `earnings_in_days`, `known_event_date`, `pre_event_runup_score`, `event_risk_flag`.
- Options signals: `put_strike`, `put_expiry`, `put_dte`, `put_delta`, `put_iv_rank`, `put_premium`, `put_breakeven`, `assignment_notional`, `cash_secured_amount`, `earnings_before_expiry`.
- Confidence calibration signals: `historical_strategy_win_rate`, `historical_strategy_alpha_vs_benchmark`, `historical_direction_win_rate`, `historical_catalyst_type_alpha`, `confidence_calibration_bucket`.

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
| Hourly 10:00-15:00 | Intraday signal refresh + news scan | `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts`, possible rebalance proposals |
| Immediately after material signal change or critical/high alert | Intraday rebalance | approved/reduced/rejected `intraday_rebalance_decisions`, possible paper orders |
| 15:55 | Optional risk check | staged close/rebalance decisions if enabled |
| 16:05 | Portfolio mark | `portfolio_snapshots`, trade PnL |
| 16:20 | Daily reflection | `daily_reflections` |
| 16:40 | Learning factor update | `learning_factors`, next-run context |
| 16:50 | Strategy evolution | `strategy_proposals`, candidate/shadow strategy updates |

Manual runs remain available for debugging, but scheduled daily flow is the primary product path.

Morning workflow semantics:

1. Scan the configured universe before the open and compute all available pre-market/daily signals.
2. Match each symbol against tactical strategies and portfolio/option strategy buckets. Each match carries its own strategy horizon, required evidence, and invalidators.
3. Build benchmark and peer-basket context for each candidate so relative strength is measured against the right opportunity set, not only `SPY`.
4. Rank candidate scores by strategy fit, catalyst quality, relative strength, signal quality, macro compatibility, liquidity, confidence calibration, and learning-factor adjustments.
5. Select one primary tactical strategy and one strategy bucket for each ticker/action under consideration.
6. Classify each selected candidate or existing position into a trade identity before any order decision.
7. Build an option instrument plan only when the selected strategy bucket and trade identity make an option expression eligible.
8. Pass only the selected candidates plus current positions and paper short puts into `TradingPipeline`.
9. `TradingPipeline` proposes an action, thesis, invalidators, suggested size, horizon, instrument expression, and trade identity.
10. Deterministic risk constraints and portfolio budget decide whether the proposed action becomes a staged paper stock order, staged paper option order, is reduced, or is rejected.

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
PrimaryStrategySelector chooses selected strategy and strategy bucket
      |
      v
TradeClassifier assigns trade identity
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
- short-put worst-case assignment risk
- portfolio concentration limits

Manual request outcomes are important reflection inputs. The system should later compare user-pinned tickers against bot-selected candidates to learn whether the scanner missed valid opportunities or correctly ignored weak ideas.

### Intraday Signal Refresh, News Scan, and Rebalance

During regular trading hours, the system runs an hourly intraday refresh. It should scan news and refresh all signal families that can materially change intraday for portfolio-relevant tickers. The initial scope should include:

- open paper positions
- tickers with staged orders or same-day trades
- top active candidates from the morning scan
- active manual/pinned review tickers
- high-impact market/sector news from the provider feed

If provider limits allow, the scan can also query broader universe signals/news, but the first production path should prioritize portfolio-relevant names so it can react quickly without excessive API usage.

Hourly refresh should update:

- intraday price/volume/liquidity signals: VWAP hold/reclaim, opening range break, relative volume, spread proxy, gap fade/fill, intraday range, ATR-relative move
- relative strength signals: ticker vs `SPY`, `QQQ`, sector/theme ETF, and peer basket since open and since prior close
- option signals for open paper puts and eligible candidates: mark, delta, IV move if available, DTE, breakeven distance, assignment-risk delta
- news/event signals: new company news, analyst revisions, guidance, filings, direct negative catalyst flags, high-impact market/sector news
- low-frequency source freshness: insider/SEC/fundamentals/earnings-calendar records should be checked for newly available rows or staleness, not blindly recomputed from scratch each hour

Each hourly run stores an `intraday_signal_snapshot` with signal deltas vs the morning snapshot and previous intraday snapshot. Rebalance should trigger from material signal changes even when no new headline exists.

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
- `close_put`: close paper short put because thesis, earnings risk, or assignment risk changed.
- `roll_put`: roll paper short put only if the replacement contract improves risk and still passes worst-case assignment checks.
- `avoid_earnings_put`: block any new or rolled short put when event risk is not explicitly acceptable.

Intraday rebalance is still gated:

1. `HourlySignalRefreshPipeline` refreshes intraday signal snapshots, computes deltas, dedupes news/events, and classifies alerts.
2. `IntradayRebalancePipeline` proposes action with signal/news evidence and urgency.
3. `PositionSizer` recalculates target size.
4. `RiskManager` applies factor exposure and concentration limits.
5. `PaperBroker` simulates any approved order.

This loop must persist rejected and no-action alerts. They are important for reflection: the system should learn whether it ignored useful news, overreacted to noise, or correctly protected the portfolio.

## 9. Trading Decision Contract

The trading agent receives:

- selected candidates with full signal snapshots, candidate score context, primary strategy, strategy bucket, and trade identity
- manual request context for user-pinned tickers, including mode, reason, and source
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
  "strategy_bucket_id": "strong_theme_catalyst_long_stock",
  "trade_identity": "catalyst_common_stock",
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
- `sell_put`
- `close_put`
- `roll_put`
- `avoid_earnings_put`
- `put_assignment_plan`

Risk checks run before order creation. If risk checks fail, no paper order is created even if the LLM decision is actionable.

For option decisions, the trading decision must include an `option_plan` object with strike, expiry, DTE, delta, IV rank/percentile, premium, breakeven, assignment notional, cash-secured amount, earnings date, roll/close conditions, and assignment plan. Missing option-chain data should produce `no_trade` or `catalyst_watch`, not a fabricated option plan.

`time_horizon` should come from the selected strategy definition, not from a global default. The trading agent may shorten or skip a trade if risk conditions conflict with the strategy horizon, but it should not silently rewrite the strategy's typical horizon without recording a reason.

Confidence must be calibrated by historical pattern quality. Bullish catalyst plus relative strength can earn high confidence when past evidence supports it. Macro-only bearish, valuation-only bearish, RSI-only bearish, or “stock is extended” reasoning must remain low confidence and should normally map to risk warning, smaller size, no trade, or watch.

### Risk Constraint and Budget Decision

The final action is computed in two stages:

1. `TradingPipeline` proposes `decision`, `suggested_target_weight`, `time_horizon`, instrument expression, thesis, and invalidators.
2. `RiskManager` applies deterministic constraints and returns `approved`, `reduced`, or `rejected`.

Risk decision fields:

- `portfolio_cash_available`
- `gross_exposure_before` and `gross_exposure_after`
- `strategy_budget_remaining`
- `macro_budget_multiplier`
- `factor_exposure_before` and `factor_exposure_after`
- `worst_case_assigned_exposure_before` and `worst_case_assigned_exposure_after`
- `remaining_factor_budget_by_type`
- `binding_factor_limits`
- `option_assignment_notional`
- `cash_secured_requirement`
- `position_limit_check`
- `liquidity_check`
- `stale_signal_check`
- `learning_factor_adjustments`
- `final_action`: `create_order`, `reduce_size_create_order`, or `reject`
- `risk_rejection_reason`

## 10. Paper Trading and Risk

### Paper Broker Rules

- Default execution model: market-on-open for planned entries, close price for end-of-day exits.
- Stock and option simulations can share order-state semantics, but option fills must stay paper-only and use explicit option-chain data or fixture data.
- Slippage model: configurable bps by liquidity bucket.
- Commission model: configurable flat or zero.
- Fill rejection if price, volume, or market data is missing.
- Option fill rejection if strike, expiry, bid/ask/mark, delta, IV rank/percentile, or earnings date data required by the strategy is missing.
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

### Short Put Assignment Risk

For paper short puts, risk must be evaluated as if assignment can happen. The risk manager should calculate both:

- current portfolio exposure: stock positions plus marked option positions
- worst-case assigned portfolio: current stock positions plus all short puts converted into long stock at their strikes

The worst-case assigned portfolio is the primary control for `sell_put` and `roll_put`. A trade is rejected or reduced if simultaneous assignment would create unacceptable concentration, even if current stock exposure looks safe.

Required assignment metrics:

- assignment notional by ticker
- cash-secured amount by contract and total portfolio
- breakeven exposure by ticker
- sector/theme/industry exposure after assignment
- high-beta AI/semis/space exposure after assignment
- strategy bucket exposure after assignment
- correlation-cluster exposure after assignment
- earnings-through-expiry flag and event-risk exposure

Example assignment question the risk manager must answer:

```text
If every open short put is assigned at strike, does the portfolio become an over-concentrated high-beta AI/semiconductor/space book?
```

If yes, the system can propose `avoid_earnings_put`, `close_put`, `roll_put` to a lower-risk contract, reduce new common-stock exposure, or reject new short puts.

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
| Option assignment | short-put assignment notional, breakeven exposure, cash-secured requirement | Avoid hidden long exposure that appears only after assignment. |

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
- Short-put assignment notional cap by ticker, sector/theme, strategy bucket, and correlation cluster.
- Cash-secured requirement cap so paper puts cannot overcommit available cash.
- Earnings-through-expiry rule for short puts, with `avoid_earnings_put` as the default when event risk is not explicitly accepted.
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
  "max_correlation_cluster_weight": 0.25,
  "max_short_put_assignment_notional_pct": 0.35,
  "max_single_name_assigned_weight": 0.10,
  "max_theme_assigned_weight": {
    "ai_semis": 0.30,
    "space": 0.15
  },
  "max_cash_secured_put_commitment_pct": 0.50
}
```

The risk manager must persist both accepted and rejected decisions. Rejected trades are important training data for reflection because the system should learn whether risk constraints protected the portfolio or blocked good opportunities.

## 11. Reflection and Learning Loop

Reflection runs after the portfolio is marked to close. It receives:

- morning macro snapshot
- strategy candidates and scores
- trading decisions and rejected decisions
- intraday news alerts and rebalance decisions
- paper orders/executions
- end-of-day PnL, benchmark return, sector return
- peer-basket returns and relevant ETF returns, e.g. `QQQ`, `SMH`, `SOXX`
- paper option positions, short-put lifecycle actions, and worst-case assignment snapshots
- per-trade MFE/MAE if available
- invalidators and whether they triggered
- prior learning factors used

Reflection should evaluate the portfolio, not just individual research calls. The main questions are:

- Did bullish catalyst trades outperform the relevant ETF and peer basket, or only ride a sector tailwind?
- Did bearish or risk-off reasoning actually add value, or did it incorrectly suppress strong-trend names?
- Were high-confidence calls calibrated by historical pattern quality, or did narrative completeness inflate confidence?
- Did `neutral/watch` hide a catalyst-watch opportunity with large move potential?
- Did short-put trades have acceptable assignment risk, and would assignment have improved or damaged portfolio construction?
- Did the selected strategies perform as expected for their horizons?
- Did risk constraints prevent losses or block profitable opportunities?
- Were skipped candidates better than selected trades?
- Did intraday news alerts trigger useful rebalances, or did the system overreact/underreact?
- Did macro regime constraints help or hurt?
- Was the portfolio too concentrated in any sector, strategy, horizon, beta, volatility, liquidity, event, macro, or correlation factor?
- Did factor concentration explain more PnL than ticker selection?
- Did active learning factors improve decisions, overfit, or become stale?
- Are there repeated profitable or avoided-loss patterns that deserve a new trading strategy rather than another one-off learning factor?

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

Reflection may also emit `strategy_proposal_hints`: partial observations that are not yet complete strategy definitions. `StrategyEvolutionPipeline` owns converting those hints into concrete strategy proposals so reflection stays focused on evidence and attribution.

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
| `manual_ticker_requests` | User-pinned tickers that must be evaluated, including reason, mode, expiry, status, and linked result |
| `macro_snapshots` | One macro snapshot/regime per run/day |
| `signal_snapshots` | Per ticker per day quant features and normalized signal JSON |
| `strategy_definitions` | Versioned strategy metadata, required signals, horizon, scoring config, invalidators |
| `strategy_proposals` | Proposed new strategies or revisions derived from reflection/learning, including lifecycle status and evidence |
| `strategy_evaluation_results` | Shadow/experimental performance and promotion/retirement evidence for strategy definitions |
| `strategy_runs` | One candidate-scoring batch per day |
| `candidate_scores` | Ranked ticker candidates by strategy, horizon, evidence, macro compatibility |
| `trade_classifications` | Trade identity, portfolio pool, strategy bucket, intended horizon, and exit-policy metadata for each candidate/position decision |
| `trading_decisions` | Trading agent decisions and context snapshot |
| `option_strategy_decisions` | Paper-only option strategy actions such as sell/close/roll/avoid/assignment plan with required option metadata |
| `paper_option_orders` | Staged/submitted/filled/rejected simulated option orders |
| `paper_option_positions` | Current simulated option position state, including short puts |
| `option_risk_snapshots` | Current and worst-case-assigned short-put exposure snapshots |
| `intraday_signal_scans` | Hourly intraday refresh metadata, status, provider coverage, ticker scope, and error state |
| `intraday_signal_snapshots` | Per ticker intraday signal values and deltas vs morning/previous snapshot |
| `news_alerts` | Normalized positive/negative news alerts with severity, sentiment, dedupe key, affected tickers/positions |
| `intraday_rebalance_decisions` | Alert-driven hold/reduce/exit/add/open_new proposals and final risk-gated outcome |
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
| `llm_usage_events` | Per LLM/API call telemetry: provider, model, pipeline, run id, token counts, estimated cost, latency, retry/error state, prompt/schema version |

Existing tables remain useful:

- `watchlists` becomes a manual override list, not the source of truth for daily scan.
- Manual watchlist/pinned symbols create `manual_ticker_requests`; they are evaluated through the same signal/strategy/risk path as scanner candidates.
- `research_runs` and `research_outputs` can remain as explanatory research artifacts, but trading decisions should use dedicated `trading_decisions` rows so research/eval history does not get overloaded.
- `eval_results` remains for research output scoring; trade/portfolio scoring should move to paper trading tables.

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

Portfolio/option strategy buckets use the same table with `strategy_layer = "expression_bucket"` and include fields such as `allowed_trade_identities`, `allowed_instruments`, `required_assignment_fields`, `earnings_policy`, and `default_exit_policy`.

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
- current NAV, day PnL, benchmark return, gross exposure, cash
- critical/high alerts and material signal-change count
- macro regime, clearly labeled as macro-only
- risk budget, factor exposure usage, and blocked strategy tags
- current LLM/API cost estimate for the day

Tabs:

1. `Overview`
   - Compact operator summary: NAV, day PnL, cash, gross/net exposure, risk budget used, critical alerts, material signal changes, open action items, and job status.
   - This tab should answer: “Do I need to pay attention right now?”

2. `Portfolio`
   - Current stock positions, paper short puts, core vs tactical pools, cash, exposure, unrealized/realized PnL.
   - Include trade identity, selected strategy, holding age, invalidator status, current risk tags, and worst-case assigned exposure for paper short puts.

3. `Trades`
   - Every same-day trade decision, including executed trades, rejected trades, reductions, exits, `sell_put`, `close_put`, `roll_put`, and no-trade decisions that reached `TradingPipeline`.
   - Each row shows time, ticker, action, instrument, trade identity, selected strategy, strategy bucket, proposed size, final size, fill/order status, confidence, and reject/reduction reason.
   - Every trade row must open a detail view with the complete audit trail:
     - multi-source signal snapshot
     - intraday signal deltas if relevant
     - multi-strategy candidate scores
     - selected primary strategy and strategy bucket
     - trade identity and instrument plan
     - LLM decision JSON and prompt/schema version
     - confidence basis and calibration bucket
     - risk manager approval/reduction/rejection details
     - paper order/fill state
     - exit plan and invalidators
     - post-close outcome once available

4. `Risk & Macro`
   - Macro regime, macro risk budget multiplier, blocked strategy tags, macro invalidators, and economic-calendar risk.
   - Portfolio risk exposures by sector/industry, theme, strategy, horizon, direction, beta, volatility, liquidity, event/catalyst type, macro sensitivity, and correlation cluster.
   - Paper options assignment view: if all short puts are assigned, show resulting ticker, sector/theme, high-beta AI/semis/space, correlation-cluster, and cash-secured exposure.
   - Show binding limits and which proposed trades were reduced or rejected by each limit.

5. `Candidates`
   - Bot-selected candidates that were not traded, manually pinned tickers, `catalyst_watch`, and `ordinary_watch`.
   - Split scanner-selected from manual-only candidates.
   - Show why skipped: missing/stale data, no catalyst, weak relative strength, poor price/volume confirmation, macro size reduction, risk block, `review_only` mode, or options metadata missing.
   - Each candidate should be drillable to the same signal/strategy/risk context used by the trade detail view, even when no order was created.

6. `Learning & Strategies`
   - Learning factors, active/suppressed/retired status, source reflection, scope, confidence, and whether they tightened candidate scoring or risk.
   - Strategy catalog with lifecycle: active, shadow, experimental, retired.
   - Strategy performance table:
     - trade count and sample size
     - win rate
     - total PnL and average PnL
     - average alpha vs `SPY`, `QQQ`, sector/theme ETF, and peer basket where available
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
- Current positions and paper short puts appear in `Portfolio`.
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
- Missing provider data should degrade the relevant signal to missing, not fabricate values.
- Candidate scoring skips tickers without minimum required signals.
- Candidate scoring must separate `ordinary_watch` from `catalyst_watch` so high-volatility catalyst opportunities are not lost in neutral output.
- Manual ticker requests that fail ticker validation, data availability, or liquidity checks should return `blocked_by_missing_data` or `no_trade`; they should not create partial fabricated snapshots.
- `review_only` manual requests must never create paper orders even when the trading decision is actionable.
- Strategy proposals must not mutate active strategy definitions directly. They create candidate/shadow strategy definitions through explicit lifecycle transitions.
- Macro-only bearish context must not create single-name bearish trades; if it affects a candidate, the persisted decision should show risk-budget reduction or no-trade reason.
- Short-put decisions with missing option-chain, earnings date, or assignment-risk inputs must be rejected or downgraded to watch.
- Intraday signal snapshots must preserve deltas vs the morning signal snapshot and previous hourly snapshot.
- News alerts must be deduped by ticker/event/source/time window so repeated headlines do not trigger repeated rebalances.
- Intraday rebalance decisions must persist the triggering `news_alert_id`, proposed action, final action, and risk decision.
- Trading decisions must persist full context snapshots: candidate signals, macro snapshot id, portfolio snapshot id, risk config version, strategy version, learning factors used.
- Option decisions must persist full option metadata and assignment-risk snapshot used at decision time.
- Paper orders must be idempotent per `trade_date + ticker + strategy_id + decision_type`.
- A failed ticker must not abort the whole universe scan.
- Reflection failure must not mutate learning factors.
- Intraday signal/news refresh failure must not block portfolio marking or post-close reflection.

## 15. Testing and Smoke Tests

Unit tests:

- signal computations
- universe filters
- manual ticker request validation, expiry, mode handling, and source attribution
- macro regime classification
- strategy candidate scoring
- trade identity classification
- relative-strength benchmark and peer-basket attribution
- confidence calibration by strategy bucket and direction
- bearish signal gating so macro-only bearish evidence cannot create a single-name short
- risk checks
- paper option strategy decision validation
- short-put assignment exposure calculation
- news alert dedupe and severity classification
- intraday signal delta detection and material-change thresholds
- intraday rebalance action gating
- factor exposure calculation
- concentration limit enforcement
- position sizing and size-reduction reasons
- paper order state transitions
- portfolio PnL calculations
- learning factor activation rules
- strategy proposal validation and duplicate detection
- strategy lifecycle transition rules
- web route rendering for today/trades/reflections

Smoke tests:

- standalone market data smoke for universe + signal computation
- standalone smoke for a tiny manual ticker request in `review_only` mode
- standalone intraday signal/news refresh smoke for a tiny fixed ticker set or fixture mode
- standalone DB smoke for writing signal/candidate/order/portfolio rows
- standalone DB smoke for writing portfolio risk snapshots and risk factor exposures
- standalone DB smoke for writing paper option decisions and assignment-risk snapshots
- optional live paper-trade dry run that uses a tiny ticker set and does not consume large API quota

Implementation must continue to use `source ~/.venv/bin/activate` before Python commands and must verify Postgres data directory is on persistent disk for deployment work.

## 16. Phased Delivery

### Phase 1: Foundation

- Add data model for universe, signals, macro snapshots, strategy definitions, candidate scores.
- Implement universe refresh and deterministic signal snapshots.
- Add manual ticker request ingestion and pinned-review signal snapshots.
- Seed the initial strategy catalog with tactical strategies plus portfolio/option strategy buckets.
- Add trade identity taxonomy and confidence-calibration fields.
- Add candidate scanner UI.

### Phase 2: Paper Trading

- Add trading decisions, paper orders, executions, positions, portfolio snapshots.
- Implement position sizing, risk checks, factor exposure caps, budget allocation, and paper broker.
- Add paper/simulation-only option strategy decisions and paper short-put lifecycle state.
- Evaluate current and worst-case assigned portfolio before approving any short put.
- Replace homepage with `/today` trading dashboard.

### Phase 3: Intraday Signal Refresh, News Alerts, and Rebalance

- Add hourly intraday signal scan metadata, intraday signal snapshots, and normalized alert tables.
- Refresh intraday price/volume/relative-strength/options/news signals for open positions, top candidates, and pinned review tickers.
- Classify positive/negative high-impact events for open positions and top candidates.
- Trigger intraday rebalance proposals for material signal changes or critical/high alerts.
- Gate every alert-driven action through `PositionSizer`, `RiskManager`, and `PaperBroker`.
- Persist no-action/rejected alerts for post-close reflection.

### Phase 4: Reflection

- Add post-close reflection agent and `daily_reflections`.
- Generate learning factors with lifecycle statuses.
- Reflect on benchmark/peer-basket outperformance, bullish vs bearish signal quality, and confidence calibration.
- Reflect on paper options outcomes and assignment-risk decisions.
- Show reflection and learning factors in UI.

### Phase 5: Learning Injection

- Inject active learning factors into `TradingPipeline`.
- Persist learning factor applications.
- Evaluate whether factors improved strategy outcomes.

### Phase 6: Strategy Evolution

- Generate new strategy proposals from repeated reflection/learning patterns.
- Add candidate/shadow strategy lifecycle states.
- Run shadow strategies during scans without allowing them to place paper orders.
- Promote strategies to experimental/active only when evidence and risk checks pass.
- Show strategy proposals and lifecycle status in UI.

### Phase 7: Strategy Expansion

- Add more strategy definitions and signal groups.
- Add macro-aware strategy blocking and risk-budget adjustment.
- Add richer attribution across ticker, strategy, sector, and macro regime.
- Add richer operational telemetry for LLM/API usage and provider costs if the basic `Ops & Cost` tab shows recurring bottlenecks.

## 17. Acceptance Criteria

1. A scheduled run can scan a configured US equity universe without relying on watchlist entries.
2. The system stores replayable quant signal snapshots for every scanned candidate.
3. A user can pin a ticker for `review_only` or `paper_trade_eligible` manual evaluation even if the scanner did not select it.
4. Manual ticker review uses the same signal snapshot, strategy matching, trade classification, confidence calibration, and risk path as scanner candidates.
5. `review_only` manual requests never create paper orders, and `paper_trade_eligible` requests only create paper orders after normal risk checks pass.
6. Macro snapshot/regime is stored separately from stock strategy inputs.
7. Strategy pipeline evaluates the initial strategy catalog and stores strategy-specific candidate score, evidence, invalidators, and typical horizon.
8. The morning trade plan selects ticker, strategy, strategy bucket, trade identity, horizon, action, target exposure, and risk budget used before the market opens.
9. Trading pipeline creates paper orders only after risk checks and budget allocation pass.
10. Position sizing records base size, volatility adjustment, liquidity cap, remaining factor budget, final size, and binding constraints.
11. Portfolio risk snapshots show factor exposure by sector, strategy, horizon, beta, volatility, liquidity, event type, macro sensitivity, correlation cluster, and short-put assignment exposure.
12. Risk manager reduces or rejects trades that would make the current or worst-case assigned portfolio too concentrated in any configured risk factor.
13. Paper portfolio shows positions, trades, exposure, and day PnL.
14. Paper options layer records `sell_put`, `close_put`, `roll_put`, `avoid_earnings_put`, and `put_assignment_plan` actions with strike, expiry, DTE, delta, IV rank, premium, breakeven, assignment notional, cash secured amount, underlying exposure, and earnings date.
15. Macro-only bearish context cannot create high-confidence single-name bearish trades; it can only reduce size, block strategy tags, or add risk warnings unless direct company-level negative evidence exists.
16. Confidence displays and persistence distinguish historically strong bullish catalyst patterns from weak bearish/macro narratives.
17. Watch output distinguishes `ordinary_watch` from `catalyst_watch`.
18. Hourly intraday refresh creates signal snapshots, material signal-change deltas, and deduped positive/negative alerts for open positions, same-day trades, top candidates, active manual review tickers, and high-impact market/sector events.
19. Critical/high alerts can trigger immediate risk-gated `hold/reduce/exit/add` rebalance decisions, with `open_new` disabled by default unless the ticker was already a morning candidate or override.
20. Post-close reflection analyzes portfolio returns, benchmark/peer-basket returns, selected trades, rejected candidates, manual ticker requests, intraday alerts, rebalance outcomes, macro constraints, factor concentration, paper option decisions, confidence calibration, and learning-factor impact.
21. Strategy evolution can create new strategy proposals from repeated learning patterns without being limited to the initial seed strategies.
22. New strategies enter `candidate` or `shadow` status first, and cannot create paper orders until promoted to `experimental` or `active`.
23. Active learning factors are visible in UI, injected into later trading decisions, and tracked through `learning_factor_applications`.
24. `/today` is a tabbed trading workstation with `Overview`, `Portfolio`, `Trades`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, and `Ops & Cost` tabs.
25. Trade detail views show complete audit trails: signal snapshots, strategy scores, selected strategy, trade identity, LLM decision JSON, risk decision, order/fill state, exit plan, invalidators, and post-close outcome.
26. `Ops & Cost` shows LLM/API usage, model/provider, tokens, estimated cost, latency, retry/error state, and prompt/schema version by pipeline and run.
27. Existing research run audit pages continue to work.

## 18. Open Questions

1. Universe scope: all US listed common stocks, or only a liquidity-filtered subset such as price > $5 and dollar volume > configurable threshold?
2. Long-only common stock first, or include direct short paper trades from V2 behind a disabled-by-default flag?
3. Holding period: strictly intraday close-out, 1-5 day swing paper trades, or both with separate strategy tags?
4. Should learning factors auto-activate immediately, or require approval for the first few weeks?
5. Should manual ticker requests expire at end of day by default, or stay active until manually dismissed?
