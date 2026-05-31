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
5. 引入 paper trading：每天根据策略和风险规则生成 orders，在同一个 simulated margin account 里更新 stock/options positions、trades、PnL、margin usage 和 buying power。
6. 常规交易时段每小时扫描新闻，盘前和盘后再额外扫描一次，识别高影响正面/负面事件，并在风险约束下立即触发调仓或退出。
7. 在 reflection 之前运行 historical replay / outcome evaluator，按策略 horizon 评估候选和已交易标的相对 `SPY`、`QQQ`、sector/theme ETF、decision-time peer basket 的表现。
8. 每天收盘后自动 reflection，归因当天交易表现，并生成结构化 learning factors 和 strategy proposals。
9. 下一次 trading agent 决策时只注入经过验证或只会收紧风险的 active learning factors；reflection 新生成的扩大仓位、提高分数或放宽准入规则默认进入 candidate/shadow/test，不直接改变交易行为。
10. UI 首页改为交易工作台，重点显示当天持仓、当天 trades、live alerts、收盘反思、learning factors 和 strategy evolution。
11. 明确分离 `Macro Engine` 与 `Stock Trading Strategy Engine`。
12. 先验证相对行业、主题、同类股票和成交量/价格结构，再找明确个股，最后决定是否交易。
13. 每个交易必须先归类为核心仓、tactical stock trade、tactical option trade、risk hedge overlay、watch-only 等 trade identity，并由这个身份决定仓位、持有周期、退出规则和反思口径。
14. 核心仓必须由上游 `portfolio_intents` 配置批准，包含 approved core tickers、target/max weight、add/trim rules 和 thesis invalidators；`core_holding` trade identity 只说明 exposure purpose，不负责决定哪些股票可以成为核心仓。
15. 增加 paper/simulation-only options strategy layer，但 V2 初始白名单先限制在 long call、long put、call/put credit spread、long straddle 和 long strangle。Standalone short put、covered/collar、debit spread 和其他 multi-leg 组合先不进入初始交易范围。
16. Risk manager 必须用 leg-based option risk 评估 delta/gamma/theta/vega、max loss、margin requirement、buying power effect、event risk；对 credit spread 或未来其他可能 assignment 的结构，额外用 worst-case assigned portfolio 评估风险，而不是只看当前股票仓位。
17. Confidence 必须按 historical replay/outcome evaluator 的 pattern 和策略桶校准，不能因为叙事完整或宏观理由多就给高分。
18. 支持用户手动 pin ticker 让 trading bot 强制评估，但 manual request 只代表“必须评估”，不代表“允许交易”。

## 3. Non-Goals

- 不接入真实券商下单，V2 只做 paper trading。
- 不做高频或分钟级自动交易。首版以 daily pre-market plan、market-open execution simulation、post-close reflection 为主。
- 不做 direct short common-stock paper trades。V2 common-stock orders are long-only; bearish evidence can reduce, block, downgrade to watch, or support paper option/risk-hedge expressions where explicitly allowed by strategy and risk rules.
- 不让 LLM 直接执行 broker/order/database side effects。Python orchestration 仍然拥有状态流转和持久化。
- 不把 reflection 生成的 learning factors 默认当作 active trading rules。扩大仓位、提高分数、放宽准入、扩大 universe 或提高风险预算的学习结果必须先进入 candidate/shadow/test；只有收紧风险、降低仓位、增加 blocked condition 的规则可以自动 active。
- 不让新生成的 strategy 直接扩大组合风险。自动发现的 strategy 必须先进入 candidate/shadow lifecycle，并受更小的 strategy/risk budget 约束。
- 不让新闻情绪单独绕过风险管理。Intraday 新闻只能触发有审计的 rebalance proposal，最终仍由 `RiskManager` 和 `PaperBroker` 执行。
- 不把宏观新闻直接混入每个 ticker prompt 里做随意推理。宏观只通过结构化 macro snapshot/regime 进入个股策略和交易 agent。
- 不因为宏观 risk-off、估值高、RSI 高、VIX 上升等单独理由生成单票做空或高 confidence bearish trade。除非有直接公司级负面 catalyst 和价格/成交量确认，否则 bearish 结论只能作为风险提示、减仓或暂停加仓依据。
- 不让短线 catalyst 信号直接驱动核心仓卖出。核心仓由独立的风险预算、加仓/暂停加仓规则和 thesis invalidation 管理。
- Stock 和 options 在 V2 共用同一个 simulated margin account。股票正股交易也消耗 margin/buying power，不单独假设 cash-only account；期权初始只模拟 long call、long put、call/put credit spread、long straddle 和 long strangle，默认按 margin account / buying power 约束建模，不要求 cash-secured 或 security-secured；但必须记录每条 leg、组合级风险、max loss、margin requirement、buying power effect 和 event risk。
- 不让手动 pin 的 ticker 绕过 liquidity、missing data、risk manager、option risk、assignment risk 或 bearish gating。手动 pin 只是 evaluation source，不是 trade approval。

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

