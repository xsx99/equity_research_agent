# Trading Runtime Compatibility Surface

`src/trading/runtime/` is now a compatibility package. It preserves the stable scheduler and script
import surface while canonical runtime code lives under `src/trading/phases/`.

Use the old `runtime.*` paths when maintaining existing callers or tests that intentionally assert
backward compatibility. For new navigation, start in `src/trading/phases/`.

## Stable Public Surface

`src/trading/runtime/__init__.py` still exposes:

- `TRADING_JOB_PHASES`
- `AVAILABLE_SMOKE_MODES`
- `run_job_phase(...)`
- `run_smoke_mode(...)`

Those names are re-exported from `src/trading/phases/_shell/`.

## Canonical Homes

- `src/trading/phases/_shell/`
  Scheduler facade, dispatch table, runtime support helpers, smoke entrypoints, and smoke modes.
- `src/trading/phases/preopen/`
  Live preopen facade, runner, dependency assembly, and risk wiring.
- `src/trading/phases/manual_review/`
  Live manual-review runtime plus manual request helpers.
- `src/trading/phases/intraday/`
  Live intraday refresh facade, runner, dependencies, helpers, rebalance, news alerts, and signals.
- `src/trading/phases/reflection/`
  Live reflection runtime plus reflection pipeline and learning-factor records.
- `src/trading/phases/strategy_evolution/`
  Live strategy-evolution runtime plus proposal and lifecycle pipeline records.
- `src/trading/phases/replay/`
  Smoke-only historical replay and outcome evaluation.

## Compatibility Shims

Every Python module under `src/trading/runtime/` re-exports one canonical module. These shims are
intentional and preserve existing scheduler jobs, smoke scripts, tests, and monkeypatch seams.

Fast navigation:

- Scheduler or CLI routing: `phases/_shell/facade.py` -> `phases/_shell/dispatch.py`
- Live preopen behavior: `phases/preopen/__init__.py` -> `runner.py` -> `dependencies.py` or `risk.py`
- Live intraday behavior: `phases/intraday/__init__.py` -> `runner.py` -> `helpers.py`
- Post-close behavior: `phases/reflection/` or `phases/strategy_evolution/`
- Fixture smoke behavior: `phases/_shell/smoke.py` -> relevant smoke module
