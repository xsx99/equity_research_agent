# Trading Runtime Navigation

`src/trading/runtime/` is the scheduler-facing shell for the trading system.

Use this package when you want to answer one of these questions:

- Which phase runs for a scheduler or CLI command?
- Where does a live phase assemble its dependencies?
- Which code is fixture-only smoke coverage versus production runtime logic?

## Start Here

Read files in this order when tracing a phase:

1. `__init__.py`
   Exposes the stable package surface: `TRADING_JOB_PHASES`, `AVAILABLE_SMOKE_MODES`, `run_job_phase(...)`, and `run_smoke_mode(...)`.
2. `facade.py`
   Thin public entrypoints used by scheduler and scripts.
3. `dispatch.py`
   Maps phase names and smoke mode names to concrete handlers.

If the problem is "what actually runs for `preopen` or `reflection`?", `dispatch.py` is the fastest answer.

## Live Phase Modules

- `preopen.py`
  Public facade for the live preopen phase.
- `manual_review.py`
  Live runtime for active manual review requests.
- `intraday_refresh.py`
  Public facade for the live intraday refresh phase.
- `reflection.py`
  Live runtime wrapper that loads same-day inputs and decides whether reflection should run or be skipped.
- `strategy_evolution.py`
  Live runtime wrapper around the post-close strategy-evolution pipeline.

These facade files are intentionally small. If you land in one of them and still need details, jump to the phase-specific internal modules next.

## Internal Split Modules

### Preopen

- `preopen_dependencies.py`
  Dependency assembly and repository-backed loaders.
- `preopen_risk.py`
  Risk workflow wiring used by the live morning path.
- `preopen_runner.py`
  Main orchestration for the preopen phase.

### Intraday Refresh

- `intraday_refresh_dependencies.py`
  Repository-backed loaders and dependency assembly.
- `intraday_refresh_helpers.py`
  Payload shaping and intraday helper functions.
- `intraday_refresh_runner.py`
  Main orchestration for the intraday refresh phase.

## Smoke Runtime Modules

Smoke paths stay under `src/trading/runtime/` because they share the same operator surface, but they are fixture-first verification code, not production live runtime.

- `smoke.py`
  Stable smoke facade and `AVAILABLE_SMOKE_MODES`.
- `smoke_entrypoints.py`
  Stable smoke entrypoint functions.
- `smoke_fixture_modes.py`
  Preopen/manual/intraday/replay/db/paper smoke handlers.
- `smoke_post_close_modes.py`
  Reflection and strategy-evolution smoke handlers.
- `smoke_support.py`
  Shared fixture builders, fake broker, deterministic clocks, and agent stubs.

If the issue only reproduces in `scripts/run_trading_smoke_test.py`, start with `smoke.py` and then go straight to the relevant smoke module rather than the live phase runtime.

## Shared Support

- `support.py`
  Cross-phase helpers for live runtime reporting, strategy bootstrap, and default provider wiring.

## Fast Navigation Patterns

- Scheduler or CLI routing issue:
  `facade.py` -> `dispatch.py` -> target phase facade
- Live preopen behavior issue:
  `preopen.py` -> `preopen_runner.py` -> `preopen_dependencies.py` or `preopen_risk.py`
- Live intraday behavior issue:
  `intraday_refresh.py` -> `intraday_refresh_runner.py` -> `intraday_refresh_helpers.py`
- Post-close skip or request-building issue:
  `reflection.py` or `strategy_evolution.py`
- Fixture smoke issue:
  `smoke.py` -> `smoke_fixture_modes.py` or `smoke_post_close_modes.py`

## What Is Not Here

- Trading domain logic lives outside this package:
  `src/trading/workflows/`, `src/trading/intraday/`, `src/trading/post_close/`, `src/trading/risk/`, and `src/trading/repositories/`
- Old root-level compatibility shims under `src/trading/` were removed. The canonical runtime paths are all under `src/trading/runtime/`.
