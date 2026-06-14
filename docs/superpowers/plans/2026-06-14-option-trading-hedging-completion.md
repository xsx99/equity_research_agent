# Option Trading And Hedging Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps so tactical option trades and `risk_hedge_overlay` hedges behave like first-class paths across preopen, execution, unified margin-account state, intraday refresh, reflection, smoke coverage, and operational audit.

**Architecture:** Keep the existing `TradingDecisionPipeline -> PositionSizer -> RiskManager -> PaperExecutionWorkflow` ownership chain. Do not redesign the option layer; finish the missing lifecycle, risk, account-state, and runtime seams around the current whitelisted option strategies and ETF hedge overlay flow. Preserve the current stock path and existing option smoke tests while tightening option-specific contracts.

**Tech Stack:** Python, pytest, dataclasses, SQLAlchemy ORM, Alembic, existing trading runtime workflows, paper option broker, existing option strategy/risk modules.

---

## Current State Summary

- Already implemented:
  - expression-bucket-driven option plan generation
  - whitelisted paper option open path
  - basic option strategy records, legs, orders, executions, positions, and risk snapshots
  - preopen option request building
  - preopen assignment-risk gate via `OptionRiskManager`
  - lookahead hedge overlay generation and paper option execution
  - option-aware quantity sizing and hedge protected-exposure basis auditing
- Still incomplete:
  - lifecycle actions are mostly modeled, but not fully stateful
  - unified account snapshots do not yet treat option overlays as a real account-state component
  - `OptionRiskManager` is still too shallow versus the D06 design
  - assignment-targeted hedge paths are not implemented
  - intraday option state refresh / rebalance is not end-to-end
  - reflection, dashboard, and smoke coverage for option-specific behaviors are still partial

## File Map

- `src/trading/workflows/paper_execution.py`
  - Main option execution orchestration; currently strongest source of lifecycle gaps.
- `src/trading/brokers/paper_option.py`
  - Paper option order/execution simulator; currently action-aware but not position-lifecycle-aware.
- `src/trading/options/strategy.py`
  - Option plan contract and strategy-level fields.
- `src/trading/risk/options.py`
  - Option risk manager; currently assignment-ratio-based and missing richer factor/event checks.
- `src/trading/runtime/preopen_risk.py`
  - Morning option request assembly and preopen assignment gate.
- `src/trading/runtime/lookahead_risk.py`
  - Residual hedge overlay materialization and protected exposure basis selection.
- `src/trading/workflows/portfolio_sync.py`
  - Unified stock account + local option overlay merge point.
- `src/trading/portfolio/state.py`
  - Portfolio snapshot and context constructors; currently under-models option overlays.
- `src/trading/intraday/rebalance.py`
  - Intraday action gating; should become option-lifecycle-aware.
- `src/trading/runtime/intraday_refresh_runner.py`
  - Intraday orchestration; needs option exposure refresh input, not just stock/news paths.
- `src/trading/repositories/in_memory.py`
  - Fast test repository support for new option state transitions.
- `src/trading/repositories/sqlalchemy.py`
  - Persistence and read-model surface for option lifecycle, hedge overlays, and richer audit fields.
- `tests/trading/test_paper_stock_broker.py`
  - Existing paper execution tests, including option execution and hedge overlay coverage.
- `tests/trading/test_option_risk.py`
  - Focused option risk tests; should expand materially.
- `tests/trading/test_runtime_live.py`
  - Preopen/live orchestration regression suite.
- `tests/trading/test_intraday_rebalance.py`
  - Intraday rebalance behavior.
- `tests/trading/test_runtime_intraday_live.py`
  - Live intraday orchestration tests.
- `tests/trading/test_option_repository.py`
  - Repository expectations for option strategy/order/position persistence.
- `documents/research_app/runbook.md`
  - Operator-facing smoke and runtime notes.
- `documents/repo_overview.md`
  - Major refactor summary after substantial completion.

## Scope Notes

- Keep the current whitelist unchanged:
  - `long_call`
  - `long_put`
  - `put_credit_spread`
  - `call_credit_spread`
  - `long_straddle`
  - `long_strangle`
- Keep option execution paper-only.
- Do not add real broker option integration in this slice.
- Do not redesign the entire risk model before closing obvious lifecycle/account-state gaps.
- Treat `risk_hedge_overlay` as a separate portfolio pool from tactical option trades in every new persistence or reporting path.

### Task 1: Finish Stateful Option Lifecycle Actions

