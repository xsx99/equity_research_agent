# Trading Agent Refactor Progress Tracker

## 2026-05-29

- Created the V2 staged implementation plan in `plan/research_app/trading_agent_refactor_implementation_plan.md`.
- Execution policy: implement one PR slice at a time, stop after verification, wait for user review/merge before continuing.
- Updated the design and implementation plan to include strategy evolution: the system can summarize repeated learning into new strategy proposals, add them to the strategy catalog as candidate/shadow strategies, and promote them through gated lifecycle states.
- Updated the design and implementation plan to include hourly intraday signal refresh, news scans, and risk-gated immediate rebalance actions for material signal changes or critical/high positive or negative news.
- Updated the design and implementation plan with 500+ eval learnings: V2 is explicitly a relative-strength catalyst bot, bullish catalyst signals are higher-trust than bearish macro narratives, macro risk is a sizing/risk-budget input rather than a single-name short trigger, and confidence must be calibrated by historical pattern quality.
- Added trade identity requirements for portfolio pools: core holdings, tactical stock trades, tactical option trades, RiskManager hedge overlays, and watch-only candidates.
- Added paper/simulation-only options strategy layer requirements for leg-based single-leg and multi-leg option strategies, with short-put aliases such as `sell_put`, `close_put`, `roll_put`, `avoid_earnings_put`, and `put_assignment_plan`.
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
- Generalized the options layer beyond puts: tactical option trades can be single-leg calls/puts, margin-backed short puts, spreads, collars, or configurable multi-leg structures, with leg-based risk and short-option assignment checks.
- Clarified option simulation collateral model: V2 assumes a margin account / buying-power model for option trades, not cash-secured or security-secured requirements, while still tracking assignment exposure for short-option structures.
- Clarified account model: paper stock and option trades share one simulated margin account with unified account equity, margin requirement, buying power, excess liquidity, and assignment-risk checks.
- Split mixed strategy/expression names: strong-theme, valuation-repair, and core-accumulation ideas are strategy playbooks, while `long_stock`, `margin_backed_short_put`, `defined_risk_directional_option`, `defined_risk_income_spread`, and `core_stock_accumulation` are pure expression buckets.
- Added peer/sector-leader earnings read-through as a `SignalPipeline` source family classified with macro/sector/theme context, not as a target-company signal.
- Clarified that target-company earnings releases, guidance, transcripts, and post-earnings analyst revisions remain ticker-level company signals in that ticker's own `quant_signal_snapshot`.
- Added portfolio-aware future event calendar requirements: normalize macro/earnings/Fed/company events, score relevance against current holdings/candidates/options/horizons, and show only material upcoming risks in the UI.

## PR Slice Status

| Slice | Scope | Status | Notes |
| --- | --- | --- | --- |
| PR 1 | Trading foundation schema + strategy catalog | Pending | Adds 15 broad tactical strategies, 4 eval-derived playbooks, 5 pure expression buckets including defined-risk options, manual ticker request schema, prompt registry/schema, and portfolio-pool trade identity taxonomy. |
| PR 2 | Universe scan + signal snapshots | Pending | Adds relative-strength benchmark/peer fields, manual request ingestion, own-company earnings signals, macro/sector/theme read-through, portfolio-aware event calendar risk scoring, Postgres-backed insider/news/fundamental/context signals, and explicit missing signal handling. |
| PR 3 | Strategy matching + candidate scoring | Pending | Adds source attribution, primary strategy selection, trade classification, catalyst-watch split, bearish gating, and confidence calibration inputs. |
| PR 4 | Position sizing + portfolio risk manager | Pending | Depends on candidates and risk tables; keeps core holdings separate from short-term catalyst trades. |
| PR 5 | Trading decisions + paper stock broker + portfolio state | Pending | Depends on stock risk gate; adds unified simulated margin account and enforces `review_only` vs `paper_trade_eligible` manual request mode. |
| PR 6 | Paper options strategy layer + assignment risk | Pending | Paper/simulation-only leg-based option strategies, short-put aliases, RiskManager-owned hedge overlays, option-risk snapshots, and worst-case assignment checks when relevant. |
| PR 7 | Intraday signal refresh + news alerts + rebalance | Pending | Hourly signal/news refresh during market hours; material signal changes or critical/high alerts can trigger risk-gated stock and paper-option actions. |
| PR 8 | Reflection + learning factors | Pending | Uses highest-quality configured reflection model; includes peer benchmarks, manual request attribution, bullish/bearish calibration, and option attribution. |
| PR 9 | Strategy evolution + dynamic strategy catalog | Pending | Converts repeated learning into candidate/shadow strategies beyond the initial seeds. |
| PR 10 | Today dashboard UI | Pending | Tabbed workstation with trade audit drill-downs, strategy performance, and LLM/API cost telemetry. |
| PR 11 | Scheduler, smoke tests, deploy docs | Pending | Final operational wiring, including manual ticker review job, intraday signal refresh job, and smoke mode. |

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
- No implementation tests run yet; documentation/planning update only.