结论：采用 Option A，但首版 MVP 不直接实现完整交易平台。先跑通 universe -> point-in-time signal snapshot -> strategy scoring -> historical replay/outcome evaluator，证明候选生成和策略评分能被无未来数据地回放和评估；再逐步加入 paper trading、options、intraday refresh、reflection 和 strategy evolution。保留当前“Python owns orchestration, LLM owns bounded reasoning”的原则，把系统拆成可审计的 daily trading layers。

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
RiskConfigResolver -> generated effective risk config from risk_appetite preset
      |
      v
PositionSizer + RiskManager -> approved/reduced/rejected final action, including option-risk and worst-case assignment checks
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
HistoricalReplayOutcomeEvaluator -> candidate/trade outcomes by strategy horizon
      |
      v
ReflectionPipeline -> daily_reflections -> learning_factors
      |
      v
StrategyEvolutionPipeline -> strategy_proposals -> strategy_definitions
      |
      v
Next trading run receives validated active learning_factors
```

### Component Boundaries

| Component | Responsibility | LLM? | Persistence |
| --- | --- | --- | --- |
| `UniverseProvider` | Load daily tradable US equity universe from market data provider, normalize tickers, and apply user-editable liquidity, sector, exchange, and asset filters | No | `universe_filter_configs`, `universe_symbols`, `universe_snapshots` |
| `ManualTickerReviewPipeline` | Accept user-pinned tickers for forced evaluation, validate basic eligibility, attach request reason/mode, and merge them into signal/strategy evaluation without granting trade approval | No | `manual_ticker_requests`, `universe_symbols`, `signal_snapshots` |
| `SourceIngestionJobs` | Supporting scheduled/targeted data ingestion layer that keeps normalized Postgres source tables fresh for insider/Form 4, SEC filings, news/analyst events, fundamentals, market data, option chains, earnings/events, and macro calendars. These jobs do not make trading decisions; they only provide point-in-time replayable source rows, provider health, request-budget, and freshness metadata for downstream pipelines | No | source-specific tables, `source_ingestion_runs`, `provider_request_runs` |
| `MacroPipeline` | Fetch rates, VIX, credit spreads, commodities, broad index trend, economic calendar; consume macro/sector/theme read-through context; produce market regime | Optional bounded summary using Gemini Flash | `macro_snapshots` |
| `PortfolioEventCalendarPipeline` | Normalize future macro, economic, earnings, Fed, and company events; score relevance/risk against current holdings, candidates, option expiries, and strategy holding periods; hide irrelevant low-impact events from the UI | No | `calendar_events`, `portfolio_event_risk_assessments` |
| `SignalPipeline` | Build deterministic pre-open per-ticker baseline signal snapshots from market bars plus normalized Postgres-backed insider, SEC, news, fundamentals, event/earnings calendar, options, macro/sector/theme read-through source family, and existing research context data; refresh provider data only through controlled adapters when needed | No | `signal_snapshots` |
| `StrategyPipeline` | Match each ticker to versioned strategy definitions, score every eligible `(ticker, strategy_id)` pair, attach strategy horizon/evidence, and create ranked candidate scores | Mostly no; optional strategy explanation | `strategy_runs`, `candidate_scores` |
| `PrimaryStrategySelector` | Choose one primary tactical strategy and one expression bucket per ticker/action so attribution, trade identity, and risk budgeting stay clean | No | `trade_classifications`, `trading_decisions` context |
| `TradeClassifier` | Assign portfolio-pool trade identity before candidate order decisions: core holding, tactical stock trade, tactical option trade, or watch-only. `RiskManager` assigns `risk_hedge_overlay` for hedge actions | No | `trade_classifications` or embedded in `trading_decisions` |
| `OptionsStrategyLayer` | Create paper-only leg-based option plans only when an option expression is eligible, limited initially to long calls, long puts, call/put credit spreads, long straddles, and long strangles, with Greeks, max loss, margin requirement, buying-power effect, and assignment risk when relevant | Mostly no; optional explanation | `option_strategy_decisions`, `paper_option_orders`, `paper_option_positions` |
| `TradingPipeline` | Combine selected strategy, trade identity, instrument plan, macro regime, portfolio state, risk appetite/effective risk config, and learning factors; produce proposed trading decisions, thesis, invalidators, and suggested sizing | Yes, Gemini Flash bounded decision schema | `trading_decisions`, `paper_orders` |
| `RiskConfigResolver` | Convert the user-facing `risk_appetite` preset into a deterministic generated risk config using account state, macro regime, portfolio composition, trade identity, and hard safety rails | No | `risk_appetite_profiles`, `risk_limit_configs` |
| `PositionSizer` | Convert approved trade intent into target quantity/weight using volatility, liquidity, strategy budget, macro budget, and factor exposure constraints | No | `position_sizing_decisions` |
| `RiskManager` | Enforce portfolio-level risk limits, factor exposure concentration limits, correlation clusters, leg-based option risk, assignment exposure when relevant, and hard reject/reduce rules | No | `portfolio_risk_snapshots`, `risk_factor_exposures`, `option_risk_snapshots` |
| `PaperBroker` | Simulate stock and option fills, slippage, commissions, rejects, order status transitions, and margin/buying-power effects | No | `paper_orders`, `paper_executions` |
| `PortfolioPipeline` | Maintain stock/options positions and one unified simulated margin account with cash balance, account equity, margin used, buying power, excess liquidity, exposure, and realized/unrealized PnL | No | `paper_positions`, `portfolio_snapshots` |
| `HourlySignalRefreshPipeline` | Build scoped intraday delta snapshots using the same canonical signal schema as pre-open snapshots. It runs freshness-gated targeted refreshes for portfolio-relevant tickers, updates price/volume, relative strength, VWAP/gap, option marks, news/events, and checks low-frequency source freshness without full re-ingestion | Optional Gemini Flash bounded classifier only for news/event classification after deterministic filters | `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts` |
| `IntradayRebalancePipeline` | Convert material signal changes and critical/high-impact alerts into reduce/exit/add/hold proposals for existing positions or active candidates | Yes, Gemini Flash bounded decision schema; risk manager remains final gate | `intraday_rebalance_decisions`, `paper_orders` |
| `HistoricalReplayOutcomeEvaluator` | Replay prior decision-time snapshots without lookahead, evaluate candidates/trades/watch items over each strategy horizon, and compute alpha vs `SPY`, `QQQ`, sector/theme ETF, and decision-time peer basket before reflection or strategy promotion uses the evidence | No | `historical_replay_runs`, `candidate_outcome_evaluations`, `strategy_evaluation_results` |
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
- `PortfolioState` persists the identity with open positions, staged orders, paper option positions, and closed trades.
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

首版不需要一次实现所有信号，但 schema 要允许增量添加。缺失信号必须显式保存为 `null` 或 `status=missing`，不能在 prompt 中伪造。

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

## 8. Daily Workflow

All scheduled times are in `America/New_York`.

| Time | Job | Output |
| --- | --- | --- |
| 07:00 | Universe refresh | tradable symbols and exclusions |
| 07:15 | Macro snapshot + event calendar refresh | `macro_snapshots`, normalized `calendar_events`, portfolio-scored `portfolio_event_risk_assessments`, and prior-night/early-morning sector-theme read-through context |
| 07:30 | Pre-market signal computation | `signal_snapshots` for the universe, including own-event timing and macro/sector/theme read-through exposure context |
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
6. Select one primary tactical strategy and one expression bucket for each ticker/action under consideration.
7. Classify each selected candidate or existing position into a portfolio-pool trade identity before any order decision.
8. Build a tactical option plan only when the selected expression bucket and `trade_identity = "tactical_option_trade"` make an option expression eligible.
9. Pass only the selected candidates plus current positions and paper option positions into `TradingPipeline`.
10. `TradingPipeline` proposes an action, thesis, invalidators, suggested size, horizon, instrument expression, and trade identity.
11. Deterministic risk constraints and portfolio budget decide whether the proposed action becomes a staged paper stock order, staged tactical paper option order, is reduced, or is rejected.
12. Separately, `RiskManager` may generate paper-only `risk_hedge_overlay` actions when portfolio-level beta, concentration, or event risk should be hedged instead of handled only by sizing.

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
PrimaryStrategySelector chooses selected strategy and expression bucket
      |
      v
TradeClassifier assigns portfolio-pool trade identity
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
- tickers with staged orders or same-day trades
- top active candidates from the morning scan
- active manual/pinned review tickers
- high-impact market/sector news from the provider feed

If provider limits allow, the scan can also query broader universe signals/news, but the first production path should prioritize portfolio-relevant names so it can react quickly without excessive API usage.

Hourly refresh starts with a freshness plan rather than a full rerun of all source pipelines:

1. Determine the intraday scope: open positions, same-day trades, staged orders, top morning candidates, manual requests, option positions, and critical/high event exposures.
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
5. `PaperBroker` simulates any approved order.

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

## 10. Paper Trading and Risk

### Unified Paper Margin Account

V2 should simulate one margin account shared by stock trades, option trades, hedge overlays, and assignment scenarios. There should not be a separate stock cash account and option margin account. Every proposed order must be evaluated against the same account-level buying power and margin constraints.

The account snapshot should persist:

- `cash_balance`
- `account_equity`
- `net_liquidation_value`
- `buying_power`
- `excess_liquidity`
- `stock_market_value`
- `option_market_value`
- `stock_margin_requirement`
- `option_margin_requirement`
- `total_margin_requirement`
- `initial_margin_requirement` and `maintenance_margin_requirement` when available or approximated
- `margin_model_profile`, `margin_model_version`, and `margin_requirement_source`
- `day_pnl`, `realized_pnl`, and `unrealized_pnl`

The default estimated margin model should be more realistic than a flat toy model while still being explicit that it is an estimate. V2 should default to `estimated_fidelity_like_conservative_v1`: a broker-profile model inspired by public Reg T, exchange, and Fidelity-style house/RBR concepts. It must not claim to exactly reproduce Fidelity's internal margin engine unless broker-observed margin requirements are imported and stored.

Supported margin model profiles:

- `reg_t_base_conservative_v1`: simple Reg T style fallback.
- `estimated_fidelity_like_conservative_v1`: default paper model with Reg T initial requirements, broker-house maintenance assumptions, option-spread treatment, and conservative add-ons.
- `broker_observed_margin_v1`: optional future mode that uses imported broker-reported requirements or broker-calculator outputs as the authoritative requirement, while still storing the simulated estimate for comparison.

Every margin computation should persist `margin_model_profile`, `margin_model_version`, `margin_requirement_source`, and whether the requirement is estimated, broker-observed, or manually overridden. If broker-observed values are unavailable, the system should use the conservative estimate and label it as such.

Default estimated rules:

- Long marginable US stock starts with a Reg T style 50% initial requirement. Maintenance uses the maximum of the configured base maintenance requirement and any security, house, concentration, volatility, liquidity, leveraged-ETF, or unknown-marginability add-on. The default base maintenance requirement should be at least 30% for fully marginable diversified common stock.
- Unknown, non-marginable, very low-priced, highly volatile, hard-to-borrow, concentrated, or manually restricted securities should fall back to a 100% requirement unless a stricter override is configured.
- Short stock is disabled in V2 by default. If enabled later, it must use stricter initial and maintenance requirements, locate/borrow assumptions, and conservative house add-ons.
- Long options consume full premium paid plus fees as buying-power effect.
- Defined-risk credit spreads consume max loss when max loss is known; if a configured broker profile requires a higher value, use the higher value.
- Long straddles and long strangles consume full net premium paid plus fees as buying-power effect.
- Standalone naked short options, short straddles, short strangles, standalone short puts, covered calls, collars, debit spreads, and custom multi-leg structures are outside the initial V2 option whitelist. They should be rejected or downgraded unless explicitly enabled in a later design revision.
- If naked or undefined-risk structures are enabled later, they must use conservative uncovered-option formulas and may be blocked entirely when inputs are missing. The model must not treat short-option premium as sufficient collateral.
- Multi-leg option strategies must persist a deterministic `strategy_pairing_method`. If legs cannot be paired unambiguously into a defined-risk structure, margin should fall back to the more conservative naked-leg estimate or the trade should be rejected.
- Assignment-capable strategies must pass both current margin/buying-power checks and a worst-case assigned portfolio check at strike-level stock exposure.
- If required data is missing, stale, or internally inconsistent, the risk manager should use the more conservative requirement, reduce size, or reject the paper order.

This keeps paper risk close enough to real margin-account behavior for planning, while preserving a clear audit trail between estimated requirements and any future broker-observed values.

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
- unified margin-account equity, buying power, margin used, and gross/net exposure
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

### Option Strategy Risk and Assignment Risk

For every paper option strategy, risk must be evaluated at the strategy level and at the leg level. The risk manager should calculate:

- per-leg option exposure: call/put, side, quantity, strike, expiry, DTE, Greeks, mark, and event-through-expiry status
- strategy-level exposure: net debit/credit, max loss, max profit when definable, breakevens, margin requirement, buying-power effect, net Greeks, and liquidity/width quality
- portfolio-level option exposure: aggregate delta/gamma/theta/vega, protected exposure, hedge cost, margin usage, buying-power usage, and concentration by ticker/theme/expiry/event

For assignment-capable paper strategies, risk must also be evaluated as if assignment can happen. The risk manager should calculate both:

- current portfolio exposure: stock positions plus marked option positions
- worst-case assigned portfolio: current stock positions plus assignment-capable short option legs converted into the resulting stock exposure at their strikes

The worst-case assigned portfolio is the primary control for assignment-capable credit spreads and any future strategy with short option legs that can create stock exposure. Standalone short puts are not part of the initial V2 option whitelist. A trade is rejected, reduced, or adjusted if simultaneous assignment would create unacceptable concentration, even if current stock exposure looks safe.

Required assignment metrics:

- assignment notional by ticker
- margin requirement and buying-power effect by strategy and total portfolio
- breakeven exposure by ticker
- sector/theme/industry exposure after assignment
- high-beta AI/semis/space exposure after assignment
- expression bucket exposure after assignment
- correlation-cluster exposure after assignment
- earnings-through-expiry flag and event-risk exposure

Example assignment question the risk manager must answer:

```text
If every assignment-capable short option leg is assigned at strike, does the portfolio become an over-concentrated high-beta AI/semiconductor/space book?
```

If yes, the system can propose `avoid_event_option`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy` to a lower-risk whitelisted structure, reduce new common-stock exposure, or reject new option strategies.

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
| Option strategy | per-leg Greeks, net Greeks, max loss, max profit, breakevens, margin requirement, buying-power effect, spread width, expiry/event exposure | Understand option risk beyond the underlying stock position. |
| Option assignment | assignment-capable short-leg notional, breakeven exposure, margin requirement, buying-power effect | Avoid hidden stock exposure that appears only after assignment. |
| Hedge overlay | hedge notional, hedge delta, hedge cost, protected exposure | Track whether paper option hedges reduce the intended risk without becoming a hidden speculative position. |

