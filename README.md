# Equity Trading Workstation

This repository now centers on an operator-facing equity trading workstation. The
main product surface is the `/today` dashboard plus the scheduler-driven trading
runtime behind it: universe selection, point-in-time signal snapshots, strategy
scoring, deterministic risk gating, paper execution, portfolio sync, and
post-close reflection.

The older watchlist-driven research workflow still exists in the repo and still
matters for audit and experimentation, but it is no longer the best mental model
for a new reader. If you are orienting yourself for the first time, start with
`src/trading/`, `src/web/routers/today.py`, `src/trading/runtime/`, and the
active design docs under `plan/`.

## What This Repo Demonstrates

- Trading-first architecture: `src/trading/` owns the pre-open, manual-review,
  intraday-refresh, reflection, and strategy-evolution runtime phases.
- Deterministic orchestration: Python owns persistence, state transitions,
  portfolio/risk logic, and paper execution; LLMs stay inside bounded,
  versioned, schema-validated decision surfaces.
- Point-in-time auditability: candidate generation, risk decisions, trading
  decisions, and replay/reflection inputs are stored with decision-time context
  so the system can be reviewed without reconstructing mutable external state.
- Operator-facing UI: `/today` is a trading workstation, not a research result
  list. The web layer is organized around read models, presenters, and tabbed
  operational workflows.
- Operational realism: Docker Compose deployment, persistent-disk Postgres
  requirements, smoke scripts, and scheduler jobs are treated as first-class
  parts of the product.

## System Overview

At a high level, the active trading stack looks like this:

1. Source ingestion and market context
   Normalized source tables capture technical, news/event, insider, social/macro,
   options, and calendar inputs with point-in-time availability metadata.
2. Pre-open decision chain
   Universe scan plus manual-review requests feed the signal snapshot, strategy
   scoring, trade classification, position sizing, risk, and trading-decision
   workflows.
3. Paper execution and portfolio state
   Approved stock decisions can route to Alpaca paper trading, option decisions
   stay in paper/simulation mode, and portfolio snapshots unify positions,
   buying power, and risk context.
4. Intraday and post-close loops
   Intraday refresh surfaces material changes and rebalance decisions; reflection
   and strategy-evolution paths analyze outcomes after the close.
5. Operator workstation and scheduling
   FastAPI serves the `/today` workstation, while APScheduler and standalone
   smoke entrypoints run the daily phases.

Simplified active flow:

```text
source ingestion -> universe/manual review -> signal snapshots -> strategy scoring
                 -> trade classification -> sizing/risk -> trading decisions
                 -> paper execution -> portfolio snapshots -> intraday/reflect
                 -> /today workstation
```

The legacy research flow still exists beside this stack:

```text
watchlist -> ResearchPipeline -> ResearchAgent -> research_runs/research_outputs
                                       -> EvalPipeline -> eval_results
```

That path is still useful for audit and experimentation, but it is no longer the
best summary of the repository.

## Repo Map

- [`src/trading/`](src/trading) active trading domain logic, runtime phases,
  workflows, risk, portfolio, replay, intraday, and post-close modules
- [`src/web/`](src/web) FastAPI app factory, `/today` router/loaders, presenters,
  templates, and UI filters
- [`src/db/`](src/db) SQLAlchemy models, sessions, and Alembic bootstrap
- [`src/scheduler/`](src/scheduler) APScheduler service and runtime job wiring
- [`src/research/`](src/research) legacy watchlist-driven research and eval path
- [`src/agents/`](src/agents) prompt registry plus trading/research/reflection
  agent wrappers and schemas
- [`src/providers/`](src/providers) market, news, and global-context adapters
- [`scripts/`](scripts) smoke entrypoints and one-off operational scripts
- [`documents/`](documents) deployment/runbook/general operational notes
- [`plan/`](plan) active design docs, implementation slices, and progress tracker
- [`tests/`](tests) unit and integration-style coverage across trading, web,
  research, scheduler, and provider surfaces

## Current Status

Implemented today:

- `/today` trading workstation with portfolio, trades, risk/macro, candidates,
  learning, and system views
- pre-open, manual-review, intraday-refresh, reflection, and strategy-evolution
  runtime phases
- point-in-time signal snapshots, deterministic strategy scoring, and replayable
  decision artifacts
- deterministic risk management plus paper stock and paper-option execution paths
- scheduler jobs, smoke tests, and Docker-based deployment plumbing
- legacy watchlist/research/eval workflow kept intact alongside the trading stack

Still intentionally incomplete or evolving:

- some naming and documentation cleanup still lags the trading-first architecture
- deeper live-data coverage and polish around certain runtime edges
- continued UI simplification and operator-surface cleanup
- broader learning-loop and strategy-evolution maturity beyond the current slices
