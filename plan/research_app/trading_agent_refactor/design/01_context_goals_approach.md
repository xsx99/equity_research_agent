# Design Module 01: Context, Goals, and Approach

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

