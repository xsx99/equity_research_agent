from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig
from src.trading.data_sources.live_universe import LiveUniverseProvider
from src.trading.risk import (
    HedgeActionRecord,
    OptionRiskAssessment,
    PortfolioRiskIntentRecord,
    RiskDecisionRecord,
)
from src.trading.runtime.preopen_dependencies import _ConfiguredLiveUniverseScanPipeline
from src.trading.runtime.preopen_risk import _LiveRiskWorkflow, _build_trade_risk_request
from src.trading.runtime.preopen import (
    LivePreopenDependencies,
    LivePreopenRuntime,
    run_live_preopen_once,
)
from src.trading.runtime.preopen_dependencies import build_live_preopen_dependencies
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


def _build_runtime(
    *,
    execute_paper_orders: bool,
    execute_paper_option_orders: bool = False,
    execution_result: object | None = None,
) -> tuple[LivePreopenRuntime, _CallRecorder]:
    recorder = _CallRecorder()
    universe_result = SimpleNamespace(included_symbols=("AAPL", "MSFT"))
    strategy_result = SimpleNamespace(
        candidates=(SimpleNamespace(ticker="AAPL"),),
        classifications=(SimpleNamespace(ticker="AAPL"),),
    )
    portfolio_result = SimpleNamespace(portfolio_context=SimpleNamespace(account_equity=100000.0))
    risk_result = SimpleNamespace(risk_decisions=(SimpleNamespace(ticker="AAPL"),))
    decision_result = SimpleNamespace(decisions=(SimpleNamespace(ticker="AAPL", decision="enter_long"),))
    execution_result = execution_result or SimpleNamespace(paper_orders=(SimpleNamespace(ticker="AAPL"),))
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
        execute_paper_option_orders=execute_paper_option_orders,
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


def test_live_preopen_runtime_requires_paper_execution_when_option_execution_enabled():
    runtime, _recorder = _build_runtime(
        execute_paper_orders=False,
        execute_paper_option_orders=True,
    )

    try:
        runtime.run()
    except ValueError as exc:
        assert str(exc) == "option_execution_requires_paper_order_execution"
    else:
        raise AssertionError("expected option execution policy validation to fail")


def test_live_preopen_runtime_reports_option_orders_separately_when_enabled():
    runtime, recorder = _build_runtime(
        execute_paper_orders=True,
        execute_paper_option_orders=True,
        execution_result=SimpleNamespace(
            paper_orders=(SimpleNamespace(ticker="AAPL"),),
            paper_option_orders=(SimpleNamespace(ticker="AAPL", option_symbol="AAPL240621C00200000"),),
        ),
    )

    result = runtime.run()

    assert recorder.calls[-1] == "paper_execution"
    assert result["execution"] == {
        "mode": "execute",
        "orders_submitted": 1,
        "option_orders_submitted": 1,
    }


def test_run_live_preopen_once_builds_default_dependencies_when_not_injected(monkeypatch):
    runtime_instance, _recorder = _build_runtime(execute_paper_orders=False)

    monkeypatch.setattr(
        "src.trading.runtime.preopen.build_live_preopen_dependencies",
        lambda _session: runtime_instance.dependencies,
    )

    result = run_live_preopen_once(now=lambda: datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc))

    assert result["status"] == "passed"
    assert result["execution"]["mode"] == "dry_run"