Factor exposures should be approximate in V2. A robust simple model is better than a fragile complex one: start with sector/industry, strategy, horizon, direction, beta proxy, volatility bucket, liquidity bucket, and event type, then add rolling-correlation clusters once enough market data is available.

### Risk Appetite Presets

The operator-facing risk configuration should be intentionally small. In V2, all trading is paper-only, so there is no need to expose fields such as `allowed_paper_only`. The primary user setting should be:

```json
{
  "risk_appetite": "balanced"
}
```

Supported presets:

| Preset | Intended behavior |
| --- | --- |
| `conservative` | Smaller paper position sizes, lower margin usage, stricter assignment exposure, stricter theme/sector concentration, more frequent downgrade to watch, and preference for defined-risk option structures. |
| `balanced` | Default profile. Allows normal paper position sizes and moderate margin usage while still enforcing all hard safety rails. |
| `aggressive` | Larger paper position sizes, wider concentration and margin budgets, and more willingness to use option expressions when data is complete. It still cannot bypass hard safety rails. |

`RiskConfigResolver` owns the conversion from `risk_appetite` to an effective generated `RiskLimitConfig`. The resolver must be deterministic and versioned. Inputs should include:

- selected `risk_appetite`
- account equity, buying power, margin usage, and excess liquidity
- current portfolio composition and trade identities
- macro regime and macro budget multiplier
- strategy horizon and expression bucket
- option assignment exposure and Greeks
- event risk and source freshness state

