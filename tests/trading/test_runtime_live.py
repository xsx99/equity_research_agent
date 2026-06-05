from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig
from src.trading.data_sources.live_universe import LiveUniverseProvider
from src.trading.risk import RiskDecisionRecord
from src.trading.runtime.preopen_dependencies import _ConfiguredLiveUniverseScanPipeline
from src.trading.runtime.preopen_risk import _LiveRiskWorkflow
from src.trading.runtime.preopen import (
    LivePreopenDependencies,
    LivePreopenRuntime,
    run_live_preopen_once,
)
from src.trading.runtime.support import (
    build_execution_report,
    build_runtime_report,
    seed_initial_strategy_definitions,
)
from src.trading.strategies.catalog import get_initial_strategy_definitions
from src.trading.strategies.matching import StrategyDefinitionRecord


class _CallRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, name: str) -> None:
        self.calls.append(name)


class _UniverseFilterLoader:
    def __init__(self, recorder: _CallRecorder, config: object) -> None:
        self.recorder = recorder
        self.config = config

    def load_active(self) -> object:
        self.recorder.record("load_universe_filter")
        return self.config


class _ManualRequestLoader:
    def __init__(self, recorder: _CallRecorder, requests: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.requests = requests

    def load_active(self) -> tuple[object, ...]:
        self.recorder.record("load_manual_requests")
        return self.requests


class _UniverseScanPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, config: object, decision_time: datetime, manual_requests: tuple[object, ...]) -> object:
        assert config is not None
        assert decision_time.tzinfo is not None
        assert isinstance(manual_requests, tuple)
        self.recorder.record("universe_scan")
        return self.result


class _SignalPipeline:
    def __init__(self, recorder: _CallRecorder, snapshots: tuple[object, ...]) -> None:
        self.recorder = recorder
        self.snapshots = snapshots

    def build_pre_open_snapshots(self, *, universe_result: object, decision_time: datetime) -> tuple[object, ...]:
        assert universe_result is not None
        assert decision_time.tzinfo is not None
        self.recorder.record("signal_snapshot")
        return self.snapshots


class _StrategyPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, snapshots: tuple[object, ...], decision_time: datetime) -> object:
        assert snapshots
        assert decision_time.tzinfo is not None
        self.recorder.record("strategy_scoring")
        return self.result


class _PortfolioSyncWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(self, *, as_of: datetime) -> object:
        assert as_of.tzinfo is not None
        self.recorder.record("portfolio_sync")
        return self.result


class _RiskWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        assert candidates
        assert classifications
        assert portfolio_context is not None
        assert decision_time.tzinfo is not None
        self.recorder.record("risk")
        return self.result


class _TradingDecisionPipeline:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        decision_time: datetime,
    ) -> object:
        assert candidates
        assert classifications
        assert risk_decisions
        assert decision_time.tzinfo is not None
        self.recorder.record("trading_decision")
        return self.result


class _PaperExecutionWorkflow:
    def __init__(self, recorder: _CallRecorder, result: object) -> None:
        self.recorder = recorder
        self.result = result

    def run(
        self,
        *,
        trading_decisions: tuple[object, ...],
        risk_decisions: tuple[object, ...],
        trade_date: datetime,
    ) -> object:
        assert trading_decisions
        assert risk_decisions
        assert trade_date.tzinfo is not None
        self.recorder.record("paper_execution")
        return self.result


def _build_runtime(*, execute_paper_orders: bool) -> tuple[LivePreopenRuntime, _CallRecorder]:
    recorder = _CallRecorder()
    universe_result = SimpleNamespace(included_symbols=("AAPL", "MSFT"))
    strategy_result = SimpleNamespace(
        candidates=(SimpleNamespace(ticker="AAPL"),),
        classifications=(SimpleNamespace(ticker="AAPL"),),
    )
    portfolio_result = SimpleNamespace(portfolio_context=SimpleNamespace(account_equity=100000.0))
    risk_result = SimpleNamespace(risk_decisions=(SimpleNamespace(ticker="AAPL"),))
    decision_result = SimpleNamespace(decisions=(SimpleNamespace(ticker="AAPL", decision="enter_long"),))
    execution_result = SimpleNamespace(paper_orders=(SimpleNamespace(ticker="AAPL"),))
    dependencies = LivePreopenDependencies(
        universe_filter_loader=_UniverseFilterLoader(
            recorder,
            SimpleNamespace(profile_name="default"),
        ),
        manual_request_loader=_ManualRequestLoader(recorder, (SimpleNamespace(ticker="NVDA"),)),
        universe_scan_pipeline=_UniverseScanPipeline(recorder, universe_result),
        signal_pipeline=_SignalPipeline(recorder, (SimpleNamespace(ticker="AAPL"),)),
        strategy_pipeline=_StrategyPipeline(recorder, strategy_result),
        portfolio_sync_workflow=_PortfolioSyncWorkflow(recorder, portfolio_result),
        risk_workflow=_RiskWorkflow(recorder, risk_result),
        trading_decision_pipeline=_TradingDecisionPipeline(recorder, decision_result),
        paper_execution_workflow=_PaperExecutionWorkflow(recorder, execution_result),
    )
    runtime = LivePreopenRuntime(
        dependencies=dependencies,
        now=lambda: datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc),
        execute_paper_orders=execute_paper_orders,
    )
    return runtime, recorder


