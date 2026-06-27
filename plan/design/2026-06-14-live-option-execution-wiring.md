# Live Option Execution Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing local `PaperOptionBroker` into live preopen, live intraday rebalance, and `risk_hedge_overlay` execution so approved option actions persist real simulated orders, executions, positions, and hedge artifacts.

**Architecture:** Reuse `PaperExecutionWorkflow` as the single option executor instead of creating a second intraday-specific option path. Add an explicit option-execution policy, inject `PaperOptionBroker` into the live dependency graph, carry option execution payloads through intraday request assembly, and let both tactical option trades and hedge overlays execute through the existing SQL-backed lifecycle flow.

**Tech Stack:** Python, pytest, SQLAlchemy ORM, existing trading runtime package, `PaperExecutionWorkflow`, `PaperOptionBroker`, existing CLI/smoke scripts.

---

## File Map

### Runtime wiring and execution policy

- Modify: `src/core/config.py`
- Modify: `src/trading/runtime/preopen.py`
- Modify: `src/trading/runtime/preopen_runner.py`
- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/facade.py`
- Modify: `scripts/run_trading_once.py`

### Intraday option execution context

- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/intraday/rebalance.py`

### Verification and operator docs

- Modify: `scripts/run_trading_live_preopen_order_smoke.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

### Tests

- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/scripts/test_run_trading_once.py`
- Test: `tests/scripts/test_run_trading_live_preopen_order_smoke.py`

## Scope Guardrails

- Do not change manual review behavior in this plan.
- Do not add new option strategy types.
- Do not add external broker-backed option execution.
- Keep dry-run as the default for both scheduler and CLI surfaces.
- Option execution must require explicit opt-in separate from stock execution.

### Task 1: Add Explicit Live Option Execution Policy

**Files:**
- Modify: `src/core/config.py`
- Modify: `src/trading/runtime/preopen.py`
- Modify: `src/trading/runtime/preopen_runner.py`
- Modify: `src/trading/runtime/intraday_refresh.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/facade.py`
- Modify: `scripts/run_trading_once.py`
- Test: `tests/scripts/test_run_trading_once.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing execution-policy tests**

```python
def test_live_preopen_requires_explicit_option_execution_flag():
    result = run_live_preopen_once(
        execute_paper_orders=True,
        execute_paper_option_orders=False,
    )
    assert result["execution"]["option_orders_submitted"] == 0


def test_run_trading_once_exposes_execute_paper_option_orders_flag():
    exit_code = run_trading_once.main(
        [
            "--phase",
            "preopen",
            "--mode",
            "live-preopen",
            "--execute-paper-orders",
            "--execute-paper-option-orders",
            "--json",
        ]
    )
    assert exit_code == 0
```

- [ ] **Step 2: Run the focused execution-policy tests**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_once.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py -k "option and execute" -q`

Expected: FAIL because the live runtime and CLI only expose the stock-level `execute_paper_orders` switch today.

- [ ] **Step 3: Add minimal config and runtime plumbing**

```python
def run_live_preopen_once(
    *,
    execute_paper_orders: bool = False,
    execute_paper_option_orders: bool = False,
    ...
) -> dict[str, object]:
    ...
```

```python
if execute_paper_option_orders and not execute_paper_orders:
    raise ValueError("option_execution_requires_paper_order_execution")
```

- [ ] **Step 4: Extend runtime reports so option execution is visible**

```python
execution = {
    "mode": mode,
    "orders_submitted": stock_count,
    "option_orders_submitted": option_count,
}
```

- [ ] **Step 5: Re-run the focused execution-policy tests**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_once.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py -k "option and execute" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/config.py src/trading/runtime/preopen.py src/trading/runtime/preopen_runner.py \
  src/trading/runtime/intraday_refresh.py src/trading/runtime/intraday_refresh_runner.py \
  src/trading/runtime/facade.py scripts/run_trading_once.py \
  tests/scripts/test_run_trading_once.py tests/trading/test_runtime_live.py \
  tests/trading/test_runtime_intraday_live.py
git commit -m "feat: add explicit live option execution policy"
```

### Task 2: Wire `PaperOptionBroker` Into Live Preopen Execution

**Files:**
- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/runtime/preopen_runner.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing preopen wiring tests**

```python
def test_live_preopen_dependencies_build_paper_option_broker_for_execution():
    dependencies = build_live_preopen_dependencies(session)
    assert dependencies.paper_execution_workflow.option_broker is not None


def test_live_preopen_executes_tactical_option_trade_when_option_execution_enabled():
    result = runtime.run()
    assert result["execution"]["option_orders_submitted"] == 1
