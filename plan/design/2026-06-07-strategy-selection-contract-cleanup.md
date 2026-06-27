# Strategy Selection Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up PR03 strategy matching so only true trade-eligible candidates enter the trade pipeline, while retained watch outcomes persist through a separate watch path with no fake `long_stock` fallback.

**Architecture:** Keep `candidate_scores` as the raw scored layer, keep `trade_classifications` as the trade-path classification layer, and add an explicit `watch_candidates` persistence layer. Tighten actionability at the matcher boundary, split selector outputs into `selected_trades` and `watch_candidates`, and update repositories and read models to consume the new contract without manufacturing stock-trade semantics for no-trade rows.

**Tech Stack:** Python, pytest, SQLAlchemy, Alembic, dataclasses, existing trading workflows and web presenters.

---

### Task 1: Lock The New Contract And Schema Boundary

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/module_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/03_strategy_architecture.md`
- Modify: `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/017_strategy_selection_contract_cleanup.py`
- Test: `tests/db/test_trading_models.py`

- [ ] **Step 1: Write the failing schema tests**

```python
def test_candidate_score_persists_candidate_status():
    ...

def test_watch_candidate_model_persists_without_expression_bucket():
    ...
```

- [ ] **Step 2: Run the model tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py -q`
Expected: FAIL because `candidate_status` and `watch_candidates` are not modeled yet.

- [ ] **Step 3: Update canonical contract docs before touching runtime code**

```markdown
- StrategyPipeline now emits `selected_trades` and `watch_candidates`.
- TradeClassifier consumes selected trades only.
- watch candidates persist separately from trade classifications.
```

- [ ] **Step 4: Add the schema changes**

```python
class CandidateScore(Base):
    candidate_status = Column(String(32), nullable=False, index=True)


class WatchCandidate(Base):
    watch_candidate_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(UUID(as_uuid=True), ForeignKey("candidate_scores.candidate_score_id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_run_id = Column(UUID(as_uuid=True), ForeignKey("strategy_runs.strategy_run_id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    watch_strategy_id = Column(String(64), nullable=False, index=True)
    watch_strategy_version = Column(String(16), nullable=False)
    watch_type = Column(String(64), nullable=True, index=True)
    result_status = Column(String(64), nullable=False, index=True)
    watch_reason = Column(Text, nullable=False)
    selection_context_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
```

- [ ] **Step 5: Add the Alembic migration**

Run: `source ~/.venv/bin/activate && alembic upgrade head --sql > /tmp/strategy_selection_contract_cleanup.sql`
Expected: SQL renders successfully with the new column/table and no invalid constraint references.

- [ ] **Step 6: Re-run the model tests**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py -q`
Expected: PASS

### Task 2: Tighten Matcher Semantics

**Files:**
- Modify: `src/trading/strategies/catalog.py`
- Modify: `src/trading/strategies/matching.py`
- Modify: `src/trading/strategies/__init__.py`
- Test: `tests/trading/test_strategy_matching.py`

- [ ] **Step 1: Add failing matcher tests**

```python
def test_candidate_is_not_actionable_when_missing_required_signals():
    ...

def test_strategy_matcher_preserves_falsey_required_signal_values():
    ...

def test_strategy_matcher_uses_configured_default_action_and_direction():
    ...

def test_strategy_matcher_blocks_candidate_when_macro_regime_is_disallowed():
    ...
```

- [ ] **Step 2: Run the matcher tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py -q`
Expected: FAIL because the matcher still uses loose actionability, truthy fallback, and hard-coded `enter_long` / `bullish`.

- [ ] **Step 3: Extend strategy config with explicit selection policy**

```python
"selection_policy": {
    "actionable_score_threshold": 0.55,
    "default_candidate_action": "enter_long",
    "default_candidate_direction": "bullish",
    "eligible_expression_bucket_ids": ["long_stock"],
}
```

- [ ] **Step 4: Implement strict candidate status and actionability**

```python
candidate_status = _resolve_candidate_status(
    score=score,
    missing_required_signals=missing,
    action=action,
    rejection_reason=rejection_reason,
    macro_compatibility=macro_compatibility,
    actionable_score_threshold=threshold,
)
```

- [ ] **Step 5: Fix required-signal lookup to preserve falsey values**

```python
primary = flattened.get(signal_name)
fallback = flattened.get(str(signal_name).replace(".", "_"))
value = primary if primary is not None else fallback
```

- [ ] **Step 6: Re-run the matcher tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py -q`
Expected: PASS

### Task 3: Split Selector Output And Remove Expression Fallback

**Files:**
- Modify: `src/trading/strategies/selector.py`
- Modify: `src/trading/strategies/__init__.py`
- Test: `tests/trading/test_primary_strategy_selector.py`

- [ ] **Step 1: Add failing selector tests**

```python
def test_selector_returns_selected_trades_and_watch_candidates_separately():
    ...

def test_selector_does_not_assign_long_stock_to_watch_candidates():
    ...

def test_selector_requires_explicit_expression_bucket_mapping():
    ...
```

- [ ] **Step 2: Run the selector tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_primary_strategy_selector.py -q`
Expected: FAIL because the selector still returns one mixed `SelectedStrategyRecord` list and falls back to `long_stock`.

- [ ] **Step 3: Introduce explicit selector result objects**

```python
@dataclass(frozen=True)
class SelectedTradeRecord:
    ...


@dataclass(frozen=True)
class WatchCandidateRecord:
    ...


@dataclass(frozen=True)
class PrimarySelectionResult:
    selected_trades: tuple[SelectedTradeRecord, ...]
    watch_candidates: tuple[WatchCandidateRecord, ...]
```