def test_live_preopen_runtime_runs_morning_chain_without_execution_by_default():
    runtime, recorder = _build_runtime(execute_paper_orders=False)

    result = runtime.run()

    assert recorder.calls == [
        "load_universe_filter",
        "load_manual_requests",
        "universe_scan",
        "signal_snapshot",
        "strategy_scoring",
        "portfolio_sync",
        "risk",
        "trading_decision",
    ]
    assert result["status"] == "passed"
    assert result["phase"] == "preopen"
    assert result["execution"]["mode"] == "dry_run"
    assert result["execution"]["orders_submitted"] == 0


def test_live_preopen_runtime_executes_paper_orders_only_when_enabled():
    runtime, recorder = _build_runtime(execute_paper_orders=True)

    result = runtime.run()

    assert recorder.calls[-1] == "paper_execution"
    assert result["execution"]["mode"] == "execute"
    assert result["execution"]["orders_submitted"] == 1


def test_run_live_preopen_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime_instance, _recorder = _build_runtime(execute_paper_orders=False)

    monkeypatch.setattr(
        "src.trading.runtime.preopen.build_live_preopen_dependencies",
        lambda _session: runtime_instance.dependencies,
    )

    result = run_live_preopen_once(now=lambda: datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["execution"]["mode"] == "dry_run"


def test_configured_live_universe_scan_pipeline_prefers_targeted_symbols_for_manual_scope():
    class _ScopedProvider:
        def fetch_universe_assets(self):
            raise AssertionError("full_universe_fetch_should_not_run")

        def fetch_assets_for_symbols(self, symbols):
            assert symbols == ("AAPL", "NVDA")
            return [
                UniverseAsset(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Consumer Electronics",
                    price=200.0,
                    avg_dollar_volume=100_000_000.0,
                ),
                UniverseAsset(
                    symbol="NVDA",
                    company_name="NVIDIA Corp.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Semiconductors",
                    price=120.0,
                    avg_dollar_volume=120_000_000.0,
                ),
            ]

    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    pipeline = _ConfiguredLiveUniverseScanPipeline(provider=_ScopedProvider())

    result = pipeline.run(
        config=UniverseFilterConfig(manual_include=("AAPL",)),
        decision_time=decision_time,
        manual_requests=(SimpleNamespace(ticker="NVDA"),),
    )

    assert result.included_symbols == ("AAPL", "NVDA")


def test_live_universe_provider_skips_symbols_that_fail_targeted_enrichment():
    class _MarketProvider:
        def fetch_daily_bars(self, ticker, lookback_days):
            del lookback_days
            if ticker == "BAD":
                raise RuntimeError("bad_symbol")
            return [
                {
                    "date": "2026-06-02",
                    "open": 198.0,
                    "high": 201.0,
                    "low": 197.0,
                    "close": 200.0,
                    "volume": 1_000_000,
                }
            ]

        def fetch_context(self, ticker):
            return {"company_name": f"{ticker} Inc.", "sector": "Technology"}

    provider = LiveUniverseProvider(market_provider=_MarketProvider())

    assets = provider.fetch_assets_for_symbols(("AAPL", "BAD"))

    assert [asset.symbol for asset in assets] == ["AAPL"]


def test_bootstrap_seed_strategy_definitions_populates_empty_repository_once():
    class _Repository:
        def __init__(self) -> None:
            self.rows: list[StrategyDefinitionRecord] = []

        def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
            return list(self.rows)

        def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
            self.rows.append(definition)

    repository = _Repository()

    seed_initial_strategy_definitions(repository)
    seed_initial_strategy_definitions(repository)

    expected_ids = {row["strategy_id"] for row in get_initial_strategy_definitions()}
    assert len(repository.rows) == len(expected_ids)
    assert {row.strategy_id for row in repository.rows} == expected_ids


def test_bootstrap_seed_strategy_definitions_preserves_existing_repository_rows():
    existing = StrategyDefinitionRecord(
        strategy_definition_id="existing-definition",
        strategy_id="existing_strategy_v1",
        version="v1",
        display_name="Existing Strategy",
        strategy_layer="tactical_pattern",
        typical_horizon="1d-1w",
        config_json={},
        lifecycle_status="active",
        is_active=True,
        source="seed",
    )

    class _Repository:
        def __init__(self) -> None:
            self.rows = [existing]
            self.save_calls = 0

        def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
            return list(self.rows)

        def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
            self.save_calls += 1
            self.rows.append(definition)

    repository = _Repository()

    seed_initial_strategy_definitions(repository)

    assert repository.rows == [existing]
    assert repository.save_calls == 0


def test_build_runtime_report_produces_normalized_contract():
    result = build_runtime_report(
        phase="preopen",
        as_of=datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc),
        summary={"candidate_count": 1},
        execution={"mode": "dry_run", "orders_submitted": 0},
    )

    assert result == {
        "status": "passed",
        "phase": "preopen",
        "as_of": "2026-06-03T12:45:00+00:00",
        "summary": {"candidate_count": 1},
        "execution": {"mode": "dry_run", "orders_submitted": 0},
    }


