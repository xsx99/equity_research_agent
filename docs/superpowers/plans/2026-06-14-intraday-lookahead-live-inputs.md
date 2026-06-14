# Intraday Lookahead Live Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make intraday lookahead hedge decisions consume live macro severity and richer sector-cluster/readthrough inputs instead of only deriving deterministic own-event risk from flattened alert shapes.

**Architecture:** Keep the existing `PortfolioHedgePlanner` and `IntradayRebalancePipeline` intact. The change stays narrow: preserve richer intraday alert context through request assembly, add a live macro-state seam at runtime, and extend `LookaheadRiskWorkflowHelper` so it can derive `macro` and `sector_event_cluster` planner inputs from already-available runtime artifacts. This slice does not design a new macro ingestion pipeline or a new hedge optimizer.

**Tech Stack:** Python, pytest, dataclasses, existing intraday runtime helpers, existing deterministic risk/planner layer

---

## Scope Notes

- Reuse current `PortfolioHedgePlanner` behavior in [src/trading/risk/planner.py](/Users/shuxinxu/repos/equity_research_agent/src/trading/risk/planner.py) rather than changing hedge rules.
- Treat macro severity wiring as a narrow runtime seam: runtime loads `watch` / `high` / `critical` from an injected loader and passes it into the helper.
- Treat sector-cluster wiring as a deterministic transformation over data already present in `NewsAlertRecord` plus ticker sector metadata from baseline snapshots.
- Do not add a new DB model or a new upstream macro pipeline in this slice.

### Task 1: Preserve Rich Intraday Risk Payloads

**Files:**
- Modify: `src/trading/runtime/intraday_refresh_helpers.py`
- Modify: `src/trading/runtime/lookahead_risk.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing runtime test for rich alert payload propagation**

```python
def test_live_intraday_refresh_runtime_keeps_readthrough_and_theme_fields_on_rebalance_requests():
    runtime, _recorder, rebalance_pipeline, _repository = _build_runtime()
    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "theme_context_loader": lambda tickers, decision_time: {"NVDA": ("ai_semis",)},
        }
    )

    runtime.run()

    request = next(item for item in rebalance_pipeline.last_requests if item.ticker == "NVDA")
    assert request.metadata_json["sector"] == "Semiconductors"
    assert request.alerts[0]["affected_themes"] == ["ai_semis"]
    assert request.alerts[0]["readthrough_source_ticker"] == "AVGO"
```

- [ ] **Step 2: Run the runtime test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py::test_live_intraday_refresh_runtime_keeps_readthrough_and_theme_fields_on_rebalance_requests -q`
Expected: FAIL because `_build_alert_map()` currently drops `affected_themes` and `readthrough_source_ticker`, and `_build_rebalance_request()` does not carry sector metadata for the helper.

- [ ] **Step 3: Implement the minimal payload-preservation changes**

```python
def _build_alert_map(alerts: tuple[object, ...]) -> dict[str, list[dict[str, Any]]]:
    ...
    payload = {
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "sentiment": alert.sentiment,
        "headline": alert.headline,
        "summary": alert.summary,
        "source_ticker": getattr(alert, "source_ticker", None),
        "readthrough_source_ticker": getattr(alert, "readthrough_source_ticker", None),
        "affected_themes": list(getattr(alert, "affected_themes", ())),
    }

def _build_rebalance_request(...):
    metadata_json = {
        "sector": _sector_from_baseline(baseline),
    }
```

- [ ] **Step 4: Re-run the runtime test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py::test_live_intraday_refresh_runtime_keeps_readthrough_and_theme_fields_on_rebalance_requests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/trading/runtime/intraday_refresh_helpers.py src/trading/runtime/lookahead_risk.py \
  tests/trading/test_runtime_intraday_live.py
git commit -m "feat: preserve intraday lookahead alert context"
```

### Task 2: Add A Live Macro Severity Seam To Intraday Lookahead

**Files:**
- Modify: `src/trading/runtime/intraday_refresh_dependencies.py`
- Modify: `src/trading/runtime/intraday_refresh_runner.py`
- Modify: `src/trading/runtime/lookahead_risk.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing runtime test for macro severity wiring**

```python
def test_live_intraday_refresh_runtime_passes_macro_risk_state_into_intraday_lookahead_helper():
    runtime, _recorder, rebalance_pipeline, _repository = _build_runtime()
    runtime.dependencies = LiveIntradayRefreshDependencies(
        **{
            **runtime.dependencies.__dict__,
            "macro_state_loader": lambda decision_time: "high",
        }
    )

    runtime.run()

    assert rebalance_pipeline.last_portfolio_risk_intent.aggregate_risk_state == "macro_high_risk"
    assert rebalance_pipeline.last_portfolio_risk_intent.hedge_actions[0].risk_source == "macro"
```

- [ ] **Step 2: Run the runtime test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py::test_live_intraday_refresh_runtime_passes_macro_risk_state_into_intraday_lookahead_helper -q`
Expected: FAIL because the intraday dependency graph has no `macro_state_loader`, and `build_intraday_portfolio_risk_intent()` does not accept or forward `macro_risk_state`.

- [ ] **Step 3: Implement the minimal macro seam**

```python
@dataclass(frozen=True)
class LiveIntradayRefreshDependencies:
    ...
    macro_state_loader: Callable[[datetime], str | None]

macro_risk_state = self.dependencies.macro_state_loader(decision_time)
portfolio_risk_intent = self.dependencies.lookahead_helper.build_intraday_portfolio_risk_intent(
    ...,
    macro_risk_state=macro_risk_state,
)

