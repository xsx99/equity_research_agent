# Alpaca-Backed Option Paper Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local-simulated option execution backend with Alpaca paper-trading-backed option execution while preserving the repo's existing option strategy, risk, runtime, and audit semantics.

**Architecture:** Keep `PaperExecutionWorkflow` as the single option execution path, but make its option broker broker-native instead of locally self-filling. Persist Alpaca-tradable contract symbols and broker identifiers, build simple vs `mleg` payloads from saved strategy legs, and treat Alpaca account/position state as the live exposure source of truth while keeping local option tables as strategy-level mirrors.

**Tech Stack:** Python, pytest, SQLAlchemy ORM, Alembic, httpx, Alpaca Trading API, existing live trading runtimes and smoke scripts.

---

## File Map

### Broker contract and schema

- Modify: `src/trading/options/strategy.py`
- Modify: `src/db/models/trading.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/repositories/in_memory.py`
- Create: `alembic/versions/021_alpaca_option_execution_contract.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/trading/test_option_repository.py`

### Alpaca-backed option broker

- Modify: `src/trading/brokers/paper_option.py`
- Modify: `src/trading/brokers/paper_stock.py`
- Test: `tests/trading/test_paper_option_broker.py`
- Test: `tests/trading/test_paper_stock_broker.py`

### Workflow and lifecycle execution

- Modify: `src/trading/workflows/paper_execution.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

### Portfolio sync and reconciliation

- Modify: `src/trading/portfolio/state.py`
- Modify: `src/trading/workflows/portfolio_sync.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_portfolio.py`
- Test: `tests/trading/test_portfolio_sync.py`

### Runtime wiring, smoke coverage, and docs

- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `scripts/run_trading_live_preopen_order_smoke.py`
- Create: `scripts/run_trading_option_paper_execution.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/repo_overview.md`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/scripts/test_run_trading_live_preopen_order_smoke.py`
- Test: `tests/test_run_trading_option_paper_execution.py`

## Scope Guardrails

- Do not change manual-review behavior.
- Do not add new option strategy types beyond the current whitelist.
- Do not add live-money trading support.
- Do not keep a live-path local-fill fallback once `execute_paper_option_orders=True`.
- Treat Alpaca as the live account/position source of truth for options, not the local `paper_option_positions` overlay.

### Task 1: Persist Alpaca-Tradable Option Contract And Order Metadata

**Files:**
- Modify: `src/trading/options/strategy.py`
- Modify: `src/db/models/trading.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/repositories/in_memory.py`
- Create: `alembic/versions/021_alpaca_option_execution_contract.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`
- Test: `tests/trading/test_option_repository.py`

- [ ] **Step 1: Write the failing schema and repository tests**

```python
def test_option_strategy_legs_persist_contract_symbol_and_ratio_qty():
    decision = build_option_strategy_decision(
        legs=[
            {
                "contract_symbol": "AAPL250117C00190000",
                "ratio_qty": 1,
            }
        ]
    )
    assert decision.metadata_json["legs"][0]["contract_symbol"] == "AAPL250117C00190000"


def test_save_paper_option_order_persists_client_and_broker_ids(sqlalchemy_repository):
    order = PaperOptionOrderRecord(
        ...,
        client_order_id="2026-06-14:AAPL:earnings_drift_v1:open_option_strategy",
        broker_order_id="alpaca-option-order-1",
        order_class="mleg",
    )
    sqlalchemy_repository.save_paper_option_order(order)
    saved = sqlalchemy_repository.load_latest_paper_option_order(...)
    assert saved.client_order_id == order.client_order_id
    assert saved.broker_order_id == order.broker_order_id


def test_save_paper_option_execution_persists_broker_order_id(sqlalchemy_repository):
    execution = PaperOptionExecutionRecord(
        ...,
        broker_order_id="alpaca-option-order-1",
    )
    sqlalchemy_repository.save_paper_option_execution(execution)
    saved = sqlalchemy_repository.load_latest_paper_option_execution(...)
    assert saved.broker_order_id == execution.broker_order_id
```

- [ ] **Step 2: Run the focused persistence tests**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_option_repository.py -k "option and (contract or broker or client)" -q`

Expected: FAIL because option legs and option-order tables do not yet persist Alpaca-tradable contract identifiers or broker-native order identifiers.

- [ ] **Step 3: Extend the option strategy and ORM contracts**

```python
@dataclass(frozen=True)
class OptionLegDefinition:
    contract_symbol: str
    ratio_qty: int = 1
