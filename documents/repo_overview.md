# Repository Overview

## Agent LLM Configuration

Agent model selection is centralized in `src/core/config.py`, with provider construction in
`src/agents/llm_models.py`.

- Research and trading-decision agents default to `gemini-2.5-flash-lite` through
  `RESEARCH_MODEL_NAME` and `TRADING_MODEL_NAME`.
- Post-close reflection and strategy evolution default to OpenRouter's `moonshotai/kimi-k2.6`
  through `REFLECTION_MODEL_NAME` and `STRATEGY_EVOLUTION_MODEL_NAME`.
- Gemini models use `GOOGLE_API_KEY`; OpenRouter-hosted models use `OPENROUTER_API_KEY` and
  `OPENROUTER_BASE_URL`.

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

Scheduler orchestration now lives under `src/trading/phases/`.

- `src/trading/phases/preopen/` owns the live preopen facade, runner, dependency assembly, and
  preopen risk wiring.
- `src/trading/phases/manual_review/` owns the live manual-review runtime plus manual request
  contracts and SQLAlchemy request helpers. Its dependency graph reuses the canonical preopen
  builder directly.
- `src/trading/phases/intraday/` owns the live intraday refresh facade, runner, dependency assembly,
  payload helpers, rebalance pipeline, news alerts, and intraday signal records.
- `src/trading/phases/reflection/` owns the live post-close reflection runtime and reflection
  pipeline/learning-factor records.
- `src/trading/phases/strategy_evolution/` owns the live post-close strategy-evolution runtime and
  proposal/lifecycle pipeline records.
- `src/trading/phases/replay/` owns historical replay and outcome evaluation. It is smoke-only
  today, not wired as a scheduler phase.
- `src/trading/phases/_shell/` owns the cross-phase scheduler facade, dispatch table, runtime
  support helpers, and smoke entrypoints/modes.
- Old `src/trading/runtime/preopen*`, `runtime/manual_review.py`, `runtime/intraday_refresh*`,
  `runtime/reflection.py`, `runtime/strategy_evolution.py`, `runtime/{facade,dispatch,support,smoke*}`,
  `src/trading/manual_review/*`, `src/trading/intraday/*`, `src/trading/post_close/*`, and
  `src/trading/replay/*` paths are compatibility shims that preserve existing caller imports and
  monkeypatch seams.
- `src/trading/trade_day.py` and `src/trading/risk/lookahead_risk.py` are the canonical homes for
  the shared trade-day and lookahead-risk utilities; old `runtime.*` paths remain shims.
- `src/trading/strategies/policy.py` is the canonical home for shared strategy policy helpers such
  as `experimental_strategy_weight_cap`; `post_close/strategy_policy.py` remains a shim.
