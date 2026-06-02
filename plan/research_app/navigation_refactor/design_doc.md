# Navigation Refactor Design Doc

## Goal

Reduce navigation and comprehension cost without changing research, trading, scheduler, web, smoke, or test behavior.

## Current Problem

The current layout overloads a few names:

- `src/trading/pipeline.py` contains multiple V2 workflow entrypoints.
- `src/trading/repository.py` is an in-memory artifact store, not a Postgres repository.
- `src/tools/` mixes agent-callable tool wrappers with real external API providers.
- `src/research/pipeline.py` and `src/research/eval_pipeline.py` are legacy research workflows, but their names compete with trading pipelines.

## Target Shape

Use package names that describe responsibility:

```text
src/trading/
  workflows/          # orchestration entrypoints
  signals/            # signal source contracts, PIT helpers, builders, snapshots, ingestion
  strategies/         # catalog, matching, selection, classification, taxonomy, calibration
  data_sources/        # universe contracts and provider resilience guardrails
  manual_review/       # manual ticker request state and service helpers
  portfolio/           # portfolio intent contracts for core-holding eligibility
  relationships/       # source-backed ticker relationship graph and peer baskets
  replay/              # historical replay and candidate outcome evaluation
  repositories/       # persistence implementations and protocols

src/research/
  workflows/          # legacy research/evaluation orchestration
  repositories/       # research DB helpers

src/providers/
  market_data/        # external market-data clients and helper contracts
  news_data/          # external news clients and helper contracts
  global_context/     # external macro/news context providers

src/tools/
  base.py
  context.py
  registry.py
  insider_db_tools.py # agent-callable DB tools
  market_data/        # agent-callable wrapper over providers.market_data
  news_data/          # agent-callable wrapper over providers.news_data
  global_context/     # agent-callable wrapper over providers.global_context
```

## Compatibility Policy

This refactor may update import paths throughout the app and tests. Because the reorganized version has not been released, old root-level compatibility modules should be deleted after internal imports move to the new paths.

No business logic changes are in scope. Existing tests should continue to pass.

## Verification

- `source ~/.venv/bin/activate && pytest -q`
- `git diff --check`
