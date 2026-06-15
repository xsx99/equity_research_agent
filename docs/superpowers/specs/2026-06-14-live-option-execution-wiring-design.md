# Live Option Execution Wiring Design

**Date:** 2026-06-14

## Goal

Enable real simulated option execution through the existing local `PaperOptionBroker` for three live paths:

1. live preopen runtime tactical option trades
2. live intraday rebalance option lifecycle actions
3. live `risk_hedge_overlay` hedge orders

The target behavior is "real paper execution inside this repo": option orders, executions, positions, risk snapshots, and hedge decisions must all be persisted through the existing SQL-backed workflow and follow the current option lifecycle semantics.

## Agreed Scope

In scope:

- `preopen live runtime`
- `intraday rebalance`
- `risk_hedge_overlay`
- real simulated execution via the existing local `PaperOptionBroker`
- operator-facing execution controls and smoke coverage

Out of scope:

- manual review runtime
- external broker-backed option execution
- new option strategy types
- redesigning the option whitelist or option risk model beyond what is required to execute the existing paths safely

## Why The Current Live Path Still Does Not Execute Options

The current codebase already has most of the option domain pieces:

- expression-bucket-driven option plan generation
- `PaperOptionBroker`
- SQL persistence for option decisions, legs, orders, executions, positions, and hedge decisions
- preopen option assignment-risk checks
- `risk_hedge_overlay` materialization logic

The remaining gaps are wiring gaps, not missing option strategy logic.

### Gap 1: Preopen live execution does not inject an option broker

`build_live_preopen_dependencies(...)` constructs `PaperExecutionWorkflow` without `option_broker`, so tactical option trades and generated hedge overlays stop before execution even when `execute_paper_orders=True`.

### Gap 2: Intraday rebalance is still stock-exit-oriented

`IntradayRebalancePipeline` can emit option lifecycle actions such as `roll_option_strategy` and `adjust_option_strategy`, but its execution branch only materializes stock-style `reduce/exit` decisions and only injects a stock broker into `PaperExecutionWorkflow`.

### Gap 3: Intraday execution requests do not carry enough option payload

The intraday request assembly path carries option mark/Greek summaries, but it does not yet carry the concrete `option_strategy` execution payload required by `PaperExecutionWorkflow` for close/roll/adjust execution. Even if an option broker were injected, the intraday executor would not have enough state to run the existing option lifecycle path.

### Gap 4: Runtime execution policy is too coarse

The current operator flag is `execute_paper_orders`. It does not distinguish stock from option execution. Because options are riskier and still locally simulated, they need an explicit opt-in that is separate from stock order execution.

## Options Considered

### Option A: Minimal dependency injection only

Add `PaperOptionBroker` to preopen dependencies and stop there.

Pros:

- smallest change
- fixes preopen tactical option execution immediately

Cons:

- does not solve intraday option lifecycle execution
- does not solve live hedge overlay execution consistently across runtimes
- leaves the execution policy ambiguous

Verdict: insufficient.

### Option B: Reuse `PaperExecutionWorkflow` as the single live option executor

Inject `PaperOptionBroker` into live runtimes, extend intraday request context so it can build valid option execution payloads, and route both tactical and hedge option actions through `PaperExecutionWorkflow`.

Pros:

- preserves one lifecycle implementation
- keeps tactical options and hedge overlays on the same persistence contract
- avoids drift between preopen and intraday execution semantics

Cons:

- requires some intraday request-context plumbing
- needs explicit operator policy for option execution

Verdict: recommended.

### Option C: Build a second intraday-specific option executor

Keep preopen on `PaperExecutionWorkflow`, but build a separate intraday option execution path.

Pros:

- could be tailored for intraday-only actions

Cons:

- duplicates lifecycle behavior
- increases drift risk
- creates two persistence and audit paths for the same option book

Verdict: reject.

## Recommended Design

### 1. Keep `PaperExecutionWorkflow` as the only option executor

All live option execution should continue to flow through the existing `PaperExecutionWorkflow`:

- tactical preopen option trades
- intraday option lifecycle actions
- generated `risk_hedge_overlay` executions

No new executor should be introduced.

### 2. Add explicit live option execution policy

Add a separate runtime policy for options.

Recommended contract:

- `execute_paper_orders`: enables stock paper execution
- `execute_paper_option_orders`: enables option paper execution

Option execution should require both:

- the runtime is allowed to execute paper orders
- option execution is explicitly enabled

This prevents silently turning on option execution anywhere that currently only expects stock paper orders.

### 3. Wire `PaperOptionBroker` into preopen live dependencies

`build_live_preopen_dependencies(...)` should construct a shared `PaperOptionBroker` and pass it into `PaperExecutionWorkflow`.

When:

- `TradingDecisionPipeline` emits a tactical option decision, or
- `RiskManager` emits a generated hedge payload

the live preopen execution path should be able to persist:

- `option_strategy_decisions`
- `option_strategy_legs`
- `paper_option_orders`
- `paper_option_executions`
- `paper_option_positions`
- `option_risk_snapshots`
- `risk_hedge_decisions` when applicable

