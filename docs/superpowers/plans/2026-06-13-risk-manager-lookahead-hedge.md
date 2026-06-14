# Risk Manager Lookahead Hedge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic `1-5` trading day lookahead risk planning so the trading runtime can reduce or block risky exposure, generate ETF option hedge overlays, and keep final alpha trade sizing under `RiskManager` control.

**Architecture:** Keep the current `TradingPipeline -> PositionSizer -> RiskManager -> PaperExecutionWorkflow` ownership chain, but insert a pure `PortfolioHedgePlanner` that produces portfolio-level risk intent before final risk approval. Persist planner artifacts for audit, extend `RiskManager` to consume planner intent and emit `generated_hedge_action`, then wire pre-open and intraday runtimes to materialize hedge overlay decisions from residual post-approval exposure.

**Tech Stack:** Python, pytest, dataclasses, SQLAlchemy ORM, Alembic, existing trading runtime workflows, web `/today` read models.

---

## File Map

- `src/trading/risk/lookahead.py`
  - New pure contracts for lookahead macro state, event assessments, planner position actions, hedge actions, and persisted risk intents.
- `src/trading/risk/planner.py`
  - New deterministic `PortfolioHedgePlanner` rule engine.
- `src/trading/risk/manager.py`
  - Final trade approval, planner-intent application, residual hedge payload generation.
- `src/trading/risk/context.py`
  - Existing trade-risk and sizing contracts; extend only where final evaluation needs new lookahead fields.
- `src/trading/runtime/lookahead_risk.py`
  - New runtime helper that builds lookahead event assessments and hedge-decision materialization inputs from portfolio state, signal snapshots, and alert/news context.
- `src/trading/runtime/preopen_risk.py`
  - Pre-open orchestration: size trades, build planner input, persist planner intent, run final approvals, then materialize hedge overlay decisions from residual approved exposure.
- `src/trading/runtime/preopen_dependencies.py`
  - Wire planner and any lookahead-input loader helpers into live pre-open dependencies.
- `src/trading/intraday/rebalance.py`
  - Extend rebalance execution to accept planner-driven forced reductions and hedge lifecycle changes.
- `src/trading/runtime/intraday_refresh_runner.py`
  - Reuse lookahead planner after intraday refresh for hedge `open/adjust/close` and forced tactical reductions.
- `src/trading/runtime/intraday_refresh_dependencies.py`
  - Wire planner and runtime helpers into live intraday dependencies.
- `src/trading/workflows/paper_execution.py`
  - Execute approved hedge overlay trading decisions through the existing option paper path and preserve risk-decision alignment.
- `src/db/models/trading.py`
  - Persist new lookahead planner artifacts.
- `src/trading/repositories/in_memory.py`
  - Test repository support for lookahead intent and event-risk persistence.
- `src/trading/repositories/sqlalchemy.py`
  - ORM persistence/loaders for lookahead planner artifacts and richer risk payloads.
- `alembic/versions/019_risk_manager_lookahead_hedge.py`
  - Schema changes for planner persistence.
- `src/web/routers/today.py`
  - Show planner-derived risk intent, hedge overlay rationale, and risk-normalization state.
- `src/web/presenters/today_copy.py`
  - Human-readable labels for new risk statuses and hedge actions.
- `documents/repo_overview.md`
  - Major refactor summary.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Implementation status and verification evidence.

## Scope Notes

- This plan intentionally keeps the first hedge underlier/tool scope narrow:
  - broad ETF option hedges: `SPY`, `QQQ`, `IWM`
  - sector ETF option hedges: `XLK`, `XLF`, `XLE`, `SMH`
- This slice does not implement a full upstream macro pipeline. Instead, it adds planner contracts and runtime hooks that can consume:
  - existing own-event timing from signal snapshots
  - intraday alerts/news context
  - optional macro-state inputs when available
- `RiskManager` remains the only owner of final executable alpha size via `approved_weight`.

### Task 1: Lock The Lookahead Risk Contract And Persistence Boundary

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/module_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md`
- Modify: `plan/research_app/trading_agent_refactor/design/06_paper_trading_and_risk.md`
- Modify: `plan/research_app/trading_agent_refactor/design/08_data_model.md`
- Create: `src/trading/risk/lookahead.py`
- Modify: `src/trading/risk/__init__.py`
- Modify: `src/db/models/trading.py`
- Modify: `src/trading/repositories/in_memory.py`
- Modify: `src/trading/repositories/sqlalchemy.py`
- Create: `alembic/versions/019_risk_manager_lookahead_hedge.py`
- Test: `tests/db/test_trading_models.py`
- Test: `tests/trading/test_risk_context.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`

- [ ] **Step 1: Write the failing contract and schema tests**

```python
def test_portfolio_risk_intent_model_persists_position_and_hedge_actions():
    ...