```

```python
class PaperOptionOrder(Base):
    broker_order_id = Column(String(128), nullable=True, index=True)
    client_order_id = Column(String(255), nullable=False)
    order_class = Column(String(16), nullable=False, default="simple", server_default="simple")
```

```python
class PaperOptionExecution(Base):
    broker_order_id = Column(String(128), nullable=True, index=True)
```

- [ ] **Step 4: Add the Alembic migration and repository mappings**

```python
op.add_column("paper_option_orders", sa.Column("broker_order_id", sa.String(length=128), nullable=True))
op.add_column("paper_option_orders", sa.Column("client_order_id", sa.String(length=255), nullable=False))
op.add_column("paper_option_executions", sa.Column("broker_order_id", sa.String(length=128), nullable=True))
op.add_column("option_strategy_legs", sa.Column("contract_symbol", sa.String(length=32), nullable=False))
```

- [ ] **Step 5: Re-run the focused persistence tests**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_option_repository.py -k "option and (contract or broker or client)" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/options/strategy.py src/db/models/trading.py src/trading/repositories/sqlalchemy.py \
  src/trading/repositories/in_memory.py alembic/versions/021_alpaca_option_execution_contract.py \
  tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_option_repository.py
git commit -m "feat: persist alpaca option execution contract"
```

### Task 2: Replace The Local Option Fill Simulator With An Alpaca-Backed `PaperOptionBroker`

**Files:**
- Modify: `src/trading/brokers/paper_option.py`
- Modify: `src/trading/brokers/paper_stock.py`
- Test: `tests/trading/test_paper_option_broker.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing broker tests**

```python
def test_paper_option_broker_submits_simple_long_call_to_alpaca(mock_option_client):
    broker = PaperOptionBroker(client=mock_option_client)
    order = broker.submit_order(build_long_call_request())
    assert mock_option_client.posts[0]["json"]["symbol"] == "AAPL250117C00190000"
    assert mock_option_client.posts[0]["json"]["position_intent"] == "buy_to_open"
    assert order.broker_order_id == "alpaca-order-1"


def test_paper_option_broker_submits_mleg_credit_spread(mock_option_client):
    broker = PaperOptionBroker(client=mock_option_client)
    order = broker.submit_order(build_credit_spread_request())
    payload = mock_option_client.posts[0]["json"]
    assert payload["order_class"] == "mleg"
    assert payload["legs"][0]["position_intent"] == "buy_to_open"
    assert payload["legs"][1]["position_intent"] == "sell_to_open"
```

- [ ] **Step 2: Run the focused broker tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_option_broker.py tests/trading/test_paper_stock_broker.py -k "alpaca and option" -q`

Expected: FAIL because `PaperOptionBroker` still immediately self-fills locally and does not submit or poll Alpaca orders.

- [ ] **Step 3: Implement the Alpaca-backed broker behavior**

```python
response = self._client.post(
    f"{self.trading_base_url}/v2/orders",
    json=payload,
    headers=self._auth_headers(),
)
latest_payload = self._poll_until_terminal(client_order_id=client_order_id, initial_payload=response.json())
```

```python
if request.order_class == "mleg":
    payload["legs"] = [leg.to_alpaca_payload() for leg in request.legs]
else:
    payload["symbol"] = request.contract_symbol
    payload["position_intent"] = request.position_intent
```

- [ ] **Step 4: Preserve the local-simulation helper only for tests/offline paths**

```python
class LocalPaperOptionBroker:
    def submit_order(...):
        ...
```

- [ ] **Step 5: Re-run the focused broker tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_option_broker.py tests/trading/test_paper_stock_broker.py -k "alpaca and option" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/brokers/paper_option.py src/trading/brokers/paper_stock.py \
  tests/trading/test_paper_option_broker.py tests/trading/test_paper_stock_broker.py
git commit -m "feat: back paper option broker with alpaca"
```

### Task 3: Build Broker-Native Open/Close/Roll/Adjust Payloads In `PaperExecutionWorkflow`

**Files:**
- Modify: `src/trading/workflows/paper_execution.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing workflow tests**

