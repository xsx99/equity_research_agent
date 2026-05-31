# Trading Agent Refactor Progress Tracker

## 2026-05-29

- Created the V2 staged implementation plan in `plan/research_app/trading_agent_refactor_implementation_plan.md`.
- Execution policy: implement one PR slice at a time, stop after verification, wait for user review/merge before continuing.
- Updated the design and implementation plan to include strategy evolution: the system can summarize repeated learning into new strategy proposals, add them to the strategy catalog as candidate/shadow strategies, and promote them through gated lifecycle states.
- Updated the design and implementation plan to include hourly intraday signal refresh, news scans, and risk-gated immediate rebalance actions for material signal changes or critical/high positive or negative news.
- Updated the design and implementation plan with 500+ eval learnings: V2 is explicitly a relative-strength catalyst bot, bullish catalyst signals are higher-trust than bearish macro narratives, macro risk is a sizing/risk-budget input rather than a single-name short trigger, and confidence must be calibrated by historical pattern quality.
- Added trade identity requirements for portfolio pools: core holdings, tactical stock trades, tactical option trades, RiskManager hedge overlays, and watch-only candidates.
- Added paper/simulation-only options strategy layer requirements for leg-based option strategies.
- Added option-risk requirements: every option strategy needs leg-level metadata, strategy-level max-loss/margin-requirement/buying-power/Greeks risk, and worst-case assigned-portfolio checks when assignment can occur.
- Added Manual Ticker Review / Pinned Review design: users can force evaluation of non-scanner tickers in `review_only` or `paper_trade_eligible` mode, while keeping the same signal, strategy, confidence, and risk gates.
- Clarified that `SignalPipeline` builds full per-ticker snapshots from market bars plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, and existing research context sources, not only price/technical signals.
- Clarified strategy flow: score all eligible strategies first, then use `PrimaryStrategySelector` plus `TradeClassifier` to choose the selected strategy, expression bucket, and portfolio-pool trade identity before `TradingPipeline` proposes a trade.
- Clarified intraday loop: hourly refresh should scan material signal changes across price/volume, relative strength, options, news/events, and freshness checks for low-frequency sources, not news alone.
- Updated UI design to a tabbed trading workstation: Overview, Portfolio, Trades, Risk & Macro, Candidates, Learning & Strategies, and Ops & Cost, with full trade drill-down audit trails.
- Added prompt versioning and persistence requirement: every LLM pipeline must load version-controlled prompts through a prompt registry and persist prompt/template version, rendered prompt hash, input context, raw/parsed output, schema version, usage, cost, latency, and errors.
- Clarified attribution policy: benchmark and peer-basket alpha must use the selected strategy's configured holding horizon, with interim marks for open trades, rather than assuming every strategy is a one-day trade.
- Clarified that bearish evidence handling and trade identity are learned constraints embedded across the normal strategy, trading, sizing, risk, reflection, and UI flow; they are not standalone trading functions.
- Refined trade identity taxonomy into portfolio-pool identities: `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, `risk_hedge_overlay`, and `watch_only`; strategy expression buckets remain the alpha/expression layer, and risk hedge overlays are RiskManager-owned paper option actions.
- Scoped the initial options layer whitelist to long calls, long puts, call/put credit spreads, long straddles, and long strangles, with non-whitelisted structures rejected or downgraded.
- Clarified option simulation collateral model: V2 assumes a margin account / buying-power model for option trades, not cash-secured or security-secured requirements, while still tracking assignment exposure for short-option structures.
- Clarified account model: paper stock and option trades share one simulated margin account with unified account equity, margin requirement, buying power, excess liquidity, and assignment-risk checks.
- Refined the default estimated margin model: V2 should use a more realistic `estimated_fidelity_like_conservative_v1` broker-profile estimate with Reg T style initial requirements, house maintenance assumptions, conservative add-ons, explicit margin model/source metadata, and a future path for broker-observed requirement imports.
- Split mixed strategy/expression names: strong-theme, valuation-repair, and core-accumulation ideas are strategy playbooks, while `long_stock`, `defined_risk_directional_option`, `defined_risk_income_spread`, `volatility_event_option`, and `core_stock_accumulation` are pure expression buckets.
- Added peer/sector-leader earnings read-through as a `SignalPipeline` source family classified with macro/sector/theme context, not as a target-company signal.
- Clarified that target-company earnings releases, guidance, transcripts, and post-earnings analyst revisions remain ticker-level company signals in that ticker's own `quant_signal_snapshot`.
- Added portfolio-aware future event calendar requirements: normalize macro/earnings/Fed/company events, score relevance against current holdings/candidates/options/horizons, and show only material upcoming risks in the UI.
- Reframed peer earnings read-through rules as embedded event-calendar and signal-snapshot behavior, not a standalone function.
- Added source-ingestion freshness and signal coordination design: pre-open snapshots are the daily baseline, intraday snapshots reuse the same canonical schema as scoped deltas, and hourly refresh runs targeted freshness-gated source updates instead of full pipeline reruns.
- Clarified legacy table policy: `research_runs`, `research_outputs`, and `eval_results` are optional archival/compatibility artifacts, not required V2 trading-path dependencies or trade/portfolio scoring tables.
- Simplified risk configuration into `conservative`, `balanced`, and `aggressive` risk appetite presets; `RiskConfigResolver` generates detailed effective risk configs for audit/replay while hard safety rails remain invariant across presets.
- Resolved initial design questions: universe uses user-editable liquidity/sector filters, common-stock paper trading is long-only, holding period comes from strategy definitions, and manual ticker requests stay active until dismissed. Superseded on 2026-05-31: learning factors no longer activate immediately by default.

## 2026-05-31

- Updated the design and implementation plan to add point-in-time / no-lookahead data constraints. Source records and signal snapshots now require `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at`, and replay/decision paths must filter by decision-time availability.
- Added `HistoricalReplayOutcomeEvaluator` before reflection so trades, rejected candidates, watch items, manual requests, and shadow strategies are evaluated over strategy horizons against `SPY`, `QQQ`, sector/theme ETF, and decision-time peer baskets.
- Changed learning factor lifecycle policy: new factors default to `candidate` or `observation`; only risk-tightening factors may become automatically active, while score/risk expansion requires shadow/test evidence or explicit promotion.
- Added LLM output safety requirements: trading, intraday, reflection, learning extraction, and strategy proposal JSON must pass Pydantic validation with bounded retry and safe fallback.
- Added provider resilience requirements: rate limit, batch fetch, exponential backoff, request budget, cache/freshness gate, circuit breaker, persisted provider request telemetry, and degraded mode.
- Shrank the MVP/PR blast radius: first prove universe -> point-in-time signal snapshot -> strategy scoring -> replay/outcome evaluator before paper trading, options, intraday, reflection, or strategy evolution.
- Added `portfolio_intents` for approved core holdings, target/max weight, add/trim rules, thesis invalidators, and allowed tactical interactions.
- Added structured relationship data requirements: `ticker_relationships`, `peer_baskets`, and `theme_taxonomy` for peer/theme read-through, relative strength, and attribution.
- Added deterministic testing policy: unit tests use fake providers, provider integration tests use `vcrpy`/recorded cassettes, and live API smoke tests are opt-in and non-blocking for normal CI.

## PR Slice Status

| Slice | Scope | Status | Notes |
| --- | --- | --- | --- |
| PR 1 | Trading foundation schema + strategy catalog | Pending | Adds PIT metadata fields, universe filter config schema, portfolio intents, relationship/peer/theme schemas, 15 broad tactical strategies, 4 eval-derived playbooks, 5 expression buckets, manual ticker request schema, prompt registry/schema, and trade identity taxonomy. |
| PR 2 | Provider resilience + universe + point-in-time signal MVP | Pending | Adds provider guardrails, fake-provider test path, request telemetry, user-editable universe filters, persistent manual requests, minimal market/relative-strength signal snapshots, source availability metadata, portfolio-intent eligibility, and peer basket construction. |
| PR 3 | Strategy matching + historical replay outcome evaluator | Pending | Adds source attribution, primary strategy selection, trade classification, catalyst-watch split, bearish gating, confidence calibration inputs, and deterministic outcome evaluation vs benchmarks/decision-time peer baskets. |
| PR 4 | Position sizing + portfolio risk manager | Pending | Depends on candidates and risk tables; adds simple risk appetite presets, generated risk configs, invariant hard safety rails, and conservative broker-profile margin estimates. |
| PR 5 | Trading decision agent guardrails | Pending | Adds bounded LLM trading output with Pydantic validation, retry, safe fallback, prompt/schema persistence, full context snapshot, and no paper order side effects yet. |
| PR 6 | Paper stock broker + portfolio state | Pending | Adds stock paper orders/executions/positions, unified simulated margin account, margin model/source metadata, and order idempotency. |
| PR 7 | Paper options strategy layer + assignment risk | Pending | Paper/simulation-only whitelisted option strategies: long call/put, call/put credit spread, long straddle, and long strangle; includes conservative option margin formulas, RiskManager-owned hedge overlays, option-risk snapshots, and worst-case assignment checks when relevant. |
| PR 8 | Intraday signal refresh + news alerts + rebalance | Pending | Hourly freshness-gated signal/news refresh during market hours; intraday snapshots are scoped deltas vs pre-open baseline and previous hourly snapshot before risk-gated stock/paper-option actions. |
| PR 9 | Reflection + learning factors | Pending | Uses highest-quality configured reflection model with Pydantic fallback; consumes replay outcomes; new learning factors default to candidate/observation unless risk-tightening. |
| PR 10 | Strategy evolution + dynamic strategy catalog | Pending | Converts repeated learning into candidate/shadow strategies beyond the initial seeds after replay evidence and schema-validated proposals. |
| PR 11 | Today dashboard UI | Pending | Tabbed workstation with PIT audit, trade drill-downs, strategy performance, relationship/core-intent views, and LLM/API/provider telemetry. |
| PR 12 | Scheduler, smoke tests, deploy docs | Pending | Final operational wiring, including manual ticker review job, intraday signal refresh job, replay smoke, fixture/cassette tests, opt-in live smoke, and deploy docs. |

## Verification Log

- 2026-05-29: `git diff --check` passed for the planning-only update.
- 2026-05-29: `git diff --check` passed after adding Manual Ticker Review / Pinned Review planning updates.
- 2026-05-29: `git diff --check` passed after adding tabbed UI workstation planning updates.
- 2026-05-29: `git diff --check` passed after adding prompt versioning and persistence planning updates.
- 2026-05-30: `git diff --check` passed after clarifying strategy-horizon attribution wording.
- 2026-05-30: `git diff --check` passed after embedding bearish evidence handling and trade identity as cross-pipeline constraints.
- 2026-05-30: `git diff --check` passed after separating trading strategies, expression buckets, portfolio-pool trade identities, and RiskManager-owned hedge overlays.
- 2026-05-30: `git diff --check` passed after generalizing the paper options layer from put-only plans to leg-based single-leg and multi-leg option strategies.
- 2026-05-30: `git diff --check` passed after changing option simulation from cash-secured assumptions to margin requirement and buying-power modeling.
- 2026-05-30: `git diff --check` passed after unifying paper stock and option trades under one simulated margin account.
- 2026-05-30: `git diff --check` passed after splitting mixed strategy/expression IDs into strategy playbooks and pure expression buckets.
- 2026-05-30: `git diff --check` passed after classifying peer earnings read-through as macro/sector/theme context in the signal pipeline.
- 2026-05-30: `git diff --check` passed after clarifying target-company earnings as ticker-level company signals.
- 2026-05-30: `git diff --check` passed after adding portfolio-aware upcoming event calendar design and UI requirements.
- 2026-05-30: `git diff --check` passed after embedding peer earnings read-through rules into event-calendar and signal-snapshot workflow text.
- 2026-05-30: `git diff --check` passed after adding source-ingestion freshness, pre-open baseline, and intraday delta snapshot coordination.
- 2026-05-30: `git diff --check` passed after refining the default estimated margin model into a conservative broker-profile model with margin model/source metadata.
- 2026-05-30: `git diff --check` passed after clarifying legacy research/eval tables as optional non-critical-path artifacts.
- 2026-05-30: `git diff --check` passed after simplifying risk configuration into risk appetite presets and generated effective risk configs.
- 2026-05-30: `git diff --check` passed after resolving initial design questions for universe filters, long-only common stock, strategy-defined horizons, immediate learning activation, and manual request dismissal.
- 2026-05-30: `git diff --check` passed after restricting the initial paper options whitelist to long call/put, call/put credit spreads, long straddles, and long strangles.
- 2026-05-31: `git diff --check` passed after adding PIT/no-lookahead constraints, historical replay evaluator, safer learning-factor lifecycle, LLM validation/fallback, provider resilience, smaller PR slices, portfolio intents, relationship graph, and deterministic testing policy.
- No implementation tests run yet; documentation/planning update only.