The generated config is persisted for audit/debug/replay, but it is not the primary user-facing object. The UI should show the active preset and a short explanation of binding constraints. Full generated limits can live behind an advanced/debug view.

### Hard Safety Rails

Hard safety rails do not change across `conservative`, `balanced`, and `aggressive`:

- Missing, stale, or internally inconsistent signal snapshots block trading or downgrade to watch.
- Missing option-chain, leg pricing, Greeks, margin, buying-power, event, or assignment metadata blocks option trades or downgrades to watch.
- If margin requirement cannot be estimated, use the conservative fallback, reduce size, or reject.
- Worst-case assignment cannot create an over-concentrated portfolio by ticker, sector/theme, expression bucket, or correlation cluster.
- Macro-only bearish evidence cannot create a high-confidence single-name short or bearish trade.
- Core holdings cannot be sold solely because of a short-term tactical signal.
- Risk hedge overlays remain paper-only `RiskManager` actions and are excluded from tactical strategy win-rate attribution.
- No averaging down in V2 unless explicitly added later.

### Generated Risk Limits and Actions

The effective generated risk config should cover these categories without exposing dozens of knobs in the default UI:

- max position weight per ticker
- max daily new positions
- gross/net/beta-adjusted exposure
- macro budget multiplier
- strategy, horizon, event, sector, industry, theme, and correlation-cluster caps
- high-volatility and low-liquidity caps
- unified margin-account buying power, total margin requirement, and excess-liquidity caps
- stock margin and option margin/buying-power usage caps
- option max loss, net debit/credit, assignment notional, and portfolio Greeks caps
- event-through-expiry restrictions for option strategies
- paper hedge overlay eligibility and budget caps

