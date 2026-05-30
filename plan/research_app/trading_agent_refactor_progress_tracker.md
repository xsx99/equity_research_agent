# Trading Agent Refactor Progress Tracker

## 2026-05-29

- Created the V2 staged implementation plan in `plan/research_app/trading_agent_refactor_implementation_plan.md`.
- Execution policy: implement one PR slice at a time, stop after verification, wait for user review/merge before continuing.
- Updated the design and implementation plan to include strategy evolution: the system can summarize repeated learning into new strategy proposals, add them to the strategy catalog as candidate/shadow strategies, and promote them through gated lifecycle states.
- Updated the design and implementation plan to include hourly intraday signal refresh, news scans, and risk-gated immediate rebalance actions for material signal changes or critical/high positive or negative news.
- Updated the design and implementation plan with 500+ eval learnings: V2 is explicitly a relative-strength catalyst bot, bullish catalyst signals are higher-trust than bearish macro narratives, macro risk is a sizing/risk-budget input rather than a single-name short trigger, and confidence must be calibrated by historical pattern quality.
- Added trade identity requirements for core holdings, catalyst common stock, theme sell-put, valuation-repair sell-put, catalyst-watch, and ordinary watch.
- Added paper/simulation-only options strategy layer requirements for `sell_put`, `close_put`, `roll_put`, `avoid_earnings_put`, and `put_assignment_plan`.
- Added worst-case assigned-portfolio risk requirements so paper short puts are evaluated as if simultaneous assignment can occur.
- Added Manual Ticker Review / Pinned Review design: users can force evaluation of non-scanner tickers in `review_only` or `paper_trade_eligible` mode, while keeping the same signal, strategy, confidence, and risk gates.
- Clarified that `SignalPipeline` builds full per-ticker snapshots from market bars plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, and existing research context sources, not only price/technical signals.
- Clarified strategy flow: score all eligible strategies first, then use `PrimaryStrategySelector` plus `TradeClassifier` to choose the selected strategy, strategy bucket, and trade identity before `TradingPipeline` proposes a trade.
- Clarified intraday loop: hourly refresh should scan material signal changes across price/volume, relative strength, options, news/events, and freshness checks for low-frequency sources, not news alone.
- Updated UI design to a tabbed trading workstation: Overview, Portfolio, Trades, Risk & Macro, Candidates, Learning & Strategies, and Ops & Cost, with full trade drill-down audit trails.
- Added prompt versioning and persistence requirement: every LLM pipeline must load version-controlled prompts through a prompt registry and persist prompt/template version, rendered prompt hash, input context, raw/parsed output, schema version, usage, cost, latency, and errors.
- Clarified attribution policy: benchmark and peer-basket alpha must use the selected strategy's configured holding horizon, with interim marks for open trades, rather than assuming every strategy is a one-day trade.

## PR Slice Status

| Slice | Scope | Status | Notes |
| --- | --- | --- | --- |
| PR 1 | Trading foundation schema + strategy catalog | Pending | Adds 15 tactical strategies, 4 strategy buckets, manual ticker request schema, prompt registry/schema, and trade identity taxonomy. |
| PR 2 | Universe scan + signal snapshots | Pending | Adds relative-strength benchmark/peer fields, manual request ingestion, Postgres-backed insider/news/fundamental/context signals, and explicit missing signal handling. |
| PR 3 | Strategy matching + candidate scoring | Pending | Adds source attribution, primary strategy selection, trade classification, catalyst-watch split, bearish gating, and confidence calibration inputs. |
| PR 4 | Position sizing + portfolio risk manager | Pending | Depends on candidates and risk tables; keeps core holdings separate from short-term catalyst trades. |
| PR 5 | Trading decisions + paper stock broker + portfolio state | Pending | Depends on stock risk gate; enforces `review_only` vs `paper_trade_eligible` manual request mode. |
| PR 6 | Paper options strategy layer + assignment risk | Pending | Paper/simulation-only short puts; sell/close/roll/avoid/assignment plan plus worst-case assignment checks. |
| PR 7 | Intraday signal refresh + news alerts + rebalance | Pending | Hourly signal/news refresh during market hours; material signal changes or critical/high alerts can trigger risk-gated stock and paper-put actions. |
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
- No implementation tests run yet; documentation/planning update only.