def test_risk_context_exposes_lookahead_event_assessment_record():
    ...


def test_sqlalchemy_repository_round_trips_portfolio_risk_intent():
    ...
```

- [ ] **Step 2: Run the focused contract tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_risk_context.py tests/trading/test_sqlalchemy_repository.py -q`
Expected: FAIL because there is no persisted portfolio risk intent or lookahead contract layer yet.

- [ ] **Step 3: Update the canonical design/contract docs before runtime code**

```markdown
- `PortfolioHedgePlanner` emits `PortfolioRiskIntent`.
- `RiskManager` owns final `risk_hedge_overlay` generation.
- Hedge overlays materialize only after residual post-approval exposure is known.
```

- [ ] **Step 4: Add the new pure lookahead contracts**

```python
@dataclass(frozen=True)
class PortfolioEventRiskAssessmentRecord:
    ticker: str
    risk_source: str
    severity: str
    event_type: str | None
    days_until_event: int | None
    affects_existing_position: bool
    affects_pending_trade: bool
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioRiskIntentRecord:
    portfolio_risk_intent_id: str
    decision_time: datetime
    risk_window: str
    aggregate_risk_state: str
    position_actions: tuple[PositionRiskActionRecord, ...]
    hedge_actions: tuple[HedgeActionRecord, ...]
    binding_constraints: tuple[str, ...]
    metadata_json: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 5: Add minimal persistence for planner artifacts**

```python
class PortfolioRiskIntent(Base):
    portfolio_risk_intent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_risk_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"), nullable=True, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_window = Column(String(32), nullable=False)
    aggregate_risk_state = Column(String(32), nullable=False, index=True)
    position_actions_json = Column(JSONB, nullable=False, default=list)
    hedge_actions_json = Column(JSONB, nullable=False, default=list)
    binding_constraints_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
```

- [ ] **Step 6: Add the Alembic migration and repository methods**

Run: `source ~/.venv/bin/activate && alembic upgrade head --sql > /tmp/risk_manager_lookahead_hedge.sql`
Expected: SQL renders successfully with the new planner-intent table and no broken foreign keys.

- [ ] **Step 7: Re-run the focused contract tests**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_risk_context.py tests/trading/test_sqlalchemy_repository.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add plan/research_app/trading_agent_refactor/module_contracts.md \
  plan/research_app/trading_agent_refactor/design/05_workflows_and_decision_contracts.md \
  plan/research_app/trading_agent_refactor/design/06_paper_trading_and_risk.md \
  plan/research_app/trading_agent_refactor/design/08_data_model.md \
  src/trading/risk/lookahead.py src/trading/risk/__init__.py src/db/models/trading.py \
  src/trading/repositories/in_memory.py src/trading/repositories/sqlalchemy.py \
  alembic/versions/019_risk_manager_lookahead_hedge.py \
  tests/db/test_trading_models.py tests/trading/test_risk_context.py tests/trading/test_sqlalchemy_repository.py
git commit -m "feat: add lookahead risk planner contracts"
```

### Task 2: Implement The Pure Portfolio Hedge Planner

**Files:**
- Create: `src/trading/risk/planner.py`
- Modify: `src/trading/risk/__init__.py`
- Test: `tests/trading/test_portfolio_hedge_planner.py`

- [ ] **Step 1: Write the failing planner tests**

```python
def test_planner_opens_sector_hedge_for_cluster_risk_without_blocking_core_holding():
    ...


def test_planner_blocks_tactical_open_for_near_term_own_event():
    ...


def test_planner_applies_single_name_rules_before_macro_hedge_for_mixed_risk():
    ...
```

- [ ] **Step 2: Run the planner tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_hedge_planner.py -q`
Expected: FAIL because `PortfolioHedgePlanner` does not exist.

- [ ] **Step 3: Implement the deterministic planner**

```python
class PortfolioHedgePlanner:
    def plan(self, request: PortfolioHedgePlannerRequest) -> PortfolioRiskIntentRecord:
        if _has_single_name_binary_event(request):
            ...
        if _has_cluster_risk(request):
            ...
        if _has_macro_risk(request):
            ...
        return PortfolioRiskIntentRecord.create(...)
```

- [ ] **Step 4: Encode severity tiers and underlier mapping**

```python
def _coverage_ratio(severity: str) -> float:
    return {
        "watch": 0.25,
        "high": 0.50,
        "critical": 0.75,
    }[severity]


def _hedge_underlier_for_source(risk_source: str, sector: str | None) -> str:
    ...
```

- [ ] **Step 5: Re-run the planner tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_portfolio_hedge_planner.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/risk/planner.py src/trading/risk/__init__.py tests/trading/test_portfolio_hedge_planner.py
git commit -m "feat: add portfolio hedge planner"
```

