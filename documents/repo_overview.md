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