```python
def test_workflow_submits_mleg_open_order_for_credit_spread(repository, mock_option_broker):
    workflow = build_workflow(repository=repository, option_broker=mock_option_broker)
    result = workflow.run(...)
    assert result.paper_option_orders[0].order_class == "mleg"


def test_roll_option_strategy_builds_close_and_open_legs_from_existing_position(repository, mock_option_broker):
    seed_open_option_position_with_leg_refs(repository)
    workflow = build_workflow(repository=repository, option_broker=mock_option_broker)
    workflow.run(...)
    payload = mock_option_broker.submitted_payloads[-1]
    assert payload["legs"][0]["position_intent"].endswith("_to_close")
    assert payload["legs"][-1]["position_intent"].endswith("_to_open")
```

- [ ] **Step 2: Run the focused workflow tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -k "option and (roll or mleg or close)" -q`

Expected: FAIL because the workflow still assumes local immediate fills and does not carry enough broker-native leg refs to submit close/roll/adjust orders.

- [ ] **Step 3: Serialize and persist broker-leg refs on open positions**

```python
metadata_json = {
    **dict(option_decision.metadata_json),
    "broker_leg_refs": [leg_ref.to_dict() for leg_ref in order_request.legs],
    "opening_broker_order_id": order.broker_order_id,
}
```

- [ ] **Step 4: Build lifecycle orders from persisted position refs plus replacement decision legs**

```python
if action == "roll_option_strategy":
    order_request = build_roll_mleg_request(
        existing_leg_refs=existing_position.metadata_json["broker_leg_refs"],
        replacement_legs=option_decision.metadata_json["legs"],
    )
```

- [ ] **Step 5: Re-run the focused workflow tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -k "option and (roll or mleg or close)" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/workflows/paper_execution.py src/trading/repositories/sqlalchemy.py \
  src/trading/runtime/intraday_refresh_helpers.py tests/trading/test_paper_stock_broker.py \
  tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py
git commit -m "feat: execute broker-native option lifecycle orders"
```

### Task 4: Make Portfolio Sync Broker-Native For Options And Reconcile Local Strategy Positions

**Files:**
- Modify: `src/trading/portfolio/state.py`
- Modify: `src/trading/workflows/portfolio_sync.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_portfolio.py`
- Test: `tests/trading/test_portfolio_sync.py`

- [ ] **Step 1: Write the failing portfolio-sync tests**

```python
def test_build_positions_from_broker_filters_option_contract_rows():
    positions = build_positions_from_broker(
        broker_positions=[
            {"symbol": "AAPL", ...},
            {"symbol": "AAPL250117C00190000", ...},
        ],
        as_of=NOW,
    )
    assert [position.ticker for position in positions] == ["AAPL"]


def test_portfolio_sync_uses_broker_option_positions_without_local_overlay(repository, broker):
    result = BrokerPortfolioSyncWorkflow(repository=repository, broker=broker).run(as_of=NOW)
    assert result.snapshot.metadata_json["option_overlay_source"] != "local_simulation"
```

- [ ] **Step 2: Run the focused portfolio tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio.py tests/trading/test_portfolio_sync.py -k "option and broker" -q`

Expected: FAIL because the live sync path still overlays local option positions and maps all broker `/positions` rows through the stock-position builder.

- [ ] **Step 3: Split stock vs option broker positions and stop the live double-count**

```python
stock_payloads = [row for row in broker_positions if not is_option_position_payload(row)]
option_payloads = [row for row in broker_positions if is_option_position_payload(row)]
```

```python
snapshot = build_portfolio_snapshot_from_account(account_payload, as_of=as_of)
option_positions = build_option_positions_from_broker(option_payloads, local_strategy_metadata=...)
```

- [ ] **Step 4: Reconcile vanished broker option positions back into local strategy rows**

```python
if position.paper_option_position_id not in matched_broker_position_ids:
    repository.mark_paper_option_position_closed(...)
```

- [ ] **Step 5: Re-run the focused portfolio tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio.py tests/trading/test_portfolio_sync.py -k "option and broker" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/portfolio/state.py src/trading/workflows/portfolio_sync.py \
  src/trading/repositories/sqlalchemy.py tests/trading/test_portfolio.py tests/trading/test_portfolio_sync.py
git commit -m "feat: sync broker-backed option portfolio state"
```