def test_build_live_preopen_dependencies_wires_fallback_reapproval_into_paper_execution(monkeypatch):
    captured: dict[str, object] = {}

    class _Repo:
        pass

    class _SourceRepo:
        pass

    class _ManualService:
        pass

    class _Broker:
        pass

    class _OptionBroker:
        def __init__(self, **kwargs):
            captured["option_broker_kwargs"] = kwargs

    class _ConfigResolver:
        pass

    class _PositionSizer:
        pass

    class _RiskManager:
        pass

    class _OptionRiskManager:
        pass

    class _PromptRegistry:
        @staticmethod
        def get_default():
            return "prompt-registry"

    class _SignalPipeline:
        def __init__(self, **kwargs):
            captured["signal_pipeline_kwargs"] = kwargs

    class _StrategyPipeline:
        def __init__(self, **kwargs):
            captured["strategy_pipeline_kwargs"] = kwargs

    class _PortfolioSyncWorkflow:
        def __init__(self, **kwargs):
            captured["portfolio_sync_kwargs"] = kwargs

    class _TradingDecisionPipeline:
        def __init__(self, **kwargs):
            captured["trading_decision_kwargs"] = kwargs

    class _PaperExecutionWorkflow:
        def __init__(self, **kwargs):
            captured["paper_execution_kwargs"] = kwargs

    monkeypatch.setattr("src.trading.runtime.preopen_dependencies.seed_initial_strategy_definitions", lambda repo: captured.setdefault("seed_repo", repo))
    monkeypatch.setattr("src.trading.runtime.preopen_dependencies.build_default_news_provider", lambda: "news-provider")
    monkeypatch.setattr("src.trading.runtime.preopen_dependencies.app_config.TRADING_MODEL_NAME", "gpt-5-mini")
    monkeypatch.setattr("src.agents.prompt_registry.PromptRegistry", _PromptRegistry)
    monkeypatch.setattr("src.agents.trading._default_agent_runner", "runner")
    monkeypatch.setattr("src.providers.market_data.AlpacaMarketDataProvider", lambda: "market-provider")
    monkeypatch.setattr("src.trading.brokers.paper_stock.PaperStockBroker", lambda: _Broker())
    monkeypatch.setattr("src.trading.brokers.paper_option.PaperOptionBroker", _OptionBroker)
    monkeypatch.setattr("src.trading.data_sources.live_universe.LiveUniverseProvider", lambda **kwargs: ("live-universe-provider", kwargs))
    monkeypatch.setattr("src.trading.manual_review.sqlalchemy.SQLAlchemyManualTickerRequestService", lambda session: _ManualService())
    monkeypatch.setattr("src.trading.repositories.source_sqlalchemy.SQLAlchemySignalSourceRepository", lambda session: _SourceRepo())
    monkeypatch.setattr("src.trading.repositories.sqlalchemy.SqlAlchemyTradingRepository", lambda session: _Repo())
    monkeypatch.setattr("src.trading.risk.config.RiskConfigResolver", lambda: _ConfigResolver())
    monkeypatch.setattr("src.trading.risk.sizing.PositionSizer", lambda: _PositionSizer())
    monkeypatch.setattr("src.trading.risk.manager.RiskManager", lambda: _RiskManager())
    monkeypatch.setattr("src.trading.risk.options.OptionRiskManager", lambda: _OptionRiskManager())
    monkeypatch.setattr("src.trading.signals.source_ingestion.SourceIngestionService", lambda **kwargs: ("signal-ingestion", kwargs))
    monkeypatch.setattr("src.trading.workflows.signal_snapshot.SignalPipeline", _SignalPipeline)
    monkeypatch.setattr("src.trading.workflows.strategy_scoring.StrategyPipeline", _StrategyPipeline)
    monkeypatch.setattr("src.trading.workflows.portfolio_sync.BrokerPortfolioSyncWorkflow", _PortfolioSyncWorkflow)
    monkeypatch.setattr("src.trading.workflows.trading_decision.TradingDecisionPipeline", _TradingDecisionPipeline)
    monkeypatch.setattr("src.trading.workflows.paper_execution.PaperExecutionWorkflow", _PaperExecutionWorkflow)

    dependencies = build_live_preopen_dependencies(session=object())

    assert isinstance(dependencies, LivePreopenDependencies)
    assert captured["seed_repo"].__class__ is _Repo
    assert captured["trading_decision_kwargs"]["source_repository"].__class__ is _SourceRepo
    assert captured["paper_execution_kwargs"]["config_resolver"].__class__ is _ConfigResolver
    assert captured["paper_execution_kwargs"]["position_sizer"].__class__ is _PositionSizer
    assert captured["paper_execution_kwargs"]["risk_manager"].__class__ is _RiskManager
    assert captured["paper_execution_kwargs"]["option_risk_manager"].__class__ is _OptionRiskManager
    assert captured["paper_execution_kwargs"]["option_broker"].__class__ is _OptionBroker
    assert captured["option_broker_kwargs"]["trading_base_url"] == "https://paper-api.alpaca.markets"


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
    assert build_execution_report(mode="dry_run", orders_submitted=0, option_orders_submitted=0) == {
        "mode": "dry_run",
        "orders_submitted": 0,
        "option_orders_submitted": 0,
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


def test_build_trade_risk_request_maps_tactical_option_trade_to_option_instrument():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, family, decision_time
            return [SimpleNamespace(payload={"bars": [{"close": 200.0}]})]

    request = _build_trade_risk_request(
        candidate=SimpleNamespace(
            candidate_score_id="candidate-1",
            signal_snapshot_id="snapshot-1",
            ticker="NVDA",
            candidate_score=0.8,
        ),
        classification=SimpleNamespace(
            candidate_score_id="candidate-1",
            trade_classification_id="classification-1",
            trade_identity="tactical_option_trade",
        ),
        snapshot=SimpleNamespace(
            signal_json={"technical": {"atr_pct": 0.06, "dollar_volume": 50_000_000}},
            source_freshness_json={"technical": "fresh"},
        ),
        source_repository=_SourceRepository(),
        decision_time=decision_time,
    )

    assert request.instrument_type == "option"


def test_build_trade_risk_request_marks_option_metadata_incomplete_without_chain():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, family, decision_time
            return [SimpleNamespace(payload={"bars": [{"close": 200.0}]})]

    request = _build_trade_risk_request(
        candidate=SimpleNamespace(
            candidate_score_id="candidate-1",
            signal_snapshot_id="snapshot-1",
            ticker="NVDA",
            candidate_score=0.8,
        ),
        classification=SimpleNamespace(
            candidate_score_id="candidate-1",
            trade_classification_id="classification-1",
            trade_identity="tactical_option_trade",
        ),
        snapshot=SimpleNamespace(
            signal_json={"technical": {"atr_pct": 0.06, "dollar_volume": 50_000_000}},
            source_freshness_json={"technical": "fresh"},
        ),
        source_repository=_SourceRepository(),
        decision_time=decision_time,
    )

    assert request.option_risk_metadata_complete is False


def test_build_trade_risk_request_uses_option_chain_premium_for_option_price_proxy():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, decision_time
            if family == "technical":
                return [SimpleNamespace(payload={"bars": [{"close": 200.0}]})]
            if family == "option_chain":
                return [
                    SimpleNamespace(
                        payload={
                            "contracts": [
                                {
                                    "contract_symbol": "NVDA260703C00195000",
                                    "option_type": "call",
                                    "strike": 195.0,
                                    "expiry": "2026-07-03",
                                    "dte": 30,
                                    "delta": 0.42,
                                    "gamma": 0.03,
                                    "theta": -0.02,
                                    "vega": 0.08,
                                    "bid": 3.1,
                                    "ask": 3.3,
                                    "mid": 3.2,
                                    "chosen_price": 3.2,
                                    "open_interest": 1200,
                                    "volume": 180,
                                }
                            ]
                        }
                    )
                ]
            return []

    request = _build_trade_risk_request(
        candidate=SimpleNamespace(
            candidate_score_id="candidate-1",
            signal_snapshot_id="snapshot-1",
            ticker="NVDA",
            candidate_score=0.8,
        ),
        classification=SimpleNamespace(
            candidate_score_id="candidate-1",
            trade_classification_id="classification-1",
            trade_identity="tactical_option_trade",
        ),
        snapshot=SimpleNamespace(
            signal_json={"technical": {"atr_pct": 0.06, "dollar_volume": 50_000_000}},
            source_freshness_json={"technical": "fresh"},
        ),
        source_repository=_SourceRepository(),
        decision_time=decision_time,
    )

    assert request.option_risk_metadata_complete is True
    assert request.price == 320.0
    assert request.estimated_margin_requirement == 320.0
    assert request.estimated_buying_power_effect == 320.0


def test_build_trade_risk_request_uses_expression_payload_for_option_spread_risk():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, decision_time
            if family == "technical":
                return [SimpleNamespace(payload={"bars": [{"close": 118.0}]})]
            if family == "option_chain":
                return [
                    SimpleNamespace(
                        payload={
                            "contracts": [
                                {
                                    "contract_symbol": "NVDA260624P00114500",
                                    "option_type": "put",
                                    "strike": 114.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.28,
                                    "gamma": 0.02,
                                    "theta": 0.01,
                                    "vega": -0.07,
                                    "iv_rank": 0.6,
                                    "bid": 1.5,
                                    "ask": 1.7,
                                    "mid": 1.6,
                                    "chosen_price": 1.6,
                                    "open_interest": 1500,
                                    "volume": 240,
                                },
                                {
                                    "contract_symbol": "NVDA260624P00108500",
                                    "option_type": "put",
                                    "strike": 108.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.12,
                                    "gamma": 0.01,
                                    "theta": -0.01,
                                    "vega": 0.04,
                                    "iv_rank": 0.58,
                                    "bid": 0.9,
                                    "ask": 1.1,
                                    "mid": 1.0,
                                    "chosen_price": 1.0,
                                    "open_interest": 900,
                                    "volume": 120,
                                },
                            ]
                        }
                    )
                ]
            return []

    expression_definitions = {
        "defined_risk_income_spread": StrategyDefinitionRecord(
            strategy_definition_id="defined-risk-income-spread-definition",
            strategy_id="defined_risk_income_spread",
            version="v1",
            display_name="defined_risk_income_spread",
            strategy_layer="expression_bucket",
            typical_horizon="2w-8w",
            config_json={
                "default_trade_identity": "tactical_option_trade",
                "allowed_instruments": ["paper_option_strategy"],
                "allowed_option_strategy_types": ["put_credit_spread", "call_credit_spread"],
                "option_policy": {"non_event_dte_days": 21},
                "default_exit_policy": "strategy_invalidators_or_target_horizon",
            },
            lifecycle_status="active",
            is_active=True,
            source="test",
        )
    }

    request = _build_trade_risk_request(
        candidate=SimpleNamespace(
            candidate_score_id="candidate-1",
            signal_snapshot_id="snapshot-1",
            ticker="NVDA",
            candidate_score=0.8,
            decision_time=decision_time,
            direction="bullish",
            action="enter_long",
            strategy_id="strong_theme_catalyst_continuation_v1",
            strategy_version="v1",
        ),
        classification=SimpleNamespace(
            candidate_score_id="candidate-1",
            trade_classification_id="classification-1",
            trade_identity="tactical_option_trade",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
        ),
        snapshot=SimpleNamespace(
            signal_json={
                "technical": {"last_price": 118.0, "atr_pct": 0.06, "dollar_volume": 50_000_000},
                "events_news": {},
            },
            source_freshness_json={"technical": "fresh"},
        ),
        source_repository=_SourceRepository(),
        decision_time=decision_time,
        expression_definitions=expression_definitions,
    )

    assert request.option_risk_metadata_complete is True
    assert request.price == 60.0
    assert request.estimated_margin_requirement == 540.0
    assert request.estimated_buying_power_effect == 540.0
    assert request.assignment_notional == 11450.0
    assert request.event_through_horizon is False


def test_live_risk_workflow_rejects_option_trade_when_assignment_risk_fails():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    saved_option_snapshots: list[object] = []

    class _Repository:
        def load_signal_snapshots_for_decision(self, *, decision_time, snapshot_type):
            del decision_time, snapshot_type
            return (
                SimpleNamespace(
                    signal_snapshot_id="snapshot-1",
                    signal_json={
                        "technical": {
                            "last_price": 118.0,
                            "atr_pct": 0.06,
                            "dollar_volume": 50_000_000,
                        },
                        "events_news": {},
                    },
                    source_freshness_json={"technical": "fresh"},
                ),
            )

        def load_active_strategy_definitions(self):
            return [
                StrategyDefinitionRecord(
                    strategy_definition_id="defined-risk-income-spread-definition",
                    strategy_id="defined_risk_income_spread",
                    version="v1",
                    display_name="defined_risk_income_spread",
                    strategy_layer="expression_bucket",
                    typical_horizon="2w-8w",
                    config_json={
                        "default_trade_identity": "tactical_option_trade",
                        "allowed_instruments": ["paper_option_strategy"],
                        "allowed_option_strategy_types": ["put_credit_spread", "call_credit_spread"],
                        "option_policy": {"non_event_dte_days": 21},
                        "default_exit_policy": "strategy_invalidators_or_target_horizon",
                    },
                    lifecycle_status="active",
                    is_active=True,
                    source="test",
                )
            ]

        def save_portfolio_risk_snapshot(self, snapshot):
            del snapshot

        def save_risk_factor_exposures(self, exposures):
            del exposures

        def save_position_sizing_decision(self, sizing):
            del sizing

        def save_risk_decision(self, decision):
            self.saved_decision = decision

        def save_option_risk_snapshot(self, snapshot):
            saved_option_snapshots.append(snapshot)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, decision_time
            if family == "technical":
                return [SimpleNamespace(payload={"bars": [{"close": 118.0}]})]
            if family == "option_chain":
                return [
                    SimpleNamespace(
                        payload={
                            "contracts": [
                                {
                                    "option_type": "put",
                                    "strike": 114.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.28,
                                    "gamma": 0.02,
                                    "theta": 0.01,
                                    "vega": -0.07,
                                    "iv_rank": 0.6,
                                    "bid": 1.5,
                                    "ask": 1.7,
                                    "mid": 1.6,
                                    "chosen_price": 1.6,
                                    "open_interest": 1500,
                                    "volume": 240,
                                },
                                {
                                    "option_type": "put",
                                    "strike": 108.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.12,
                                    "gamma": 0.01,
                                    "theta": -0.01,
                                    "vega": 0.04,
                                    "iv_rank": 0.58,
                                    "bid": 0.9,
                                    "ask": 1.1,
                                    "mid": 1.0,
                                    "chosen_price": 1.0,
                                    "open_interest": 900,
                                    "volume": 120,
                                },
                            ]
                        }
                    )
                ]
            return []

    class _ConfigResolver:
        def resolve(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                risk_appetite="balanced",
                resolver_version="v1",
                margin_model_profile="alpaca",
                margin_model_version="broker",
                max_sector_weight=0.30,
                assignment_concentration_limit=0.10,
            )

    class _PositionSizer:
        def size_position(self, request, portfolio_context, config):
            del request, portfolio_context, config
            return SimpleNamespace(
                position_sizing_decision_id="sizing-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                ticker="NVDA",
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
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
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

        def evaluate(self, request, sizing, portfolio_context, config, portfolio_risk_intent=None):
            del request, sizing, portfolio_context, config, portfolio_risk_intent
            return RiskDecisionRecord(
                risk_decision_id="risk-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                position_sizing_decision_id="sizing-1",
                ticker="NVDA",
                status="approved",
                reason_code="within_limits",
                approved_weight=0.05,
                approved_notional=5000.0,
                approved_quantity=83.33,
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
                applied_rules=["single_name_limit_ok"],
                generated_hedge_action=None,
                decision_time=decision_time,
                metadata_json={},
            )

    class _OptionRiskManager:
        def evaluate_assignment_risk(self, option_risk, *, portfolio_context, config):
            del portfolio_context, config
            assert option_risk.option_strategy_type == "put_credit_spread"
            assert option_risk.margin_requirement == 540.0
            assert option_risk.buying_power_effect == 540.0
            return OptionRiskAssessment(
                status="rejected",
                reason_code="assignment_concentration_cap",
                worst_case_assignment_notional=11450.0,
                portfolio_delta=-0.16,
                portfolio_gamma=0.03,
                portfolio_theta=0.0,
                portfolio_vega=-0.03,
            )

    workflow = _LiveRiskWorkflow(
        repository=_Repository(),
        source_repository=_SourceRepository(),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
        option_risk_manager=_OptionRiskManager(),
    )

    result = workflow.run(
        candidates=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                signal_snapshot_id="snapshot-1",
                ticker="NVDA",
                candidate_score=0.8,
                decision_time=decision_time,
                direction="bullish",
                action="enter_long",
                strategy_id="strong_theme_catalyst_continuation_v1",
                strategy_version="v1",
            ),
        ),
        classifications=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                trade_identity="tactical_option_trade",
                expression_bucket_id="defined_risk_income_spread",
                expression_bucket_version="v1",
            ),
        ),
        portfolio_context=SimpleNamespace(
            account_equity=100000.0,
            positions=(),
            cash_balance=100000.0,
            buying_power=200000.0,
            excess_liquidity=100000.0,
            stock_margin_requirement=0.0,
            option_margin_requirement=0.0,
            total_margin_requirement=0.0,
            initial_margin_requirement=0.0,
            maintenance_margin_requirement=0.0,
            margin_requirement_source="broker_reported",
            approved_core_tickers=(),
        ),
        decision_time=decision_time,
    )

    assert result.risk_decisions[0].status == "rejected"
    assert result.risk_decisions[0].reason_code == "assignment_concentration_cap"
    assert "option_assignment_risk_check" in result.risk_decisions[0].applied_rules
    assert len(saved_option_snapshots) == 1
    assert saved_option_snapshots[0].worst_case_assignment_notional == 11450.0