Risk actions should distinguish soft warnings from hard blocks:

- Soft warning: allow order but mark the portfolio as near limit.
- Size reduction: reduce order until exposure fits the remaining factor budget.
- Hard reject: no order is created.
- Forced reduce/exit: only for existing positions that violate hard limits after market movement or stale risk data.
- Paper hedge overlay: open, close, or adjust a simulated option hedge when portfolio-level risk should be reduced without changing the underlying tactical/core position. This is a risk action, not a trading strategy signal.

Example high-level config:

```json
{
  "risk_appetite": "conservative",
  "profile_version": "v1"
}
```

Example generated config snapshot:

```json
{
  "risk_appetite": "conservative",
  "resolver_version": "risk_config_resolver_v1",
  "margin_model_profile": "estimated_fidelity_like_conservative_v1",
  "risk_tiers": {
    "position_size": "small",
    "margin_usage": "low",
    "theme_concentration": "strict",
    "assignment_exposure": "strict",
    "option_expression": "defined_risk_preferred"
  },
  "binding_limits": [
    "missing_data",
    "margin_usage",
    "assignment_exposure",
    "theme_concentration"
  ]
}
```

The risk manager must persist both accepted and rejected decisions. Rejected trades are important training data for reflection because the system should learn whether risk constraints protected the portfolio or blocked good opportunities.