- [ ] **Step 4: Replace implicit expression fallback with config-driven lookup**

```python
bucket_ids = candidate.selection_policy["eligible_expression_bucket_ids"]
expression = _choose_first_eligible_expression(bucket_ids, expressions)
if expression is None:
    return _watch_candidate_for_missing_expression(candidate)
```

- [ ] **Step 5: Re-run the selector tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_primary_strategy_selector.py -q`
Expected: PASS

### Task 4: Persist Watch Candidates And Narrow Trade Classification To Trade Path

**Files:**
- Modify: `src/trading/strategies/classifier.py`
- Modify: `src/trading/workflows/strategy_scoring.py`
- Modify: `src/trading/replay/historical.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Test: `tests/trading/test_trade_classifier.py`
- Test: `tests/trading/test_pipeline.py`
- Test: `tests/trading/test_historical_replay.py`
- Test: `tests/trading/test_candidate_repository.py`

- [ ] **Step 1: Add failing workflow and repository tests**

```python
def test_trade_classifier_rejects_watch_candidate_inputs():
    ...

def test_strategy_pipeline_persists_watch_candidates_separately():
    ...

def test_historical_replay_persists_watch_candidates():
    ...

def test_candidate_repository_round_trips_watch_candidates():
    ...
```

- [ ] **Step 2: Run the focused workflow tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trade_classifier.py tests/trading/test_pipeline.py tests/trading/test_historical_replay.py tests/trading/test_candidate_repository.py -q`
Expected: FAIL because the pipeline still mixes watch rows into trade classification and repositories have no watch-candidate persistence.

- [ ] **Step 3: Narrow `TradeClassifier` to trade-path inputs only**

```python
def classify(self, selected: SelectedTradeRecord) -> TradeClassificationRecord:
    if selected.candidate.candidate_status != "actionable":
        raise ValueError("trade_classifier_requires_actionable_selected_trade")
```

- [ ] **Step 4: Teach `StrategyPipeline` and replay to persist watch candidates**

```python
selection = self.selector.select(candidates, definitions)
classifications = tuple(self.classifier.classify_many(selection.selected_trades))
self.repository.save_watch_candidates(selection.watch_candidates)
```

- [ ] **Step 5: Update manual-request result recording**

```python
for watch in watch_candidates:
    manual_request_service.record_evaluation(..., result_status=watch.result_status, ...)
```

- [ ] **Step 6: Re-run the focused workflow tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trade_classifier.py tests/trading/test_pipeline.py tests/trading/test_historical_replay.py tests/trading/test_candidate_repository.py -q`
Expected: PASS

### Task 5: Remove Fake Trade Semantics From Repositories, Trading Decision Context, And UI

**Files:**
- Modify: `src/trading/workflows/trading_decision.py`
- Modify: `src/web/routers/today.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `tests/trading/test_trading_decision_repository.py`
- Modify: `tests/web/test_today.py`
- Modify: `tests/web/test_today_workspace.py`

- [ ] **Step 1: Add failing downstream compatibility tests**

```python
def test_trading_decision_context_does_not_fallback_watch_rows_to_long_stock():
    ...

def test_today_workspace_renders_watch_candidate_without_expression_bucket():
    ...

def test_today_candidate_summary_prefers_watch_candidate_status_over_trade_identity_fallback():
    ...
```

- [ ] **Step 2: Run the downstream tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py tests/web/test_today.py tests/web/test_today_workspace.py -q`
Expected: FAIL because repository and UI code still assume watch/no-trade rows may carry `long_stock` or `watch_only` trade classifications.

- [ ] **Step 3: Remove repository-level trade fallbacks for non-trade rows**

```python
expression_bucket_id = classification.expression_bucket_id if classification is not None else None
trade_identity = classification.trade_identity if classification is not None else None
instrument_type = "watch" if watch_candidate is not None else "stock"
```

- [ ] **Step 4: Render watch rows from explicit watch-candidate data**

```python
{
    "result_status": watch.result_status,
    "watch_type": watch.watch_type,
    "expression_bucket_id": None,
}
```

- [ ] **Step 5: Re-run the downstream tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py tests/web/test_today.py tests/web/test_today_workspace.py -q`
Expected: PASS

### Task 6: Broader Verification And Documentation

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Run focused PR03 verification**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py tests/trading/test_primary_strategy_selector.py tests/trading/test_trade_classifier.py tests/trading/test_pipeline.py tests/trading/test_historical_replay.py tests/trading/test_candidate_repository.py tests/trading/test_trading_decision_repository.py tests/db/test_trading_models.py tests/web/test_today.py tests/web/test_today_workspace.py -q`
Expected: PASS

- [ ] **Step 2: Run broader relevant trading verification**

Run: `source ~/.venv/bin/activate && pytest tests/trading -q`
Expected: PASS in the user's local environment.

- [ ] **Step 3: Run Alembic offline SQL generation**

Run: `source ~/.venv/bin/activate && alembic upgrade head --sql > /tmp/trading_head.sql`
Expected: PASS

- [ ] **Step 4: Run whitespace verification**

Run: `git diff --check`
Expected: PASS

- [ ] **Step 5: Update repo overview and progress tracker**

```markdown
- Added a dedicated watch-candidate persistence path so rejected or downgraded PR03 rows no longer impersonate selected trades.
```
