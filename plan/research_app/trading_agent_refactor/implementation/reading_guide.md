# Trading Agent Refactor PR Reading Guide

Use this guide when implementing one PR slice. The goal is to give a coding agent enough context to implement the current slice without loading the entire design doc or every future PR.

## Required Startup Reading

Every PR implementation session must read:

1. `documents/general_instructions.md`
2. [Module Contracts](../module_contracts.md)
3. [Implementation README](README.md)
4. The current PR module under this directory
5. [Progress tracker](../progress_tracker.md)

Then read only the design modules listed for the target PR below. Expand beyond that list only when the code you touch crosses into another contract producer/consumer.

## Design Module Key

| ID | Module |
| --- | --- |
| D01 | [Context, Goals, and Approach](../design/01_context_goals_approach.md) |
| D02 | [Target Architecture](../design/02_target_architecture.md) |
| D03 | [Strategy Architecture](../design/03_strategy_architecture.md) |
| D04 | [Signal Snapshots and Point-in-Time Data](../design/04_signal_snapshots.md) |
| D05 | [Workflows and Decision Contracts](../design/05_workflows_and_decision_contracts.md) |
| D06 | [Paper Trading and Risk](../design/06_paper_trading_and_risk.md) |
| D07 | [Replay, Reflection, and Learning](../design/07_replay_reflection_learning.md) |
| D08 | [Data Model](../design/08_data_model.md) |
| D09 | [UI, Error Handling, Testing, and Delivery](../design/09_ui_error_testing_delivery.md) |

## PR Reading Matrix

| PR | Current PR Module | Required Design Modules | Contract Focus | Read Upstream Artifacts |
| --- | --- | --- | --- | --- |
| PR 1a | [Minimal Trading Foundation](pr_01a_minimal_trading_foundation.md) | D02, D03, D08 | G2, G3, G5; strategy catalog, prompt registry, trade taxonomy | Existing DB model conventions, existing agent/prompt patterns |
| PR 1b | [Portfolio Intents + Relationship Graph](pr_01b_portfolio_intents_relationship_graph.md) | D03, D08 | G5; relationship graph; `core_holding` intent approval | PR 1a taxonomy and strategy models if already implemented |
| PR 2 | [Provider Resilience + Signal MVP](pr_02_provider_resilience_signal_mvp.md) | D02, D04, D05, D08 | G1, G7; universe, manual requests, provider resilience, PIT snapshots | PR 1a/1b schema/helpers; existing market-data/provider code |
| PR 3 | [Strategy Matching + Replay](pr_03_strategy_matching_replay.md) | D03, D04, D07, D08 | G1, G5, G6; candidate scores, trade classification, outcome evaluator | PR 1a strategy catalog; PR 2 signal snapshots and manual requests |
| PR 4 | [Position Sizing + Risk Manager](pr_04_position_sizing_risk_manager.md) | D03, D05, D06, D08 | G4, G5, G6, G8; `PortfolioContext` / `RiskContext`, risk presets, hard rails | PR 3 candidates/classifications; fixture-based risk context |
| PR 5 | [Trading Decision Agent Guardrails](pr_05_trading_decision_agent_guardrails.md) | D02, D05, D08 | G2, G3, G4, G5, G7; validated LLM decisions, prompt telemetry, no orders | PR 3 selected candidates/classifications; PR 4 risk context |
| PR 6 | [Paper Stock Broker + Portfolio State](pr_06_paper_stock_broker_portfolio_state.md) | D05, D06, D08 | G4; unified margin account, paper stock order state, portfolio snapshots | PR 4 risk contract; PR 5 validated decisions |
| PR 7 | [Paper Options + Assignment Risk](pr_07_paper_options_assignment_risk.md) | D03, D05, D06, D08 | G4, G5, G8; whitelisted option plans, leg risk, assignment risk | PR 4 risk contract; PR 6 portfolio account state |
| PR 8 | [Intraday Refresh + Rebalance](pr_08_intraday_refresh_rebalance.md) | D04, D05, D06, D08 | G1, G3, G4, G8; intraday deltas, alerts, rebalance gates | PR 2 baseline snapshots; PR 6/7 positions and option state |
| PR 9 | [Reflection + Learning Factors](pr_09_reflection_learning_factors.md) | D02, D05, D07, D08 | G1, G3; replay outcomes, reflection fallback, learning lifecycle | PR 3 outcome rows; PR 6/7/8 trading artifacts |
| PR 10 | [Strategy Evolution](pr_10_strategy_evolution.md) | D03, D05, D07, D08 | G2, G3; strategy proposals, duplicate control, lifecycle gates | PR 9 learning/proposal hints; PR 3 outcome evidence |
| PR 11 | [Today Dashboard UI](pr_11_today_dashboard_ui.md) | D08, D09 | UI contract; read-only audit views; limited user config/manual-request mutations | All implemented repositories/read models for tabs being built |
| PR 12 | [Scheduler, Smoke Tests, Deploy Docs](pr_12_scheduler_smoke_deploy_docs.md) | D04, D05, D06, D09 | Operational flow, standalone smoke tests, persistent Postgres storage | All completed pipeline entrypoints and existing scheduler/deploy docs |