## 11. Historical Replay, Reflection, and Learning Loop

### Historical Replay and Outcome Evaluator

Reflection should not be the first component to judge whether a strategy worked. Before reflection runs, `HistoricalReplayOutcomeEvaluator` must compute deterministic outcomes from point-in-time snapshots:

- every selected trade
- every rejected candidate that reached candidate scoring
- every `catalyst_watch` and ordinary `watch_only` item
- active and shadow strategy candidates
- manual ticker requests

The evaluator measures each item over the selected strategy's configured horizon and any interim checkpoints. It compares absolute return and risk-adjusted return against:

- `SPY`
- `QQQ`
- configured sector ETF
- configured theme ETF
- decision-time peer basket
- decision-time opportunity set when available

It should persist interim marks for open trades and final outcome rows only when the trade closes or the configured horizon expires. The evaluator must use only data that was available at each decision time for candidate reconstruction, and only subsequent market data for outcome measurement. It must not use future knowledge to change the original candidate set, peer basket, strategy assignment, confidence bucket, or trade identity.

Outcome records should include:

- `strategy_id` and version
- `trade_identity`
- `expression_bucket_id`
- `decision_time`
- `horizon_start_at` and `horizon_end_at`
- benchmark returns
- peer basket return and basket membership snapshot id
- candidate/trade return
- alpha vs each comparator
- MFE/MAE
- drawdown and volatility where available
- regime, sector/theme, catalyst type, and confidence bucket
- whether the row is interim or final