**Files:**
- Modify: `src/trading/workflows/paper_execution.py`
- Modify: `src/trading/brokers/paper_option.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_option_repository.py`

- [ ] **Step 1: Write the failing lifecycle tests**

```python
def test_paper_execution_workflow_closes_existing_option_position():
    ...


def test_paper_execution_workflow_rolls_option_strategy_by_closing_then_opening():
    ...


def test_paper_execution_workflow_adjusts_existing_option_strategy_in_place():
    ...


def test_paper_execution_workflow_persists_avoid_event_option_without_filled_order():
    ...
```

- [ ] **Step 2: Run the focused lifecycle tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_option_repository.py -k "option and (close or roll or adjust or avoid_event)" -q`
Expected: FAIL because the current option path mostly behaves like an `open_option_strategy` executor with no real position lifecycle semantics.

- [ ] **Step 3: Implement minimal stateful lifecycle behavior**

```python
if trading_decision.decision == "close_option_strategy":
    _close_matching_option_position(...)
elif trading_decision.decision == "roll_option_strategy":
    _close_matching_option_position(...)
    _open_replacement_option_position(...)
elif trading_decision.decision == "adjust_option_strategy":
    _resize_or_replace_option_position(...)
elif trading_decision.decision == "avoid_event_option":
    _persist_non_fill_option_block(...)
```

- [ ] **Step 4: Persist option position status transitions and supersession links**

```python
metadata_json = {
    "supersedes_option_position_id": old_id,
    "lifecycle_action": "roll_option_strategy",
}
```

- [ ] **Step 5: Re-run the focused lifecycle tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_option_repository.py -k "option and (close or roll or adjust or avoid_event)" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/workflows/paper_execution.py src/trading/brokers/paper_option.py \
  src/trading/repositories/in_memory.py src/trading/repositories/sqlalchemy.py \
  tests/trading/test_paper_stock_broker.py tests/trading/test_option_repository.py
git commit -m "feat: complete option lifecycle execution actions"
```

### Task 2: Make Option Overlays First-Class In The Unified Margin Account

**Files:**
- Modify: `src/trading/workflows/portfolio_sync.py`
- Modify: `src/trading/portfolio/state.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] **Step 1: Write the failing unified-account tests**

```python
def test_portfolio_sync_includes_open_option_positions_in_snapshot_margin_fields():
    ...


def test_portfolio_context_carries_option_overlay_buying_power_and_assignment_exposure():
    ...
```

- [ ] **Step 2: Run the focused account-state tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_runtime_live.py -k "option and (portfolio_sync or option_margin or assignment_exposure)" -q`
Expected: FAIL because `PortfolioSnapshot` currently leaves option overlay impact mostly at zero or broker-stock-only fields.

- [ ] **Step 3: Implement overlay-aware snapshot math**

```python
option_market_value = sum(position.buying_power_effect for position in option_positions)
option_margin_requirement = sum(position.margin_requirement for position in option_positions)
total_margin_requirement = stock_margin_requirement + option_margin_requirement
excess_liquidity = max(0.0, account_equity - max(maintenance_margin_requirement, total_margin_requirement))
```

- [ ] **Step 4: Keep broker-reported stock fields separate from local option overlay fields**

```python
metadata_json = {
    "stock_margin_requirement_source": "broker_reported",
    "option_overlay_source": "local_simulation",
}
```

- [ ] **Step 5: Re-run the focused account-state tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_runtime_live.py -k "option and (portfolio_sync or option_margin or assignment_exposure)" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/workflows/portfolio_sync.py src/trading/portfolio/state.py \
  src/trading/repositories/sqlalchemy.py tests/trading/test_paper_stock_broker.py \
  tests/trading/test_runtime_live.py
git commit -m "feat: merge option overlays into unified margin account"
```

### Task 3: Deepen Option Risk Beyond A Single Assignment Ratio

**Files:**
- Modify: `src/trading/risk/options.py`
- Modify: `src/trading/risk/manager.py`
- Modify: `src/trading/runtime/preopen_risk.py`
- Test: `tests/trading/test_option_risk.py`
- Test: `tests/trading/test_risk_manager.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] **Step 1: Write the failing richer-risk tests**

```python
def test_option_risk_manager_blocks_event_through_expiry_credit_spread_when_policy_forbids():
    ...


def test_option_risk_manager_blocks_assignment_when_sector_concentration_after_assignment_is_too_high():
    ...


def test_preopen_option_assignment_gate_persists_richer_reason_codes():
    ...
```