### Task 3: Extend RiskManager To Consume Planner Intent And Emit Hedge Payloads

**Files:**
- Modify: `src/trading/risk/context.py`
- Modify: `src/trading/risk/manager.py`
- Test: `tests/trading/test_risk_manager.py`

- [ ] **Step 1: Write the failing final-approval tests**

```python
def test_risk_manager_blocks_tactical_trade_when_planner_marks_block_open():
    ...


def test_risk_manager_reduces_trade_to_planner_override_weight():
    ...


def test_risk_manager_attaches_generated_hedge_action_for_core_position_residual_macro_risk():
    ...
```

- [ ] **Step 2: Run the focused RiskManager tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_risk_manager.py -q`
Expected: FAIL because `RiskManager.evaluate()` does not accept planner intent or generate hedge payloads.

- [ ] **Step 3: Add the lookahead evaluation context**

```python
@dataclass(frozen=True)
class TradeIncrementalExposure:
    ticker: str
    trade_identity: str
    sector: str | None
    beta_bucket: str | None
    macro_sensitivity: str | None
    event_type: str | None
    event_date_distance: int | None
```

- [ ] **Step 4: Implement planner-intent application before final hard rails**

```python
if planner_action == "block_open":
    return self._decision(..., status="rejected", reason_code="lookahead_block_open", ...)
if max_allowed_weight_override is not None:
    approved_weight = min(approved_weight, max_allowed_weight_override)
```

- [ ] **Step 5: Generate structured hedge payloads only from residual risk**

```python
if residual_hedge_action is not None and status in {"approved", "reduced"}:
    generated_hedge_action = {
        "action": residual_hedge_action.action,
        "underlier": residual_hedge_action.target_underlier,
        "coverage_ratio": residual_hedge_action.coverage_ratio,
        "option_strategy_type": "long_put",
    }
```

- [ ] **Step 6: Re-run the focused RiskManager tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_risk_manager.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/trading/risk/context.py src/trading/risk/manager.py tests/trading/test_risk_manager.py
git commit -m "feat: apply lookahead risk intent in risk manager"
```

### Task 4: Wire Pre-Open Planning, Residual Hedge Materialization, And Paper Hedge Execution

**Files:**
- Create: `src/trading/runtime/lookahead_risk.py`
- Modify: `src/trading/runtime/preopen_risk.py`
- Modify: `src/trading/runtime/preopen_dependencies.py`
- Modify: `src/trading/workflows/paper_execution.py`
- Test: `tests/trading/test_runtime_live.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`

- [ ] **Step 1: Write the failing pre-open and hedge-execution tests**

```python
def test_live_risk_workflow_persists_portfolio_risk_intent_before_final_trade_approval():
    ...


def test_live_risk_workflow_materializes_hedge_overlay_from_residual_post_approval_exposure():
    ...


def test_paper_execution_workflow_executes_risk_hedge_overlay_option_trade():
    ...
```

- [ ] **Step 2: Run the focused runtime/execution tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py tests/trading/test_sqlalchemy_repository.py -q`
Expected: FAIL because pre-open risk orchestration has no planner stage and no residual hedge-decision materialization.

- [ ] **Step 3: Build runtime helpers that derive lookahead inputs from existing artifacts**

```python
def build_preopen_event_assessments(...):
    earnings_in_days = events_news.get("earnings_in_days")
    if earnings_in_days is not None and earnings_in_days <= 5:
        ...


def build_residual_hedge_trading_decisions(...):
    if action["action"] != "open_hedge":
        return ()
    return (TradingDecisionRecord(..., trade_identity="risk_hedge_overlay", instrument_type="option", ...),)
```

- [ ] **Step 4: Insert planner and residual-hedge stages into `_LiveRiskWorkflow.run()`**

```python
intent = planner.plan(...)
self.repository.save_portfolio_risk_intent(intent)
...
approved_decisions = _evaluate_all_candidates(...)
hedge_decisions = _materialize_residual_hedges(intent=intent, approved_decisions=approved_decisions, ...)
```

- [ ] **Step 5: Reuse the existing option paper path for hedge overlays**

```python
if trading_decision.trade_identity == "risk_hedge_overlay":
    ...
    self.repository.save_risk_hedge_decision(...)
```

- [ ] **Step 6: Re-run the focused runtime/execution tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py tests/trading/test_sqlalchemy_repository.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/trading/runtime/lookahead_risk.py src/trading/runtime/preopen_risk.py \
  src/trading/runtime/preopen_dependencies.py src/trading/workflows/paper_execution.py \
  tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py tests/trading/test_sqlalchemy_repository.py
git commit -m "feat: wire preopen lookahead hedge planning"
```

### Task 5: Reuse The Planner In Intraday Refresh And Hedge Lifecycle Management

**Files:**
- Modify: `src/trading/intraday/rebalance.py`
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/lookahead_risk.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing intraday planner tests**