```

- [ ] **Step 2: Run the focused preopen option tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py -k "preopen and option" -q`

Expected: FAIL because the live preopen dependency builder does not inject `option_broker`, so option execution is skipped.

- [ ] **Step 3: Inject a shared `PaperOptionBroker` into live preopen dependencies**

```python
option_broker = PaperOptionBroker()
paper_execution_workflow = PaperExecutionWorkflow(
    repository=trading_repository,
    broker=broker,
    option_broker=option_broker,
    ...
)
```

- [ ] **Step 4: Count stock and option submissions separately in the preopen runtime report**

```python
submitted_stock_orders = tuple(getattr(result, "paper_orders", ()))
submitted_option_orders = tuple(getattr(result, "paper_option_orders", ()))
```

- [ ] **Step 5: Re-run the focused preopen option tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py -k "preopen and option" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/runtime/preopen_dependencies.py src/trading/runtime/preopen_runner.py \
  src/trading/workflows/paper_execution.py tests/trading/test_runtime_live.py \
  tests/trading/test_paper_stock_broker.py
git commit -m "feat: wire live preopen option execution"
```

### Task 3: Load Option Execution Context For Intraday Requests

**Files:**
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_rebalance.py`

- [ ] **Step 1: Write the failing intraday context tests**

```python
def test_intraday_request_context_includes_latest_option_strategy_payload():
    context = repository.load_intraday_request_contexts(...)
    assert "option_strategy" in context["NVDA"].metadata_json


def test_build_rebalance_request_carries_option_strategy_payload_for_option_positions():
    request = _build_rebalance_request(...)
    assert request.metadata_json["option_strategy"]["option_strategy_type"] == "long_call"
```

- [ ] **Step 2: Run the focused intraday context tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py -k "option and context" -q`

Expected: FAIL because intraday request context currently carries marks and Greeks but not the concrete option execution payload needed by `PaperExecutionWorkflow`.

- [ ] **Step 3: Extend intraday request-context loading with option execution metadata**

```python
contexts[ticker] = SimpleNamespace(
    ...,
    metadata_json={
        "option_strategy": latest_decision.metadata_json.get("option_strategy"),
        "option_strategy_type": latest_position.option_strategy_type,
        "paper_option_position_id": latest_position.paper_option_position_id,
    },
)
```

- [ ] **Step 4: Merge repository-loaded option metadata into intraday rebalance requests**

```python
metadata_json = {
    ...existing_fields,
    **dict(getattr(context, "metadata_json", {}) or {}),
}
```

- [ ] **Step 5: Re-run the focused intraday context tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py -k "option and context" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/repositories/sqlalchemy.py src/trading/runtime/intraday_refresh_helpers.py \
  tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py
git commit -m "feat: carry option execution context into intraday requests"
```

### Task 4: Execute Intraday Option Lifecycle Actions Through `PaperExecutionWorkflow`

**Files:**
- Modify: `src/trading/intraday/rebalance.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing intraday execution tests**

```python
def test_intraday_rebalance_executes_close_option_strategy_when_option_execution_enabled():
    result = runtime.run()
    assert result["execution"]["option_orders_submitted"] == 1


def test_intraday_rebalance_executes_roll_option_strategy_through_paper_execution_workflow():
    decision = pipeline.run(...).decisions[0]
    assert decision.action == "roll_option_strategy"
```

- [ ] **Step 2: Run the focused intraday execution tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py tests/trading/test_paper_stock_broker.py -k "intraday and option and (execute or roll or close or adjust)" -q`

Expected: FAIL because the intraday executor only materializes stock-style `exit/reduce` execution records and does not inject an option broker.

- [ ] **Step 3: Inject `PaperOptionBroker` into live intraday dependencies**

```python
rebalance_pipeline = IntradayRebalancePipeline(
    ...,
    broker=stock_broker,
    option_broker=option_broker,
)
```

- [ ] **Step 4: Build execution-side option trading decisions for approved intraday option actions**

```python
if request.instrument_type == "option" and decision.action in {
    "close_option_strategy",
    "roll_option_strategy",
    "adjust_option_strategy",
}:
    execution_decisions.append(_to_option_trading_decision(...))
```

- [ ] **Step 5: Route approved intraday option actions through `PaperExecutionWorkflow`**

```python
PaperExecutionWorkflow(
    repository=self.repository,
    broker=self.broker,
    option_broker=self.option_broker,
).run(...)
```

- [ ] **Step 6: Re-run the focused intraday execution tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py tests/trading/test_paper_stock_broker.py -k "intraday and option and (execute or roll or close or adjust)" -q`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/trading/intraday/rebalance.py src/trading/runtime/intraday_refresh_dependencies.py \
  src/trading/runtime/intraday_refresh_runner.py src/trading/workflows/paper_execution.py \
  tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py \
  tests/trading/test_paper_stock_broker.py
git commit -m "feat: execute intraday option lifecycle actions live"
```