- [ ] **Step 2: Run the focused option-risk tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_option_risk.py tests/trading/test_risk_manager.py tests/trading/test_runtime_live.py -k "option and (assignment or expiry or concentration)" -q`
Expected: FAIL because `OptionRiskManager` currently only computes net Greeks plus a simple assignment-to-equity ratio.

- [ ] **Step 3: Extend `OptionRiskInput` and `OptionRiskAssessment` only where the runtime can actually supply data**

```python
@dataclass(frozen=True)
class OptionRiskInput:
    ...
    expression_bucket_id: str | None
    assignment_notional: float
    protected_exposure_basis: str | None
```

- [ ] **Step 4: Implement conservative but explicit gates**

```python
if option_risk.event_through_expiry and option_risk.option_strategy_type in {"put_credit_spread", "call_credit_spread"}:
    return _rejected("event_through_expiry_blocked")
if _assigned_sector_concentration(...) > config.max_sector_weight:
    return _rejected("assignment_sector_concentration_cap")
if _assigned_expression_bucket_exposure(...) > config.assignment_concentration_limit:
    return _rejected("assignment_expression_bucket_cap")
```

- [ ] **Step 5: Re-run the focused option-risk tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_option_risk.py tests/trading/test_risk_manager.py tests/trading/test_runtime_live.py -k "option and (assignment or expiry or concentration)" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/risk/options.py src/trading/risk/manager.py src/trading/runtime/preopen_risk.py \
  tests/trading/test_option_risk.py tests/trading/test_risk_manager.py tests/trading/test_runtime_live.py
git commit -m "feat: deepen option risk and assignment gates"
```

### Task 4: Complete Hedge Overlay Lifecycle And Assignment-Targeted Hedges

**Files:**
- Modify: `src/trading/runtime/lookahead_risk.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Modify: `src/trading/risk/hedges.py`
- Modify: `src/trading/risk/planner.py`
- Test: `tests/trading/test_lookahead_risk.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing hedge-lifecycle tests**

```python
def test_lookahead_helper_uses_assignment_exposure_when_target_exposure_type_is_assignment():
    ...


def test_generated_hedge_can_close_existing_overlay():
    ...


def test_generated_hedge_can_adjust_existing_overlay_without_duplicate_open():
    ...
```

- [ ] **Step 2: Run the focused hedge tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_lookahead_risk.py tests/trading/test_intraday_rebalance.py tests/trading/test_paper_stock_broker.py -k "hedge and (assignment or close or adjust)" -q`
Expected: FAIL because hedge overlays currently skew toward `open_hedge -> long_put` and do not fully close the assignment-targeted loop.

- [ ] **Step 3: Implement assignment-targeted hedge basis selection**

```python
if hedge_action.target_exposure_type == "assignment":
    protected_basis = "approved_assignment_notional"
    protected_notional = ...
```

- [ ] **Step 4: Implement close/adjust overlay behavior using persisted open hedge positions**

```python
if hedge_action.action == "close_hedge":
    return _close_matching_overlay(...)
if hedge_action.action == "adjust_hedge":
    return _replace_or_resize_matching_overlay(...)
```

- [ ] **Step 5: Preserve overlay attribution separation**

```python
assert trading_decision.trade_identity == "risk_hedge_overlay"
assert strategy_id == "risk_manager_hedge_overlay_v1"
```

- [ ] **Step 6: Re-run the focused hedge tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_lookahead_risk.py tests/trading/test_intraday_rebalance.py tests/trading/test_paper_stock_broker.py -k "hedge and (assignment or close or adjust)" -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/trading/runtime/lookahead_risk.py src/trading/workflows/paper_execution.py \
  src/trading/risk/hedges.py src/trading/risk/planner.py \
  tests/trading/test_lookahead_risk.py tests/trading/test_intraday_rebalance.py \
  tests/trading/test_paper_stock_broker.py
git commit -m "feat: complete option hedge overlay lifecycle"
```

### Task 5: Finish Intraday Option Refresh And Rebalance

**Files:**
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/intraday/rebalance.py`
- Modify: `src/trading/runtime/lookahead_risk.py`
- Test: `tests/trading/test_runtime_intraday_live.py`
- Test: `tests/trading/test_intraday_rebalance.py`

- [ ] **Step 1: Write the failing intraday option tests**

```python
def test_intraday_runtime_refreshes_open_option_position_marks_and_greeks():
    ...


def test_intraday_rebalance_can_emit_roll_option_strategy_for_event_risk():
    ...


