# Trading Agent Refactor Modular Plan

This directory is the canonical modular version of the trading-agent refactor planning docs.

## How To Read

1. Start with [Module Contracts](module_contracts.md). These contracts preserve the behavior of the original long docs after the split.
2. Use the [PR Reading Guide](implementation/reading_guide.md) to choose the smallest design-module set for the current PR.
3. Read the relevant design module under [design/](design/).
4. Implement only the matching PR module under [implementation/](implementation/).
5. Update [progress tracker](progress_tracker.md) after each completed documentation or implementation slice.

## Design Modules

| Module | Contents | Original Sections |
| --- | --- | --- |
| [01 Context, Goals, and Approach](design/01_context_goals_approach.md) | Background, goals, non-goals, recommended approach | 1-4 |
| [02 Target Architecture](design/02_target_architecture.md) | Pipeline architecture, component boundaries, model routing | 5 |
| [03 Strategy Architecture](design/03_strategy_architecture.md) | Macro separation, event calendar, relationship graph, strategy catalog, trade identity, options strategy layer | 6 |
| [04 Signal Snapshots](design/04_signal_snapshots.md) | Signal schema, point-in-time/no-lookahead, source freshness, required signal families | 7 |
| [05 Workflows and Decision Contracts](design/05_workflows_and_decision_contracts.md) | Daily workflow, universe policy, manual review, intraday refresh, trading decision JSON, LLM fallback, risk decision fields | 8-9 |
| [06 Paper Trading and Risk](design/06_paper_trading_and_risk.md) | Unified margin account, paper broker, sizing, option risk, risk presets, hard safety rails | 10 |
| [07 Replay, Reflection, and Learning](design/07_replay_reflection_learning.md) | Historical replay, outcome evaluator, reflection input/output, learning factor lifecycle | 11 |
| [08 Data Model](design/08_data_model.md) | Proposed tables, legacy table policy, strategy definition shape | 12 |
| [09 UI, Error Handling, Testing, and Delivery](design/09_ui_error_testing_delivery.md) | UI, replayability, testing, phased delivery, acceptance criteria, resolved decisions | 13-18 |

## Implementation Modules

| Module | Scope |
| --- | --- |
| [Implementation README](implementation/README.md) | Execution rules and PR slice overview |
| [PR Reading Guide](implementation/reading_guide.md) | Minimal required context by PR |
| [PR 1a](implementation/pr_01a_minimal_trading_foundation.md) | Minimal trading foundation |
| [PR 1b](implementation/pr_01b_portfolio_intents_relationship_graph.md) | Portfolio intents and relationship graph |
| [PR 2](implementation/pr_02_provider_resilience_signal_mvp.md) | Provider resilience and three-family signal MVP |
| [PR 3](implementation/pr_03_strategy_matching_replay.md) | Strategy matching and historical replay |
| [PR 4](implementation/pr_04_position_sizing_risk_manager.md) | Position sizing and risk manager |
| [PR 5](implementation/pr_05_trading_decision_agent_guardrails.md) | Trading decision agent guardrails |
| [PR 6](implementation/pr_06_paper_stock_broker_portfolio_state.md) | Alpaca-backed paper stock broker and portfolio state |
| [PR 7](implementation/pr_07_paper_options_assignment_risk.md) | Paper options and assignment risk |
| [PR 8](implementation/pr_08_intraday_refresh_rebalance.md) | Intraday refresh and rebalance |
| [PR 9](implementation/pr_09_reflection_learning_factors.md) | Reflection and learning factors |
| [PR 10](implementation/pr_10_strategy_evolution.md) | Strategy evolution |
| [PR 11](implementation/pr_11_today_dashboard_ui.md) | Today dashboard UI |
| [PR 12](implementation/pr_12_scheduler_smoke_deploy_docs.md) | Scheduler, smoke tests, and deploy docs |
| [PR 13](implementation/pr_13_live_preopen_pipeline.md) | Live preopen pipeline |

## Equivalence Policy

This split is organizational only. A module may clarify ownership and dependencies, but it must not weaken these original design guarantees:

- Python orchestration owns state transitions and side effects.
- LLM outputs are bounded, versioned, validated, retried, persisted, and downgraded to safe fallbacks on failure.
- All trading, replay, reflection, and learning paths use point-in-time source availability.
- Macro context constrains risk and strategy eligibility; it does not directly rank individual stocks or create macro-only single-name bearish trades.
- Common-stock paper trading is long-only in V2.
- PR 6 common-stock paper execution/account state is Alpaca paper-backed; local paper stock tables are audit/reconciliation mirrors.
- Options are paper/simulation-only and limited to the initial whitelist until a later design revision changes it.
- Manual ticker review forces evaluation only; it never bypasses liquidity, data, strategy, confidence, sizing, or risk gates.
- Strategy evolution and learning factors use lifecycle gates before they can expand risk.