### Task 5: Wire Live Runtimes, Add Standalone Smoke Coverage, And Update Operator Docs

**Files:**
- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `scripts/run_trading_live_preopen_order_smoke.py`
- Create: `scripts/run_trading_option_paper_execution.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/repo_overview.md`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/scripts/test_run_trading_live_preopen_order_smoke.py`
- Test: `tests/test_run_trading_option_paper_execution.py`

- [ ] **Step 1: Write the failing runtime and smoke tests**

```python
def test_live_preopen_dependencies_use_alpaca_backed_option_broker(monkeypatch):
    dependencies = build_live_preopen_dependencies(session)
    assert dependencies.paper_execution_workflow.option_broker.__class__.__name__ == "PaperOptionBroker"


def test_run_trading_option_paper_execution_outputs_broker_ids(monkeypatch):
    result = run_execution(...)
    assert result["order"]["broker_order_id"] == "alpaca-order-1"
```

- [ ] **Step 2: Run the focused runtime and smoke tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/scripts/test_run_trading_live_preopen_order_smoke.py tests/test_run_trading_option_paper_execution.py -k "option and broker" -q`

Expected: FAIL because there is no standalone Alpaca option smoke entry point and the runtime/smoke surfaces still assume the old local option fill behavior.

- [ ] **Step 3: Wire the new broker into live runtime builders**

```python
option_broker = PaperOptionBroker()
paper_execution_workflow = PaperExecutionWorkflow(..., option_broker=option_broker, ...)
```

- [ ] **Step 4: Add the standalone Alpaca option smoke script and update runbook docs**

```python
result = broker.submit_option_order_for_smoke(
    contract_symbol=args.contract_symbol,
    strategy_type=args.strategy_type,
    order_class=args.order_class,
)
```

Runbook must document:
- required env vars
- paper-account options enablement assumptions
- how to verify `client_order_id`, `broker_order_id`, `paper_option_orders`, and `paper_option_executions`
- that paper option event activities may reconcile after order/position state changes

- [ ] **Step 5: Re-run the focused runtime and smoke tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/scripts/test_run_trading_live_preopen_order_smoke.py tests/test_run_trading_option_paper_execution.py -k "option and broker" -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/runtime/preopen_dependencies.py src/trading/runtime/intraday_refresh_dependencies.py \
  scripts/run_trading_live_preopen_order_smoke.py scripts/run_trading_option_paper_execution.py \
  documents/research_app/runbook.md documents/repo_overview.md tests/trading/test_runtime_live.py \
  tests/scripts/test_run_trading_live_preopen_order_smoke.py tests/test_run_trading_option_paper_execution.py
git commit -m "feat: wire alpaca-backed option execution into live runtimes"
```

### Task 6: Run Migrations, Verify End-To-End, And Update The Progress Tracker

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run the targeted verification suite**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_option_repository.py tests/trading/test_paper_option_broker.py tests/trading/test_paper_stock_broker.py tests/trading/test_portfolio.py tests/trading/test_portfolio_sync.py tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_live.py tests/trading/test_runtime_intraday_live.py tests/scripts/test_run_trading_live_preopen_order_smoke.py tests/test_run_trading_option_paper_execution.py -q`

Expected: PASS

- [ ] **Step 2: Run the DB migration verification**

Run: `source ~/.venv/bin/activate && alembic upgrade head`

Expected: PASS

- [ ] **Step 3: Run the standalone opt-in option smoke against Alpaca paper**

Run: `source ~/.venv/bin/activate && python scripts/run_trading_option_paper_execution.py --contract-symbol AAPL250117C00190000 --strategy-type long_call --json`

Expected: PASS with non-empty `client_order_id`, `broker_order_id`, and persisted local mirror rows.

- [ ] **Step 4: Run the live preopen option-path smoke**

Run: `source ~/.venv/bin/activate && python scripts/run_trading_live_preopen_order_smoke.py --ticker QQQ --instrument option --json`

Expected: PASS with `runtime.execution.option_orders_submitted >= 1` and persisted `paper_option_orders` / `paper_option_executions` linked to broker IDs.

- [ ] **Step 5: Record implementation progress**

```markdown
- 2026-06-14: Completed Task N of the Alpaca-backed option paper execution plan. ...
```

- [ ] **Step 6: Commit**

```bash
git add plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "docs: record alpaca option execution verification"
```