def test_intraday_rebalance_blocks_option_add_when_option_data_is_stale():
    ...
```

- [ ] **Step 2: Run the focused intraday option tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py -k "option and (intraday or roll or stale)" -q`
Expected: FAIL because intraday option refresh is not yet a true first-class consumer of open option overlays and option lifecycle actions.

- [ ] **Step 3: Refresh open option overlays as part of intraday scope**

```python
scope = open_stock_positions + open_option_positions + same_day_trades + top_candidates
```

- [ ] **Step 4: Add option-specific intraday gates**

```python
if option_data_is_stale:
    return _blocked("stale_option_data")
if event_through_expiry and action in {"open_option_strategy", "roll_option_strategy"}:
    return _blocked("event_risk_blocked")
```

- [ ] **Step 5: Re-run the focused intraday option tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py tests/trading/test_intraday_rebalance.py -k "option and (intraday or roll or stale)" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/runtime/intraday_refresh_runner.py src/trading/intraday/rebalance.py \
  src/trading/runtime/lookahead_risk.py tests/trading/test_runtime_intraday_live.py \
  tests/trading/test_intraday_rebalance.py
git commit -m "feat: finish intraday option refresh and rebalance"
```

### Task 6: Close Reflection, Smoke, And Operator Audit Gaps

**Files:**
- Modify: `src/trading/runtime/reflection.py`
- Modify: `src/trading/post_close/reflection.py`
- Modify: `scripts/run_trading_smoke_test.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/repo_overview.md`
- Test: `tests/trading/test_runtime_reflection_live.py`
- Test: `tests/trading/test_reflection_pipeline.py`
- Test: `tests/scripts/test_run_trading_smoke_test.py`

- [ ] **Step 1: Write the failing reflection and smoke tests**

```python
def test_reflection_input_includes_option_risk_snapshots_and_hedge_overlay_effectiveness():
    ...


def test_smoke_mode_covers_option_open_then_assignment_rejection_then_hedge_overlay():
    ...
```

- [ ] **Step 2: Run the focused reflection/smoke tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_reflection_live.py tests/trading/test_reflection_pipeline.py tests/scripts/test_run_trading_smoke_test.py -k option -q`
Expected: FAIL because reflection and smoke coverage still only partially represent option-specific lifecycle and hedge outcomes.

- [ ] **Step 3: Expand reflection payloads and smoke scenarios**

```python
payload["paper_option_decisions"] = ...
payload["option_risk_snapshots"] = ...
payload["risk_hedge_overlays"] = ...
payload["hedge_effectiveness"] = ...
```

- [ ] **Step 4: Document the final operator surface**

```markdown
- preopen option smoke
- intraday option refresh smoke
- hedge overlay inspection path
- assignment-risk rejection inspection path
```

- [ ] **Step 5: Re-run the focused reflection/smoke tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_reflection_live.py tests/trading/test_reflection_pipeline.py tests/scripts/test_run_trading_smoke_test.py -k option -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/runtime/reflection.py src/trading/post_close/reflection.py \
  scripts/run_trading_smoke_test.py documents/research_app/runbook.md documents/repo_overview.md \
  tests/trading/test_runtime_reflection_live.py tests/trading/test_reflection_pipeline.py \
  tests/scripts/test_run_trading_smoke_test.py
git commit -m "feat: finish option reflection and smoke coverage"
```

## Recommended Execution Order

1. Task 1
   Reason: without real lifecycle semantics, the rest of the option path remains misleading.
2. Task 2
   Reason: unified account state is the main missing substrate for believable option sizing/risk.
3. Task 3
   Reason: richer option risk is only worthwhile once lifecycle and account-state inputs are trustworthy.
4. Task 4
   Reason: hedge overlays should be upgraded after the underlying option exposure model is stable.
5. Task 5
   Reason: intraday should consume the completed preopen + execution contracts, not invent a second option model.
6. Task 6
   Reason: reflection/smoke/docs should validate the fully assembled behavior, not an interim contract.

## Exit Criteria

- Tactical option trades support open, close, roll, adjust, and avoid-event behaviors with persisted state transitions.
- Open option overlays affect unified margin-account snapshots and `PortfolioContext`.
- Preopen and execution-time option risk gates both enforce richer assignment/event/concentration rules.
- Hedge overlays can open, adjust, and close with explicit exposure-basis audit fields.
- Intraday refresh can evaluate open option overlays and emit option lifecycle actions safely.
- Reflection and smoke tests cover option decisions, option risk rejections, and hedge overlay effectiveness.
