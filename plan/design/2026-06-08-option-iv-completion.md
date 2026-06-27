# Option IV Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate raw option-chain implied volatility from IV rank semantics, make option payload generation consume IV-aware chain selection, and add lightweight IV/policy fallback behavior for option expressions.

**Architecture:** Keep the existing strategy -> expression -> option payload flow, but tighten the option-chain contract so provider/source rows distinguish `implied_volatility` from optional `iv_rank`. Then teach option payload generation to prefer IV-aware contracts for volatility expressions, record degraded generation modes when IV is missing, and reject/fallback only where expression policy explicitly requires IV support.

**Tech Stack:** Python, pytest, dataclasses, existing provider/source ingestion contracts, trading decision workflow, options strategy layer

---

### Task 1: Fix Option-Chain IV Contract

**Files:**
- Modify: `src/providers/market_data/alpaca_provider.py`
- Modify: `src/trading/signals/source_ingestion.py`
- Modify: `src/trading/strategies/catalog.py`
- Test: `tests/tools/test_market_data.py`
- Test: `tests/trading/test_signal_sources.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fetch_option_chain_keeps_implied_volatility_separate_from_iv_rank():
    ...


def test_source_ingestion_service_persists_option_chain_iv_fields():
    ...
```

- [ ] **Step 2: Run the focused contract tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py tests/trading/test_signal_sources.py -q`
Expected: FAIL because the provider still maps Alpaca `impliedVolatility` into `iv_rank` and the ingested payload has no distinct raw IV field.

- [ ] **Step 3: Implement the minimal contract fix**

```python
return {
    "implied_volatility": _to_float_or_none(snapshot.get("impliedVolatility")),
    "iv_rank": _to_float_or_none(snapshot.get("ivRank")),
}
```

- [ ] **Step 4: Re-run the focused contract tests**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py tests/trading/test_signal_sources.py -q`
Expected: PASS

### Task 2: Make Option Payload Generation IV-Aware

**Files:**
- Modify: `src/trading/workflows/trading_decision.py`
- Test: `tests/trading/test_trading_decision_repository.py`

- [ ] **Step 1: Write the failing option-payload tests**

```python
def test_volatility_event_option_prefers_chain_contracts_with_implied_volatility_and_higher_vega():
    ...


def test_directional_option_records_degraded_iv_metadata_when_chain_iv_is_missing():
    ...
```

- [ ] **Step 2: Run the focused workflow tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py -q`
Expected: FAIL because chain selection still scores only expiry/strike/delta and payload metadata does not expose IV degradation state.

- [ ] **Step 3: Implement IV-aware chain scoring and metadata**

```python
score = (
    expiry_penalty
    + strike_penalty
    + delta_penalty
    + _iv_penalty(...)
    + _vega_penalty(...)
)
```

- [ ] **Step 4: Re-run the focused workflow tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py -q`
Expected: PASS

### Task 3: Add Lightweight IV Policy Rejection And Fallback

**Files:**
- Modify: `src/trading/workflows/trading_decision.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Test: `tests/trading/test_trading_decision_repository.py`
- Test: `tests/trading/test_paper_stock_broker.py`

- [ ] **Step 1: Write the failing fallback/policy tests**

```python
def test_volatility_event_option_is_rejected_when_chain_lacks_required_iv_support():
    ...


def test_option_execution_advances_to_same_strategy_fallback_after_iv_policy_rejection():
    ...
```

- [ ] **Step 2: Run the focused fallback tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py tests/trading/test_paper_stock_broker.py -q`
Expected: FAIL because volatility expressions do not enforce IV requirements and downstream fallback resolution cannot distinguish IV-policy rejection from other payload rejections.

- [ ] **Step 3: Implement minimal IV policy gates**

```python
if expression_requires_iv and not chain_supports_iv:
    return _reject_option_payload(
        reason="iv_data_required",
        ...
    )
```

- [ ] **Step 4: Re-run the focused fallback tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py tests/trading/test_paper_stock_broker.py -q`
Expected: PASS

### Task 4: Verify, Document, And Track Progress

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run the relevant verification suite**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py tests/trading/test_signal_sources.py tests/trading/test_trading_decision_repository.py tests/trading/test_paper_stock_broker.py -q`
Expected: PASS

- [ ] **Step 2: Run the broader trading regression**

Run: `source ~/.venv/bin/activate && pytest tests/trading -q -k 'not sqlalchemy'`
Expected: PASS

- [ ] **Step 3: Update repo overview and tracker with the IV-contract and option-fallback changes**