Reflection and strategy evolution consume these outcome rows rather than recomputing attribution ad hoc.

### Reflection Input and Output

Reflection runs after the portfolio is marked to close and after historical replay/outcome evaluation has produced the relevant interim or final outcome rows. It receives:

- morning macro snapshot
- strategy candidates and scores
- trading decisions and rejected decisions
- intraday news alerts and rebalance decisions
- paper orders/executions
- end-of-day PnL, benchmark return, sector return
- peer-basket returns and relevant ETF returns, e.g. `QQQ`, `SMH`, `SOXX`
- paper option positions, option strategy lifecycle actions, leg-level risk snapshots, hedge overlay decisions, and worst-case assignment snapshots when relevant
- historical replay/outcome evaluator rows for selected trades, rejected candidates, watch items, and shadow strategies
- per-trade MFE/MAE if available
- invalidators and whether they triggered
- prior learning factors used

Reflection should evaluate the portfolio, not just individual research calls. The main questions are:

- Did bullish catalyst trades outperform the relevant ETF and peer basket over their intended strategy horizon, or only ride a sector tailwind?
- Did bearish or risk-off reasoning actually add value, or did it incorrectly suppress strong-trend names?
- Were high-confidence calls calibrated by historical pattern quality, or did narrative completeness inflate confidence?
- Did `neutral/watch` hide a catalyst-watch opportunity with large move potential?
- Did option trades have acceptable max loss, Greeks, event risk, liquidity, and assignment risk where relevant?
- Did risk hedge overlays reduce portfolio risk enough to justify hedge cost?
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

The next trading run adapts only to learning factors that are active under the lifecycle policy below. Adaptation means:

- candidate scores can be adjusted only by active, validated strategy-scoped learning factors
- trading prompt context may include candidate/observation lessons as soft context, but the prompt must label them as not behavior-changing
- risk manager can automatically apply learning factors that tighten constraints, lower size, add blocked conditions, or increase required confirmation
- learning factors that raise score, expand eligibility, increase size, loosen risk, or promote a new setup must remain candidate/shadow/test until outcome evidence supports promotion
- every applied learning factor is persisted through `learning_factor_applications`
- later reflections evaluate whether the learning factor helped, hurt, overfit, or should be retired

### Learning Factor Lifecycle

| Status | Meaning |
| --- | --- |
| `candidate` | Newly generated by reflection; may appear as soft context, but does not change scoring, sizing, or risk approval |
| `observation` | Informational lesson shown in UI or prompt context for analyst review; no behavioral effect |
| `shadow` | Evaluated against historical/live paper outcomes without changing orders or sizes |
| `active` | Allowed to affect candidate scoring, trading prompt context, or risk rules under its approved scope |
| `suppressed` | Stored but not injected |
| `retired` | No longer relevant |

Initial policy:

- New learning factors default to `candidate` or `observation`, not `active`.
- Risk-tightening factors may become `active` automatically when they only reduce exposure, add required confirmation, block stale-data scenarios, lower confidence, or tighten exit rules.
- Any learning factor that increases score, expands eligibility, increases position size, weakens hard safety rails, broadens universe rules, or increases strategy/risk budget must go through shadow/test evidence and explicit promotion.
- If reflection suggests a looser risk rule, broader universe rule, larger strategy budget, or new alpha pattern, the change should become a strategy/config proposal rather than an automatically active learning factor.
- Every trading decision stores which learning factors were injected so impact can be evaluated later.

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
| `macro_snapshots` | One macro snapshot/regime per run/day |
| `macro_readthrough_events` | Structured peer/sector-leader earnings read-through events with source ticker, scope, mechanism, direction, affected theme/relationship, transcript/release provenance, and validity window |
| `calendar_events` | Normalized future macro, economic, Fed, earnings, market-structure, and option-relevant events with source/provider provenance, scheduled time, event type, global importance, affected ticker/theme metadata, and raw payload reference |
| `portfolio_event_risk_assessments` | Per event portfolio relevance and risk score: affected positions/candidates/options, sector/theme mapping, holding-period lookahead reason, risk mechanism, suggested action type, and hide/show decision |
| `signal_snapshots` | Per ticker per day pre-open baseline quant features and normalized signal JSON, including source freshness, missing/stale fields, `snapshot_type`, `decision_time`, `source_record_refs`, `available_for_decision_at`, and no-lookahead audit fields |
| `strategy_definitions` | Versioned strategy metadata, required signals, horizon, scoring config, invalidators |
| `strategy_proposals` | Proposed new strategies or revisions derived from reflection/learning, including lifecycle status and evidence |
| `strategy_evaluation_results` | Shadow/experimental performance and promotion/retirement evidence for strategy definitions |
| `strategy_runs` | One candidate-scoring batch per day |
| `candidate_scores` | Ranked ticker candidates by strategy, horizon, evidence, macro compatibility |
| `trade_classifications` | Portfolio-pool trade identity, expression bucket, watch type, intended horizon, and exit-policy metadata for each candidate/position decision |
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
| `risk_factor_exposures` | Normalized per-position and portfolio exposures by factor type/name |
| `paper_orders` | Staged/submitted/filled/rejected paper orders |
| `paper_executions` | Simulated fills |
| `paper_positions` | Current position state |
| `portfolio_snapshots` | Daily unified margin account state: NAV/net liquidation value, account equity, cash balance, buying power, excess liquidity, margin requirements, margin model profile/source, exposure, and PnL |
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
- Gate every alert-driven action through `PositionSizer`, `RiskManager`, and `PaperBroker`.
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
13. Trading pipeline creates paper orders only after Pydantic-validated LLM output, retry/fallback handling, risk checks, and budget allocation pass.
14. Position sizing records base size, volatility adjustment, liquidity cap, remaining factor budget, final size, and binding constraints.
15. Portfolio risk snapshots show factor exposure by sector, strategy, horizon, beta, volatility, liquidity, event type, macro sensitivity, correlation cluster, leg-based option risk, and assignment exposure where relevant.
16. Risk manager reduces or rejects trades that would make current portfolio risk, option strategy risk, or worst-case assigned portfolio too concentrated in any configured risk factor.
17. Paper portfolio shows positions, trades, exposure, and day PnL.
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
28. Unit tests run against fake providers, integration tests use recorded cassettes, and live provider smoke tests are opt-in and non-blocking for ordinary CI.
29. `/today` is a tabbed trading workstation with `Overview`, `Portfolio`, `Trades`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, and `Ops & Cost` tabs.
30. Trade detail views show complete audit trails: signal snapshots, strategy scores, selected strategy, trade identity, LLM decision JSON, risk decision, order/fill state, exit plan, invalidators, and post-close outcome.
31. `Ops & Cost` shows LLM/API usage, model/provider, tokens, estimated cost, latency, retry/error state, validation/fallback state, prompt/schema version, and provider request budget/circuit-breaker state by pipeline and run.
32. Existing research run audit pages continue to work.

## 18. Resolved Design Decisions

1. Universe scope: use a user-editable US common-stock universe with liquidity filters and sector/industry include/exclude filters. Do not scan every listed name by default.
2. Common-stock paper trading is long-only in V2. Do not add direct short-stock paper trades behind a flag.
3. Holding period is determined automatically by the selected trading strategy definition. There is no global intraday-only or swing-only horizon.
4. New learning factors default to `candidate` or `observation`; only risk-tightening factors may become automatically active, while expansionary changes must be represented as strategy/config proposals or promoted after shadow/test evidence.
5. Manual ticker requests stay active until manually dismissed. They do not expire at end of day by default.
6. The first verifiable MVP is universe -> point-in-time signal snapshot -> strategy scoring -> historical replay/outcome evaluator; paper trading, options, intraday, reflection, and strategy evolution follow after that edge-validation path exists.