### 4. Make intraday execution payloads option-complete

The intraday request context path must carry enough option state for execution.

Required additions:

- current option strategy payload for open option positions
- option strategy type and lifecycle metadata
- enough information to close, roll, or adjust an existing option position through `PaperExecutionWorkflow`
- current position linkage for `risk_hedge_overlay` positions as well as tactical option positions

This should be loaded from the existing persisted trading decision / option position records rather than recomputed ad hoc inside intraday execution.

### 5. Let intraday rebalance execute approved option lifecycle actions

`IntradayRebalancePipeline` should stop assuming that live execution only means stock `reduce/exit`.

It should:

- create execution-side `TradingDecisionRecord` and `RiskDecisionRecord` objects for approved option actions
- attach the option payload from intraday request metadata
- invoke `PaperExecutionWorkflow` with both stock and option brokers

Supported executed actions should include:

- `close_option_strategy`
- `roll_option_strategy`
- `adjust_option_strategy`

`open_new` should remain governed by the existing intraday open-new guardrails.

### 6. Keep hedge overlays on the same live execution path

`risk_hedge_overlay` should not get a separate live executor.

The live behavior should remain:

1. lookahead risk produces `portfolio_risk_intent`
2. residual approved exposure materializes `generated_hedge_action`
3. the execution workflow converts that into a synthetic `risk_hedge_overlay` option decision
4. `PaperOptionBroker` executes and persists the lifecycle

The missing work is only the live broker injection and the intraday execution plumbing.

## File-Level Design

### Runtime and dependency wiring

- `src/core/config.py`
  - add execution-policy config for option paper orders
- `src/trading/runtime/preopen.py`
  - extend public runtime signature if needed
- `src/trading/runtime/preopen_runner.py`
  - pass the option execution policy into execution
- `src/trading/runtime/preopen_dependencies.py`
  - build and inject `PaperOptionBroker`
- `src/trading/runtime/intraday_refresh.py`
  - extend public runtime signature if needed
- `src/trading/runtime/intraday_refresh_runner.py`
  - pass option execution policy into rebalance execution
- `src/trading/runtime/intraday_refresh_dependencies.py`
  - build and inject `PaperOptionBroker`
- `src/trading/runtime/facade.py`
  - preserve dry-run defaults while allowing config-driven live execution in scheduler paths

### Intraday request-context and execution payloads

- `src/trading/runtime/intraday_refresh_helpers.py`
  - add option execution metadata to intraday requests
- `src/trading/repositories/sqlalchemy.py`
  - load the latest option execution context for intraday request assembly
- `src/trading/intraday/rebalance.py`
  - execute approved option lifecycle actions through `PaperExecutionWorkflow`

### Operator surfaces and smoke tests

- `scripts/run_trading_once.py`
  - add explicit option-execution CLI switch for live preopen and intraday runs
- `scripts/run_trading_live_preopen_order_smoke.py`
  - add a real option execution smoke mode
- `tests/scripts/test_run_trading_once.py`
  - lock the new CLI contract
- `tests/scripts/test_run_trading_live_preopen_order_smoke.py`
  - lock the live option smoke contract
- `documents/research_app/runbook.md`
  - document safe option-execution steps and verification queries

## Safety Rules

- Default remains dry-run for both scheduler and CLI.
- Stock and option execution toggles must be explicit.
- Manual review stays out of scope and unchanged.
- Option execution continues to rely on the existing option whitelist.
- Intraday option execution must continue to respect stale option data and event-through-expiry guards.
- No external broker integration is introduced.

## Future Work

### Manual review execution contract

Manual review is intentionally excluded from this slice.

Current design allows:

- `review_only`: never execute
- `paper_trade_eligible`: may execute if normal gates pass

This plan does not change that contract. A future slice should decide whether the product should:

- preserve `paper_trade_eligible`, or
- simplify manual review to watch-only for both stock and option paths

before any manual-review option execution wiring is added.

## Test Strategy

The implementation should add or extend tests in these groups:

- `tests/trading/test_runtime_live.py`
  - preopen live option broker wiring
- `tests/trading/test_runtime_intraday_live.py`
  - live intraday option execution wiring
- `tests/trading/test_intraday_rebalance.py`
  - option lifecycle execution records and guardrails
- `tests/trading/test_paper_stock_broker.py`
  - end-to-end option lifecycle and hedge overlay persistence
- `tests/scripts/test_run_trading_once.py`
  - CLI execution policy surface
- `tests/scripts/test_run_trading_live_preopen_order_smoke.py`
  - live preopen option smoke

## Success Criteria

This design is complete when:

- live preopen tactical option trades can execute through `PaperOptionBroker`
- live preopen generated hedge overlays can execute through `PaperOptionBroker`
- live intraday approved option lifecycle actions can execute through `PaperOptionBroker`
- all executed option actions persist the full existing option audit trail
- stock dry-run / execute behavior remains unchanged unless option execution is explicitly enabled
- manual review remains excluded and documented as future work