def test_build_execution_report_supports_dry_run_mode():
    assert build_execution_report(mode="dry_run", orders_submitted=0) == {
        "mode": "dry_run",
        "orders_submitted": 0,
    }


def test_live_risk_workflow_reuses_persisted_portfolio_snapshot_id_for_risk_decisions():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    portfolio_snapshot_id = "persisted-portfolio-risk-snapshot"
    captured_decisions: list[object] = []

    class _Repository:
        def load_signal_snapshots_for_decision(self, *, decision_time, snapshot_type):
            assert snapshot_type == "pre_open"
            return (
                SimpleNamespace(
                    signal_snapshot_id="snapshot-1",
                    signal_json={"technical": {"dollar_volume": 100_000_000.0}},
                    source_freshness_json={"technical": "fresh"},
                ),
            )

        def save_portfolio_risk_snapshot(self, snapshot):
            assert snapshot.portfolio_risk_snapshot_id == portfolio_snapshot_id

        def save_risk_factor_exposures(self, exposures):
            assert exposures == ()

        def save_position_sizing_decision(self, decision):
            assert decision.position_sizing_decision_id == "sizing-1"

        def save_risk_decision(self, decision):
            captured_decisions.append(decision)

    class _SourceRepository:
        def records_for_ticker(self, ticker, decision_time):
            return ()

        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, family, decision_time
            return ()

    class _ConfigResolver:
        def resolve(self, **kwargs):
            return SimpleNamespace(risk_appetite="balanced")

    class _PositionSizer:
        def size_position(self, request, portfolio_context, config):
            del request, portfolio_context, config
            return SimpleNamespace(
                position_sizing_decision_id="sizing-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                ticker="AAPL",
                risk_appetite="balanced",
                base_weight=0.05,
                volatility_adjusted_weight=0.05,
                liquidity_capped_weight=0.05,
                final_weight=0.05,
                final_notional=5000.0,
                applied_caps=[],
                binding_constraint=None,
                decision_time=decision_time,
                metadata_json={},
            )

    class _RiskManager:
        def build_portfolio_risk_snapshot(self, portfolio_context, config):
            del portfolio_context, config
            return SimpleNamespace(
                portfolio_risk_snapshot_id=portfolio_snapshot_id,
                decision_time=decision_time,
                risk_appetite="balanced",
                resolver_version="v1",
                margin_model_profile="alpaca",
                margin_model_version="broker",
                account_equity=100000.0,
                cash_balance=100000.0,
                buying_power=200000.0,
                excess_liquidity=100000.0,
                stock_margin_requirement=0.0,
                option_margin_requirement=0.0,
                total_margin_requirement=0.0,
                initial_margin_requirement=0.0,
                maintenance_margin_requirement=0.0,
                margin_requirement_source="broker_reported",
                net_exposure=0.0,
                gross_exposure=0.0,
                beta_adjusted_net_exposure=0.0,
                concentration_flags=[],
                metadata_json={},
            )

        def compute_factor_exposures(self, portfolio_context):
            del portfolio_context
            return ()

        def evaluate(self, request, sizing, portfolio_context, config):
            del request, sizing, portfolio_context, config
            return RiskDecisionRecord(
                risk_decision_id="risk-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                position_sizing_decision_id="sizing-1",
                ticker="AAPL",
                status="approved",
                reason_code="within_limits",
                approved_weight=0.05,
                approved_notional=5000.0,
                approved_quantity=25.0,
                portfolio_risk_snapshot_id="transient-snapshot-id",
                applied_rules=["single_name_limit_ok"],
                generated_hedge_action=None,
                decision_time=decision_time,
                metadata_json={},
            )

    workflow = _LiveRiskWorkflow(
        repository=_Repository(),
        source_repository=_SourceRepository(),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
    )

    result = workflow.run(
        candidates=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                signal_snapshot_id="snapshot-1",
                ticker="AAPL",
                candidate_score=0.5,
                decision_time=decision_time,
            ),
        ),
        classifications=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                trade_identity="tactical_stock_trade",
            ),
        ),
        portfolio_context=SimpleNamespace(),
        decision_time=decision_time,
    )

    assert len(result.risk_decisions) == 1
    assert len(captured_decisions) == 1
    assert captured_decisions[0].portfolio_risk_snapshot_id == portfolio_snapshot_id
