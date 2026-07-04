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

## Trading Phase Packages

Morning scheduler orchestration now lives under `src/trading/phases/`.

- `src/trading/phases/preopen/` owns the live preopen facade, runner, dependency assembly, and
  preopen risk wiring.
- `src/trading/phases/manual_review/` owns the live manual-review runtime plus manual request
  contracts and SQLAlchemy request helpers. Its dependency graph reuses the canonical preopen
  builder directly.
- `src/trading/phases/intraday/` owns the live intraday refresh facade, runner, dependency assembly,
  payload helpers, rebalance pipeline, news alerts, and intraday signal records.
- Old `src/trading/runtime/preopen*`, `runtime/manual_review.py`, `runtime/intraday_refresh*`,
  `src/trading/manual_review/*`, and `src/trading/intraday/*` paths are compatibility shims that
  preserve existing caller imports and monkeypatch seams.
- `src/trading/trade_day.py` and `src/trading/risk/lookahead_risk.py` are the canonical homes for
  the shared trade-day and lookahead-risk utilities; old `runtime.*` paths remain shims.
