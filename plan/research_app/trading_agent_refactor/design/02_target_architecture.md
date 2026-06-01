# Design Module 02: Target Architecture

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