### Task 5: Confirm Live `risk_hedge_overlay` Execution In Both Preopen And Intraday

**Files:**
- Modify: `src/trading/runtime/lookahead_risk.py` only if metadata gaps are discovered
- Modify: `src/trading/intraday/rebalance.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing live hedge-execution tests**

```python
def test_live_preopen_generated_hedge_executes_option_order_when_option_execution_enabled():
    assert result["execution"]["option_orders_submitted"] == 1


def test_live_intraday_generated_hedge_executes_option_order_when_option_execution_enabled():
    assert result["execution"]["option_orders_submitted"] == 1
```

- [ ] **Step 2: Run the focused hedge-execution tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py tests/trading/test_paper_stock_broker.py -k "hedge and option and execute" -q`

Expected: FAIL because preopen currently skips option execution without `option_broker`, and intraday execution does not yet route generated hedge actions through live option execution.

- [ ] **Step 3: Reuse the same option-execution path for generated hedges**

```python
if risk_decision.generated_hedge_action is not None:
    self._execute_generated_hedges(...)
```

- [ ] **Step 4: Verify audit rows remain separated from tactical option trades**

```python
assert trading_decision.trade_identity == "risk_hedge_overlay"
assert strategy_id == "risk_manager_hedge_overlay_v1"
```

- [ ] **Step 5: Re-run the focused hedge-execution tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py tests/trading/test_paper_stock_broker.py -k "hedge and option and execute" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/runtime/lookahead_risk.py src/trading/intraday/rebalance.py \
  src/trading/workflows/paper_execution.py tests/trading/test_runtime_live.py \
  tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py \
  tests/trading/test_paper_stock_broker.py
git commit -m "feat: execute live hedge overlays through option broker"
```

### Task 6: Add Live Option Smoke And Operator Documentation

**Files:**
- Modify: `scripts/run_trading_live_preopen_order_smoke.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Test: `tests/scripts/test_run_trading_live_preopen_order_smoke.py`

- [ ] **Step 1: Write the failing live option smoke tests**

```python
def test_live_preopen_order_smoke_can_run_option_execution_mode():
    result = run_smoke(ticker="NVDA", execute_paper_orders=True, execute_paper_option_orders=True)
    assert result["option_order"] is not None
```

- [ ] **Step 2: Run the focused live smoke tests**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_live_preopen_order_smoke.py -k option -q`

Expected: FAIL because the current live smoke only verifies stock order submission.

- [ ] **Step 3: Extend the smoke script and runbook**

```python
run_smoke(
    ticker="NVDA",
    execute_paper_orders=True,
    execute_paper_option_orders=True,
    force_expression_bucket="defined_risk_directional_option",
)
```

```markdown
1. Enable `execute_paper_orders`
2. Enable `execute_paper_option_orders`
3. Run the live preopen option smoke
4. Verify `paper_option_orders`, `paper_option_executions`, and `paper_option_positions`
```

- [ ] **Step 4: Re-run the focused live smoke tests**

Run: `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_live_preopen_order_smoke.py -k option -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_trading_live_preopen_order_smoke.py documents/research_app/runbook.md \
  plan/research_app/trading_agent_refactor/progress_tracker.md \
  tests/scripts/test_run_trading_live_preopen_order_smoke.py
git commit -m "feat: add live option execution smoke and docs"
```

## Recommended Execution Order

1. Task 1
   Reason: the execution-policy contract must be settled before wiring any live option broker.
2. Task 2
   Reason: preopen is the simplest live option path and validates the shared broker wiring.
3. Task 3
   Reason: intraday needs payload plumbing before execution can work.
4. Task 4
   Reason: once intraday can build option payloads, it can reuse the same execution workflow.
5. Task 5
   Reason: hedge overlays should be verified after both preopen and intraday option execution are live.
6. Task 6
   Reason: smoke/docs should validate the final operator surface, not an interim one.

## Exit Criteria

- Live preopen tactical option trades can execute through `PaperOptionBroker`.
- Live preopen generated `risk_hedge_overlay` orders can execute through `PaperOptionBroker`.
- Live intraday approved option lifecycle actions can execute through `PaperOptionBroker`.
- Live intraday generated hedge overlays can execute through `PaperOptionBroker`.
- Runtime reports distinguish stock and option order submission counts.
- Option execution remains dry-run by default and requires explicit opt-in.
- Manual review is excluded from implementation and documented as future work.