```python
def test_intraday_refresh_expands_or_reduces_hedge_when_risk_severity_changes():
    ...


def test_intraday_rebalance_forces_tactical_reduce_before_broad_hedge_for_name_specific_binary_risk():
    ...
```

- [ ] **Step 2: Run the focused intraday tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
Expected: FAIL because intraday refresh does not rerun planner logic or hedge lifecycle changes.

- [ ] **Step 3: Extend intraday request building with lookahead signals**

```python
rebalance_request = _build_rebalance_request(...)
planner_inputs = build_intraday_lookahead_inputs(
    snapshot=snapshot,
    alerts=alerts,
    position=position,
)
```

- [ ] **Step 4: Apply planner results to forced reductions and hedge changes**

```python
if planner_position_action.action == "force_reduce":
    ...
if planner_hedge_action.action in {"adjust_hedge", "close_hedge"}:
    ...
```

- [ ] **Step 5: Re-run the focused intraday tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/trading/intraday/rebalance.py src/trading/runtime/intraday_refresh_dependencies.py \
  src/trading/runtime/intraday_refresh_runner.py src/trading/runtime/lookahead_risk.py \
  tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py
git commit -m "feat: reuse lookahead hedge planner intraday"
```

### Task 6: Surface Auditability In `/today`, Update Docs, And Verify End-To-End

**Files:**
- Modify: `src/web/routers/today.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `src/web/presenters/today_workspace.py`
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Test: `tests/web/test_today.py`
- Test: `tests/web/test_today_copy.py`
- Test: `tests/web/test_today_workspace.py`

- [ ] **Step 1: Write the failing UI/read-model tests**

```python
def test_today_dashboard_shows_lookahead_risk_source_and_hedge_overlay_reason():
    ...


def test_risk_status_label_humanizes_lookahead_reduce_and_block_states():
    ...
```

- [ ] **Step 2: Run the focused web tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_copy.py tests/web/test_today_workspace.py -q`
Expected: FAIL because the dashboard does not load planner intent or humanize new lookahead statuses.

- [ ] **Step 3: Surface the new risk audit fields**

```python
"risk_decision": {
    "status": row.risk_decision.status,
    "reason_code": row.risk_decision.reason_code,
    "generated_hedge_action": row.risk_decision.generated_hedge_action_json,
    "lookahead_risk_source": (row.risk_decision.metadata_json or {}).get("lookahead_risk_source"),
}
```

- [ ] **Step 4: Run the focused web tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_copy.py tests/web/test_today_workspace.py -q`
Expected: PASS

- [ ] **Step 5: Run the relevant verification suite**

Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/trading/test_risk_context.py tests/trading/test_portfolio_hedge_planner.py tests/trading/test_risk_manager.py tests/trading/test_runtime_live.py tests/trading/test_paper_stock_broker.py tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py tests/trading/test_sqlalchemy_repository.py tests/web/test_today.py tests/web/test_today_copy.py tests/web/test_today_workspace.py -q`
Expected: PASS

- [ ] **Step 6: Run the broader regression slices**

Run: `source ~/.venv/bin/activate && pytest tests/trading -q -k 'not sqlalchemy'`
Expected: PASS

Run: `source ~/.venv/bin/activate && pytest tests/web -q`
Expected: PASS

- [ ] **Step 7: Update repo overview and progress tracker**

Update `documents/repo_overview.md` with:

```markdown
- Added `PortfolioHedgePlanner` as a pure lookahead risk-planning layer ahead of final `RiskManager` approval.
- Pre-open and intraday risk flows now distinguish single-name event reduction from macro/sector hedge overlays.
```

Update `plan/research_app/trading_agent_refactor/progress_tracker.md` with:

- implementation date
- files changed
- verification commands and results
- known follow-ups or upstream macro-feed gaps

- [ ] **Step 8: Commit**

```bash
git add src/web/routers/today.py src/web/presenters/today_copy.py src/web/presenters/today_workspace.py \
  documents/repo_overview.md plan/research_app/trading_agent_refactor/progress_tracker.md \
  tests/web/test_today.py tests/web/test_today_copy.py tests/web/test_today_workspace.py
git commit -m "feat: expose lookahead hedge risk audit trail"
```

## Known Risks To Watch During Implementation

- Do not let planner-generated hedge intent create executable hedge orders before `RiskManager` resolves final alpha approvals.
- Keep hedge overlay option structures inside the current supported option capability set unless a separate design expands that whitelist.
- Avoid letting broad ETF hedges bypass tactical reductions that should happen for single-name binary event risk.
- Keep `PositionSizer` ownership intact. Planner can constrain, but it must not become a second sizing engine.
- Be careful with intraday forced reductions: they should reuse existing execution semantics instead of inventing a parallel order path.