def build_intraday_portfolio_risk_intent(..., macro_risk_state: str | None) -> PortfolioRiskIntentRecord:
    return self.hedge_planner.plan(
        PortfolioHedgePlannerRequest(
            ...,
            macro_risk_state=macro_risk_state,
        )
    )
```

- [ ] **Step 4: Re-run the runtime test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_intraday_live.py::test_live_intraday_refresh_runtime_passes_macro_risk_state_into_intraday_lookahead_helper -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/trading/runtime/intraday_refresh_dependencies.py src/trading/runtime/intraday_refresh_runner.py \
  src/trading/runtime/lookahead_risk.py tests/trading/test_runtime_intraday_live.py
git commit -m "feat: wire intraday macro lookahead state"
```

### Task 3: Derive Sector-Cluster Assessments From Readthrough Alerts

**Files:**
- Modify: `src/trading/runtime/lookahead_risk.py`
- Modify: `src/trading/intraday/rebalance.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write the failing tests for sector-cluster derivation**

```python
def test_intraday_helper_derives_sector_cluster_assessment_from_readthrough_alert():
    helper = LookaheadRiskWorkflowHelper()
    intent = helper.build_intraday_portfolio_risk_intent(
        rebalance_requests=(
            SimpleNamespace(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                existing_position=True,
                allow_open_new=False,
                alerts=(
                    {
                        "alert_type": "earnings_readthrough",
                        "severity": "high",
                        "source_ticker": "AVGO",
                        "readthrough_source_ticker": "AVGO",
                        "affected_themes": ["ai_semis"],
                    },
                ),
                metadata_json={"sector": "Semiconductors"},
            ),
        ),
        portfolio_context=_portfolio_context_with_semis_position(),
        config=_balanced_config(),
        decision_time=_now(),
        macro_risk_state=None,
    )

    assert intent.aggregate_risk_state == "event_cluster_risk"
    assert intent.hedge_actions[0].risk_source == "sector_event_cluster"
    assert intent.hedge_actions[0].target_underlier == "SMH"


def test_intraday_rebalance_attaches_sector_cluster_generated_hedge_payload():
    ...
    assert result.decisions[0].risk_decision_id is not None
    assert repository.risk_decisions[0].generated_hedge_action["risk_source"] == "sector_event_cluster"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
Expected: FAIL because `_intraday_event_assessment()` only emits `own_event`, and the helper never derives `sector_event_cluster` assessments from readthrough/theme fields.

- [ ] **Step 3: Implement deterministic cluster derivation**

```python
def _intraday_cluster_assessment(*, request: object, alert: dict[str, Any]) -> PortfolioEventRiskAssessmentRecord | None:
    severity = str(alert.get("severity") or "low").lower()
    if severity not in {"high", "critical"}:
        return None
    themes = tuple(alert.get("affected_themes") or ())
    readthrough_source = alert.get("readthrough_source_ticker") or alert.get("source_ticker")
    sector = dict(getattr(request, "metadata_json", {}) or {}).get("sector")
    if not themes and not readthrough_source:
        return None
    if not sector:
        return None
    return PortfolioEventRiskAssessmentRecord(
        ticker=str(getattr(request, "ticker", "")),
        risk_source="sector_event_cluster",
        severity=severity,
        event_type=str(alert.get("alert_type") or "readthrough"),
        days_until_event=0,
        affects_existing_position=bool(getattr(request, "existing_position", False)),
        affects_pending_trade=not bool(getattr(request, "existing_position", False)),
        metadata_json={
            "sector": sector,
            "affected_themes": list(themes),
            "readthrough_source_ticker": readthrough_source,
        },
    )
```

- [ ] **Step 4: Re-run the focused intraday tests**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/trading/runtime/lookahead_risk.py src/trading/intraday/rebalance.py \
  tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py
git commit -m "feat: derive intraday sector cluster lookahead risk"
```

### Task 4: Document The New Intraday Input Boundary And Verify End-To-End

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Update the docs to describe the new intraday input contract**

```markdown
- Intraday lookahead now consumes:
  - actionable own-event alerts
  - live macro severity from an injected runtime loader
  - readthrough/theme context preserved from `NewsAlertRecord`
- Dedicated macro ingestion and broader cluster scoring remain follow-up work.
```

- [ ] **Step 2: Run the focused verification suite**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
Expected: PASS

- [ ] **Step 3: Run broader relevant verification**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py tests/trading/test_paper_stock_broker.py -q`
Expected: PASS

- [ ] **Step 4: Update the progress tracker with the implementation result and exact verification commands**

```markdown
- 2026-06-14: Completed the intraday live-input follow-up. Intraday lookahead now preserves sector/readthrough/theme context, accepts injected macro severity, and derives `sector_event_cluster` assessments for deterministic hedge adjustments. Verification passed with ...
```

- [ ] **Step 5: Commit**

```bash
git add documents/repo_overview.md plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "docs: record intraday lookahead live input wiring"
```

## Acceptance Criteria

- Intraday runtime no longer flattens away `affected_themes` or `readthrough_source_ticker` before lookahead planning.
- Intraday lookahead helper accepts `macro_risk_state` explicitly and passes it into `PortfolioHedgePlannerRequest`.
- High/critical readthrough alerts plus sector metadata can deterministically produce `sector_event_cluster` hedge intent.
- Intraday risk decisions can surface generated hedge payloads with `risk_source in {"macro", "sector_event_cluster"}` without changing the planner rule engine.
- Docs clearly state that this slice wires live inputs but does not yet introduce a dedicated macro ingestion pipeline or cluster optimizer.