def test_live_risk_workflow_persists_richer_option_risk_reason_codes():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    saved_option_snapshots: list[object] = []

    class _Repository:
        def load_signal_snapshots_for_decision(self, *, decision_time, snapshot_type):
            del decision_time, snapshot_type
            return (
                SimpleNamespace(
                    signal_snapshot_id="snapshot-1",
                    signal_json={
                        "technical": {"atr_pct": 0.03},
                        "fundamental": {"sector": "Technology"},
                        "events_news": {},
                    },
                    source_freshness_json={"technical": "fresh", "fundamental": "fresh", "events_news": "fresh"},
                ),
            )

        def load_active_strategy_definitions(self):
            return [
                StrategyDefinitionRecord(
                    strategy_definition_id="defined-risk-income-spread-definition",
                    strategy_id="defined_risk_income_spread",
                    version="v1",
                    display_name="defined_risk_income_spread",
                    strategy_layer="expression_bucket",
                    typical_horizon="2w-8w",
                    config_json={
                        "default_trade_identity": "tactical_option_trade",
                        "allowed_instruments": ["paper_option_strategy"],
                        "allowed_option_strategy_types": ["put_credit_spread", "call_credit_spread"],
                        "option_policy": {"non_event_dte_days": 21},
                        "default_exit_policy": "strategy_invalidators_or_target_horizon",
                    },
                    lifecycle_status="active",
                    is_active=True,
                    source="test",
                )
            ]

        def save_portfolio_risk_snapshot(self, snapshot):
            del snapshot

        def save_risk_factor_exposures(self, exposures):
            del exposures

        def save_position_sizing_decision(self, sizing):
            del sizing

        def save_risk_decision(self, decision):
            self.saved_decision = decision

        def save_option_risk_snapshot(self, snapshot):
            saved_option_snapshots.append(snapshot)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, decision_time
            if family == "technical":
                return [SimpleNamespace(payload={"bars": [{"close": 118.0}]})]
            if family == "option_chain":
                return [
                    SimpleNamespace(
                        payload={
                            "contracts": [
                                {
                                    "option_type": "put",
                                    "strike": 114.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.28,
                                    "gamma": 0.02,
                                    "theta": 0.01,
                                    "vega": -0.07,
                                    "iv_rank": 0.6,
                                    "bid": 1.5,
                                    "ask": 1.7,
                                    "mid": 1.6,
                                    "chosen_price": 1.6,
                                    "open_interest": 1500,
                                    "volume": 240,
                                },
                                {
                                    "option_type": "put",
                                    "strike": 108.5,
                                    "expiry": "2026-06-24",
                                    "dte": 21,
                                    "delta": -0.12,
                                    "gamma": 0.01,
                                    "theta": -0.01,
                                    "vega": 0.04,
                                    "iv_rank": 0.58,
                                    "bid": 0.9,
                                    "ask": 1.1,
                                    "mid": 1.0,
                                    "chosen_price": 1.0,
                                    "open_interest": 900,
                                    "volume": 120,
                                },
                            ]
                        }
                    )
                ]
            return []

    class _ConfigResolver:
        def resolve(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                risk_appetite="balanced",
                resolver_version="v1",
                margin_model_profile="alpaca",
                margin_model_version="broker",
                max_sector_weight=0.30,
                assignment_concentration_limit=0.15,
            )

    class _PositionSizer:
        def size_position(self, request, portfolio_context, config):
            del request, portfolio_context, config
            return SimpleNamespace(
                position_sizing_decision_id="sizing-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                ticker="NVDA",
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
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
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

        def evaluate(self, request, sizing, portfolio_context, config, portfolio_risk_intent=None):
            del request, sizing, portfolio_context, config, portfolio_risk_intent
            return RiskDecisionRecord(
                risk_decision_id="risk-1",
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                position_sizing_decision_id="sizing-1",
                ticker="NVDA",
                status="approved",
                reason_code="within_limits",
                approved_weight=0.05,
                approved_notional=5000.0,
                approved_quantity=83.33,
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
                applied_rules=["single_name_limit_ok"],
                generated_hedge_action=None,
                decision_time=decision_time,
                metadata_json={},
            )

    class _OptionRiskManager:
        def evaluate_assignment_risk(self, option_risk, *, portfolio_context, config):
            del portfolio_context, config
            assert option_risk.sector == "Technology"
            return OptionRiskAssessment(
                status="rejected",
                reason_code="assignment_sector_concentration_cap",
                worst_case_assignment_notional=11450.0,
                portfolio_delta=-0.16,
                portfolio_gamma=0.03,
                portfolio_theta=0.0,
                portfolio_vega=-0.03,
                metadata_json={
                    "assignment_ratio": 0.1145,
                    "sector_exposure_after_assignment_ratio": 0.3645,
                    "blocked_exposure_basis": "sector_after_assignment",
                },
            )

    workflow = _LiveRiskWorkflow(
        repository=_Repository(),
        source_repository=_SourceRepository(),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
        option_risk_manager=_OptionRiskManager(),
    )

    result = workflow.run(
        candidates=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                signal_snapshot_id="snapshot-1",
                ticker="NVDA",
                candidate_score=0.8,
                decision_time=decision_time,
                direction="bullish",
                action="enter_long",
                strategy_id="strong_theme_catalyst_continuation_v1",
                strategy_version="v1",
            ),
        ),
        classifications=(
            SimpleNamespace(
                candidate_score_id="candidate-1",
                trade_classification_id="classification-1",
                trade_identity="tactical_option_trade",
                expression_bucket_id="defined_risk_income_spread",
                expression_bucket_version="v1",
            ),
        ),
        portfolio_context=SimpleNamespace(
            account_equity=100000.0,
            positions=(),
            cash_balance=100000.0,
            buying_power=200000.0,
            excess_liquidity=100000.0,
            stock_margin_requirement=0.0,
            option_margin_requirement=0.0,
            total_margin_requirement=0.0,
            initial_margin_requirement=0.0,
            maintenance_margin_requirement=0.0,
            margin_requirement_source="broker_reported",
            approved_core_tickers=(),
        ),
        decision_time=decision_time,
    )

    assert result.risk_decisions[0].status == "rejected"
    assert result.risk_decisions[0].reason_code == "assignment_sector_concentration_cap"
    assert result.risk_decisions[0].metadata_json["option_risk_reason_code"] == "assignment_sector_concentration_cap"
    assert result.risk_decisions[0].metadata_json["option_risk_checks"]["blocked_exposure_basis"] == "sector_after_assignment"
    assert len(saved_option_snapshots) == 1
    assert saved_option_snapshots[0].metadata_json["option_risk_reason_code"] == "assignment_sector_concentration_cap"
    assert saved_option_snapshots[0].metadata_json["option_risk_checks"]["sector_exposure_after_assignment_ratio"] == 0.3645


