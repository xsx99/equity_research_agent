# Repository Overview

## Trading Decision Package

Trade-decision generation now lives under `src/trading/decision/`.

- `src/trading/decision/pipeline.py` is the canonical home for `TradingDecisionPipeline`,
  `TradingDecisionPipelineResult`, and `TradingDecisionRecord`.
- `src/trading/decision/option_strategy_builder/` contains the option strategy helper family:
  `policy.py`, `chain.py`, `payload.py`, and `evidence.py`, with `__init__.py` as the explicit
  helper hub.
- `src/trading/workflows/trading_decision.py` and
  `src/trading/workflows/option_strategy_builder.py` are compatibility shims that preserve existing
  workflow import paths and helper object identity.

## Trading Capability Packages

The remaining trading workflow implementations now live in their capability packages.

- `src/trading/execution/paper_execution.py` and
  `src/trading/execution/paper_execution_options.py` own paper stock/option execution next to the
  existing execution attempt records.
- `src/trading/signals/pipeline.py`, `src/trading/strategies/scoring.py`,
  `src/trading/portfolio/sync.py`, and `src/trading/data_sources/universe_scan.py` own the signal,
  strategy, portfolio-sync, and universe-scan pipeline adapters.
- `src/trading/workflows/` is now a compatibility layer: its modules explicitly re-export the old
  import surfaces while callers migrate in later slices.