## PR 11 Tab-Specific Expansion

PR 11 is the only slice where reading more design context is often justified, because the UI displays artifacts from every prior pipeline. Start with D08 and D09, then read the module for the tab being implemented:

| UI Area | Add Design Module |
| --- | --- |
| Strategy catalog, candidate explanations, manual review, relationship/core-intent views | D03 |
| Signal snapshot audit and source availability details | D04 |
| Trade decision, manual request mode, intraday alert/rebalance audit | D05 |
| Portfolio, margin account, option risk, assignment risk, factor exposure | D06 |
| Reflection, learning factors, strategy performance, replay outcomes | D07 |

## PR 2 Live API Smoke

PR 2 live provider checks are opt-in and should stay outside normal unit tests. Use the standalone source-ingestion smoke script from the PR 2 worktree when you need to verify the real provider path:

```bash
source ~/.venv/bin/activate
LOG_LEVEL=WARNING python scripts/run_trading_source_ingestion_smoke.py \
  --env-file /Users/shuxinxu/repos/equity_research_agent/.env \
  --ticker AAPL \
  --families technical \
  --json
```

The default/cheap path is `technical` only and should make one market-data request. To verify the full PR 2 adapter path, run:

```bash
source ~/.venv/bin/activate
LOG_LEVEL=WARNING python scripts/run_trading_source_ingestion_smoke.py \
  --env-file /Users/shuxinxu/repos/equity_research_agent/.env \
  --ticker AAPL \
  --families technical fundamental events_news \
  --json
```

This smoke script uses in-memory repositories only. It does not write to Postgres, does not create trading decisions, and does not call an LLM. `LOG_LEVEL=WARNING` keeps HTTP client INFO logs from printing provider query parameters. The command should report `status=passed`, source records for each requested family, and `ProviderRequestRun` statuses for `market_bars`, `market_context`, and `news` when the full path is requested.

## When To Read More

Broaden the context only for one of these reasons:

- The current PR changes a producer or consumer listed in [Module Contracts](../module_contracts.md).
- A test or implementation touches an upstream table, service, or schema not covered by the required modules.
- The progress tracker says a design decision superseded the module text.
- Existing code diverges from the plan and the discrepancy affects the current PR contract.
- You are implementing PR 11 and a specific tab needs audit detail from another design module.

## What Not To Read By Default

Do not load all design modules or all PR modules at session start. Future PR modules are context only when the current PR explicitly produces data that a future consumer contract requires. Older PR modules are context only when their implemented artifacts are direct dependencies.

The old compatibility indexes were removed during cleanup. Use this modular directory as the source of truth.

## Implementation Handoff Checklist

Before writing code for a PR:

1. Confirm the target PR and current tracker status.
2. Read the required startup documents.
3. Read the PR's required design modules from the matrix.
4. Identify the producer/consumer rows in [Module Contracts](../module_contracts.md).
5. Inspect existing code and tests for the files named in the PR module.
6. Write failing tests first, following the current PR module.
7. After implementation, update the progress tracker with files changed, commands run, results, and known gaps.