def test_live_risk_workflow_persists_portfolio_risk_intent_and_materializes_generated_hedge():
    decision_time = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    saved_intents: list[PortfolioRiskIntentRecord] = []
    saved_decisions: list[RiskDecisionRecord] = []
    captured_intents: list[PortfolioRiskIntentRecord | None] = []

    class _Repository:
        def load_signal_snapshots_for_decision(self, *, decision_time, snapshot_type):
            del decision_time, snapshot_type
            return (
                SimpleNamespace(
                    signal_snapshot_id="snapshot-1",
                    signal_json={"events_news": {"earnings_in_days": 2}},
                    source_freshness_json={"technical": "fresh"},
                ),
            )

        def save_portfolio_risk_snapshot(self, snapshot):
            del snapshot

        def save_risk_factor_exposures(self, exposures):
            del exposures

        def save_portfolio_risk_intent(self, intent):
            saved_intents.append(intent)

        def save_position_sizing_decision(self, sizing):
            del sizing

        def save_risk_decision(self, decision):
            saved_decisions.append(decision)

    class _SourceRepository:
        def latest_available_by_family(self, ticker, family, decision_time):
            del ticker, family, decision_time
            return [SimpleNamespace(payload={"bars": [{"close": 200.0}]})]

    class _ConfigResolver:
        def resolve(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                risk_appetite="balanced",
                resolver_version="v1",
                margin_model_profile="alpaca",
                margin_model_version="broker",
                max_sector_weight=0.30,
            )

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
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
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

        def evaluate(self, request, sizing, portfolio_context, config, portfolio_risk_intent=None):
            del request, sizing, portfolio_context, config
            captured_intents.append(portfolio_risk_intent)
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
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
                applied_rules=["single_name_limit_ok"],
                generated_hedge_action=None,
                decision_time=decision_time,
                metadata_json={},
            )

    class _LookaheadHelper:
        def build_preopen_portfolio_risk_intent(self, **kwargs):
            del kwargs
            return PortfolioRiskIntentRecord.create(
                portfolio_risk_snapshot_id="snapshot-portfolio-1",
                decision_time=decision_time,
                risk_window="1-5d",
                aggregate_risk_state="macro_high_risk",
                hedge_actions=(
                    HedgeActionRecord(
                        action="open_hedge",
                        risk_source="macro",
                        severity="high",
                        target_underlier="QQQ",
                        target_exposure_type="broad_market",
                        coverage_ratio=0.5,
                        reason_code="macro_high_overlay",
                        metadata_json={},
                    ),
                ),
            )

        def materialize_generated_hedges(self, *, risk_decisions, portfolio_risk_intent):
            del portfolio_risk_intent
            payload = {
                "action": "open_hedge",
                "risk_source": "macro",
                "severity": "high",
                "target_underlier": "QQQ",
                "target_exposure_type": "broad_market",
                "coverage_ratio": 0.5,
                "reason_code": "macro_high_overlay",
                "option_strategy_type": "long_put",
                "underlying_price": 500.0,
                "protected_notional": 5000.0,
            }
            return (replace(risk_decisions[0], generated_hedge_action=payload),)

    workflow = _LiveRiskWorkflow(
        repository=_Repository(),
        source_repository=_SourceRepository(),
        config_resolver=_ConfigResolver(),
        position_sizer=_PositionSizer(),
        risk_manager=_RiskManager(),
        lookahead_helper=_LookaheadHelper(),
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
        portfolio_context=SimpleNamespace(account_equity=100000.0, positions=()),
        decision_time=decision_time,
    )

    assert len(saved_intents) == 1
    assert captured_intents == [saved_intents[0]]
    assert result.risk_decisions[0].generated_hedge_action is not None
    assert result.risk_decisions[0].generated_hedge_action["target_underlier"] == "QQQ"
    assert saved_decisions[-1].generated_hedge_action["target_underlier"] == "QQQ"
