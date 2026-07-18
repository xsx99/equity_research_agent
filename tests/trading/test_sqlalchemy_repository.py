from __future__ import annotations

import operator
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    CalendarEvent,
    DailyReflection,
    EventNewsItem,
    IntradayRebalanceDecision,
    LearningFactor,
    LlmPromptRun,
    LlmPromptTemplate,
    LlmUsageEvent,
    ManualTickerRequest,
    MacroSnapshot,
    NewsAlert,
    OptionRiskSnapshot,
    OptionStrategyDecision,
    OptionStrategyLeg,
    PaperExecution,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PaperPosition,
    PaperOptionExecution,
    PaperOptionOrder,
    PortfolioEventRiskAssessment,
    PortfolioRiskSnapshot,
    PortfolioSnapshot as PortfolioSnapshotModel,
    RiskDecision,
    RiskHedgeDecision,
    RiskFactorExposure,
    SocialMacroItem,
    TradingRuntimeRun,
    TradingDecision,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
)
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.data_sources.universe import UniverseSnapshotResult, UniverseSymbolDecision
from src.trading.brokers.paper_option import PaperOptionExecutionRecord, PaperOptionOrderRecord, PaperOptionPosition
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.risk.context import PortfolioRiskSnapshotRecord, PositionSizingDecisionRecord, RiskFactorExposureRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository, _trading_decision_payload
from src.trading.runtime.trade_day import local_day_bounds_utc
from src.trading.workflows.paper_execution import PaperExecutionWorkflow
from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.risk import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord, RiskDecisionRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord
from src.agents.trading import PromptRunRecord
from src.agents.trading import UsageEventRecord
from src.agents.prompt_registry import PromptTemplate


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter(self, *criteria: Any) -> "_FakeQuery":
        filtered = [
            row
            for row in self._rows
            if all(_matches_filter_criterion(row, criterion) for criterion in criteria)
        ]
        return _FakeQuery(filtered)

    def filter_by(self, **kwargs: Any) -> "_FakeQuery":
        filtered = [
            row
            for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _FakeQuery(filtered)

    def all(self) -> list[object]:
        return list(self._rows)

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]

    def order_by(self, *criteria: Any) -> "_FakeQuery":
        return self


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}
        self.flush_calls = 0

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        return _FakeQuery(self.rows_by_type.get(model, []))

    def flush(self) -> None:
        self.flush_calls += 1


class _AutoflushFakeSession(_FakeSession):
    def query(self, model: type) -> _FakeQuery:
        self.flush()
        return super().query(model)

    def flush(self) -> None:
        for row in self.rows_by_type.get(LearningFactor, []):
            if getattr(row, "title", None) is None:
                raise AssertionError("autoflush attempted before learning factor fields were populated")
        super().flush()


def test_sqlalchemy_repository_persists_llm_prompt_telemetry_rows():
    session = _FakeSession()
    repo = SqlAlchemyTradingRepository(session)
    template = PromptTemplate(
        prompt_id="intraday_rebalance",
        prompt_version="v1",
        pipeline_name="intraday_rebalance",
        output_schema_id="IntradayRebalanceOutput",
        output_schema_version="v1",
        template="Decide {{ ticker }}",
        template_path="agents/prompts/trading/intraday_rebalance_v1.yaml",
        template_hash="template-hash",
    )
    prompt_run = PromptRunRecord(
        pipeline_name="intraday_rebalance",
        rendered_prompt_hash="rendered-hash",
        rendered_prompt_redacted="Decide AAPL",
        input_context_json={"ticker": "AAPL"},
        raw_output_text="{bad json",
        parsed_output_json={"ticker": "AAPL", "action": "hold"},
        parse_status="failed",
        validation_errors_json=["action field required"],
        fallback_action="hold",
        error_message="action field required",
    )
    usage_event = UsageEventRecord(
        provider="google",
        model="gemini-2.5-flash-lite",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        estimated_cost=0.001,
        latency_ms=1234,
        retry_count=1,
        status="succeeded",
    )

    repo.save_prompt_template(template)
    repo.save_prompt_run(prompt_run)
    repo.save_usage_events([usage_event])

    template_rows = session.rows_by_type.get(LlmPromptTemplate, [])
    run_rows = session.rows_by_type.get(LlmPromptRun, [])
    usage_rows = session.rows_by_type.get(LlmUsageEvent, [])
    assert len(template_rows) == 1
    assert len(run_rows) == 1
    assert len(usage_rows) == 1
    assert run_rows[0].prompt_template_id == template_rows[0].prompt_template_id
    assert run_rows[0].pipeline_name == "intraday_rebalance"
    assert run_rows[0].parse_status == "failed"
    assert run_rows[0].validation_errors_json == ["action field required"]
    assert usage_rows[0].prompt_run_id == run_rows[0].prompt_run_id
    assert usage_rows[0].retry_count == 1


def _matches_filter_criterion(row: object, criterion: Any) -> bool:
    if isinstance(criterion, BooleanClauseList):
        clauses = list(criterion.clauses)
        if criterion.operator is operator.and_:
            return all(_matches_filter_criterion(row, clause) for clause in clauses)
        if criterion.operator is operator.or_:
            return any(_matches_filter_criterion(row, clause) for clause in clauses)
        raise AssertionError(f"unsupported boolean operator: {criterion.operator!r}")
    if isinstance(criterion, BinaryExpression):
        left = _resolve_filter_operand(row, criterion.left)
        right = _resolve_filter_operand(row, criterion.right)
        if criterion.operator is operator.eq:
            return left == right
        if criterion.operator is operator.ne:
            return left != right
        if criterion.operator is operator.ge:
            return left is not None and right is not None and left >= right
        if criterion.operator is operator.gt:
            return left is not None and right is not None and left > right
        if criterion.operator is operator.le:
            return left is not None and right is not None and left <= right
        if criterion.operator is operator.lt:
            return left is not None and right is not None and left < right
        if getattr(criterion.operator, "__name__", "") == "in_op":
            return left in set(right)
        if getattr(criterion.operator, "__name__", "") == "not_in_op":
            return left not in set(right)
        raise AssertionError(f"unsupported comparison operator: {criterion.operator!r}")
    raise AssertionError(f"unsupported filter criterion: {criterion!r}")


def _resolve_filter_operand(row: object, operand: Any) -> Any:
    if hasattr(operand, "value"):
        return operand.value
    if hasattr(operand, "key"):
        return getattr(row, operand.key)
    return operand


def test_sqlalchemy_repository_persists_universe_snapshot_and_symbols():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    filter_id = uuid.uuid4()
    session.add(
        UniverseFilterConfig(
            universe_filter_config_id=filter_id,
            profile_name="default",
            version=1,
            is_active=True,
            min_price=5,
            min_avg_dollar_volume=25_000_000,
            included_sectors_json=[],
            excluded_sectors_json=[],
            included_industries_json=[],
            excluded_industries_json=[],
            exchanges_json=[],
            asset_types_json=["common_stock"],
            manual_include_json=["AAPL"],
            manual_exclude_json=[],
        )
    )
    snapshot = UniverseSnapshotResult(
        snapshot_id=str(uuid.uuid4()),
        snapshot_time=now,
        filter_config=UniverseFilterConfigRecord(profile_name="default", version=1, manual_include=("AAPL",)),
        included=(
            UniverseSymbolDecision(
                symbol="AAPL",
                status="included",
                exclusion_reason=None,
                asset=UniverseAsset(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Consumer Electronics",
                    price=200.0,
                    avg_dollar_volume=100_000_000.0,
                ),
            ),
        ),
        excluded=(
            UniverseSymbolDecision(
                symbol="XYZ",
                status="excluded",
                exclusion_reason="below_min_price",
                asset=UniverseAsset(
                    symbol="XYZ",
                    company_name="Example Co.",
                    asset_type="common_stock",
                    exchange="NASDAQ",
                    sector="Technology",
                    industry="Software",
                    price=2.0,
                    avg_dollar_volume=10_000_000.0,
                ),
            ),
        ),
        metadata={"provider": "alpaca_live"},
    )

    repository.save_universe_snapshot(snapshot)

    persisted_snapshot = session.query(UniverseSnapshot).one_or_none()
    persisted_symbols = session.query(UniverseSymbol).all()
    assert persisted_snapshot is not None
    assert persisted_snapshot.provider == "alpaca_live"
    assert persisted_snapshot.universe_filter_config_id == filter_id
    assert len(persisted_symbols) == 2


def test_sqlalchemy_repository_saves_and_loads_latest_runtime_run_by_phase_and_trade_date():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    first_completed = datetime(2026, 6, 20, 13, 45, tzinfo=timezone.utc)
    latest_completed = datetime(2026, 6, 20, 13, 49, tzinfo=timezone.utc)

    repository.save_runtime_run(
        {
            "phase": "preopen",
            "status": "passed",
            "trade_date": date(2026, 6, 20),
            "as_of": latest_completed,
            "started_at": datetime(2026, 6, 20, 13, 40, tzinfo=timezone.utc),
            "completed_at": first_completed,
            "summary_json": {"candidate_count": 3},
            "execution_json": {"mode": "dry_run", "orders_submitted": 0},
            "metadata_json": {"source": "run_live_preopen_once"},
        }
    )
    repository.save_runtime_run(
        {
            "phase": "preopen",
            "status": "failed",
            "trade_date": date(2026, 6, 19),
            "as_of": datetime(2026, 6, 19, 13, 49, tzinfo=timezone.utc),
            "started_at": datetime(2026, 6, 19, 13, 40, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 6, 19, 13, 41, tzinfo=timezone.utc),
            "summary_json": {"reasons": ["provider_unavailable"]},
            "execution_json": {"mode": "dry_run", "orders_submitted": 0},
            "metadata_json": {"source": "run_live_preopen_once"},
        }
    )
    repository.save_runtime_run(
        {
            "phase": "preopen",
            "status": "passed",
            "trade_date": date(2026, 6, 20),
            "as_of": latest_completed,
            "started_at": datetime(2026, 6, 20, 13, 47, tzinfo=timezone.utc),
            "completed_at": latest_completed,
            "summary_json": {"candidate_count": 9, "trading_decision_count": 2},
            "execution_json": {"mode": "execute", "orders_submitted": 1},
            "metadata_json": {"source": "run_live_preopen_once"},
        }
    )

    latest_same_day = repository.load_latest_runtime_run(
        phase="preopen",
        trade_date=date(2026, 6, 20),
    )
    latest_any_day = repository.load_latest_runtime_run(phase="preopen")

    assert latest_same_day is not None
    assert latest_same_day["status"] == "passed"
    assert latest_same_day["trade_date"] == date(2026, 6, 20)
    assert latest_same_day["summary_json"]["candidate_count"] == 9
    assert latest_same_day["execution_json"]["mode"] == "execute"
    assert latest_any_day == latest_same_day
    assert len(session.query(TradingRuntimeRun).all()) == 3


def test_sqlalchemy_repository_loads_intraday_request_contexts_with_schema_valid_selection_source():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    decision_time = datetime(2026, 6, 20, 15, 30, tzinfo=timezone.utc)
    session.rows_by_type[PaperPosition] = [
        SimpleNamespace(
            status="open",
            ticker="AAPL",
            quantity=10,
            average_cost=190.0,
            market_price=200.0,
            market_value=2000.0,
            trade_identity="tactical_stock_trade",
            strategy_id="relative_strength_rotation_v1",
            opened_at=decision_time,
            updated_at=decision_time,
            direction="long",
        )
    ]

    contexts = repository.load_intraday_request_contexts(
        tickers=("AAPL",),
        trade_date=decision_time.date(),
    )

    assert contexts["AAPL"].selection_source == "risk_manager"
    assert contexts["AAPL"].trade_identity == "tactical_stock_trade"


def test_trading_decision_payload_includes_rationale_fields_for_reflection_consumers():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        ticker="NVDA",
        decision="enter_long",
        strategy_id="relative_strength_rotation_v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="scanner",
        confidence=Decimal("0.74"),
        target_weight=Decimal("0.04"),
        approved_weight=Decimal("0.04"),
        decision_time=now,
        key_drivers_json=["sector_relative_strength", "relative_volume"],
        counterarguments_json=["valuation is elevated versus peers"],
        invalidators_json=["QQQ closes below prior close"],
        metadata_json={"paper_trade_authorized": True},
    )

    payload = _trading_decision_payload(row)

    assert payload["key_drivers"] == ["sector_relative_strength", "relative_volume"]
    assert payload["counterarguments"] == ["valuation is elevated versus peers"]
    assert payload["invalidators"] == ["QQQ closes below prior close"]


def test_sqlalchemy_repository_loads_manual_review_audit_rows_with_explicit_linkage_and_execution_states():
    now = datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc)
    request_id = uuid.uuid4()
    pending_request_id = uuid.uuid4()
    signal_snapshot_id = uuid.uuid4()
    trading_decision_id = uuid.uuid4()
    risk_decision_id = uuid.uuid4()
    paper_order_id = uuid.uuid4()
    paper_execution_id = uuid.uuid4()
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.rows_by_type[ManualTickerRequest] = [
        SimpleNamespace(
            manual_ticker_request_id=request_id,
            ticker="AAPL",
            reason="breakout retest",
            mode="paper_trade_eligible",
            status="active",
            created_at=now,
            last_evaluated_at=now,
            latest_result_status="actionable_trade",
            latest_signal_snapshot_id=signal_snapshot_id,
        ),
        SimpleNamespace(
            manual_ticker_request_id=pending_request_id,
            ticker="MSFT",
            reason="still waiting",
            mode="review_only",
            status="active",
            created_at=now,
            last_evaluated_at=None,
            latest_result_status=None,
            latest_signal_snapshot_id=None,
        ),
    ]
    session.rows_by_type[TradingDecision] = [
        SimpleNamespace(
            trading_decision_id=trading_decision_id,
            manual_request_id=request_id,
            risk_decision_id=risk_decision_id,
            ticker="AAPL",
            decision="enter_long",
            metadata_json={"paper_trade_authorized": True},
            decision_time=now,
            created_at=now,
        ),
    ]
    session.rows_by_type[RiskDecision] = [
        SimpleNamespace(
            risk_decision_id=risk_decision_id,
            ticker="AAPL",
            status="approved",
            reason_code="within_limits",
            decision_time=now,
            created_at=now,
        ),
    ]
    session.rows_by_type[PaperOrder] = [
        SimpleNamespace(
            paper_order_id=paper_order_id,
            trading_decision_id=trading_decision_id,
            ticker="AAPL",
            status="filled",
            rejection_reason=None,
            created_at=now,
        ),
    ]
    session.rows_by_type[PaperExecution] = [
        SimpleNamespace(
            paper_execution_id=paper_execution_id,
            paper_order_id=paper_order_id,
            ticker="AAPL",
            executed_at=now,
            created_at=now,
        ),
    ]

    rows = repository.load_manual_review_audit_rows()

    assert [row.ticker for row in rows] == ["AAPL", "MSFT"]
    assert rows[0].manual_ticker_request_id == str(request_id)
    assert rows[0].latest_signal_snapshot_id == str(signal_snapshot_id)
    assert rows[0].latest_trading_decision_id == str(trading_decision_id)
    assert rows[0].latest_decision_action == "enter_long"
    assert rows[0].latest_risk_outcome == "approved"
    assert rows[0].latest_order_status == "filled"
    assert rows[0].latest_execution_status == "filled"
    assert rows[0].execution_path_state == "filled"
    assert rows[0].linkage_state == "execution_linked"
    assert rows[1].manual_ticker_request_id == str(pending_request_id)
    assert rows[1].execution_path_state == "pending_evaluation"
    assert rows[1].linkage_state == "pending_evaluation"


def test_sqlalchemy_repository_persists_pr4_risk_artifacts():
    now = datetime(2026, 6, 3, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    portfolio_snapshot = PortfolioRiskSnapshotRecord(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="v1",
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        account_equity=100000.0,
        cash_balance=50000.0,
        buying_power=100000.0,
        excess_liquidity=50000.0,
        stock_margin_requirement=1000.0,
        option_margin_requirement=0.0,
        total_margin_requirement=1000.0,
        initial_margin_requirement=1000.0,
        maintenance_margin_requirement=500.0,
        margin_requirement_source="broker_reported",
        net_exposure=10000.0,
        gross_exposure=10000.0,
        beta_adjusted_net_exposure=9000.0,
        concentration_flags=["single_name_warning"],
        metadata_json={"macro_regime": "risk_on"},
    )
    exposures = (
        RiskFactorExposureRecord(
            factor_type="sector",
            factor_value="technology",
            gross_exposure=10000.0,
            net_exposure=10000.0,
            long_exposure=10000.0,
            short_exposure=0.0,
            position_count=1,
            metadata_json={},
        ),
    )
    sizing = PositionSizingDecisionRecord(
        position_sizing_decision_id="sizing-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        ticker="AAPL",
        risk_appetite="balanced",
        base_weight=0.05,
        volatility_adjusted_weight=0.04,
        liquidity_capped_weight=0.04,
        final_weight=0.04,
        final_notional=4000.0,
        applied_caps=["liquidity_cap"],
        binding_constraint="liquidity_cap",
        decision_time=now,
        metadata_json={},
    )
    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.04,
        approved_notional=4000.0,
        approved_quantity=20.0,
        portfolio_risk_snapshot_id="risk-snapshot-1",
        applied_rules=["liquidity_cap"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    repository.save_portfolio_risk_snapshot(portfolio_snapshot)
    repository.save_risk_factor_exposures(exposures)
    repository.save_position_sizing_decision(sizing)
    repository.save_risk_decision(risk_decision)

    assert session.flush_calls >= 4


def test_sqlalchemy_repository_persists_lookahead_risk_audit_fields_in_metadata():
    now = datetime(2026, 6, 13, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-lookahead-1",
        candidate_score_id=None,
        trade_classification_id=None,
        position_sizing_decision_id=None,
        ticker="NVDA",
        status="approved",
        reason_code="own_event_force_reduce",
        approved_weight=0.02,
        approved_notional=2000.0,
        approved_quantity=10.0,
        portfolio_risk_snapshot_id=None,
        applied_rules=["portfolio_risk_intent"],
        generated_hedge_action={"reason_code": "macro_high_overlay"},
        decision_time=now,
        binding_constraint="own_event_force_reduce",
        lookahead_risk_source="own_event",
        metadata_json={},
    )

    repository.save_risk_decision(risk_decision)

    stored = session.rows_by_type[RiskDecision][0]

    assert stored.metadata_json["binding_constraint"] == "own_event_force_reduce"
    assert stored.metadata_json["lookahead_risk_source"] == "own_event"
    assert stored.generated_hedge_action_json["reason_code"] == "macro_high_overlay"


def test_sqlalchemy_repository_round_trips_portfolio_risk_intent():
    now = datetime(2026, 6, 13, 12, 45, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    portfolio_snapshot = PortfolioRiskSnapshotRecord(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_appetite="balanced",
        resolver_version="v1",
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        account_equity=100000.0,
        cash_balance=50000.0,
        buying_power=100000.0,
        excess_liquidity=50000.0,
        stock_margin_requirement=1000.0,
        option_margin_requirement=0.0,
        total_margin_requirement=1000.0,
        initial_margin_requirement=1000.0,
        maintenance_margin_requirement=500.0,
        margin_requirement_source="broker_reported",
        net_exposure=10000.0,
        gross_exposure=10000.0,
        beta_adjusted_net_exposure=9000.0,
        concentration_flags=["single_name_warning"],
        metadata_json={"macro_regime": "risk_on"},
    )
    intent = PortfolioRiskIntentRecord.create(
        portfolio_risk_snapshot_id="risk-snapshot-1",
        decision_time=now,
        risk_window="1-5d",
        aggregate_risk_state="mixed_risk",
        position_actions=(
            PositionRiskActionRecord(
                ticker="NVDA",
                trade_identity="tactical_stock_trade",
                action="block_open",
                risk_source="own_event",
                severity="high",
                max_allowed_weight_override=None,
                reason_code="own_event_block",
                metadata_json={"days_until_event": 2},
            ),
        ),
        hedge_actions=(
            HedgeActionRecord(
                action="open_hedge",
                risk_source="macro",
                severity="watch",
                target_underlier="QQQ",
                target_exposure_type="broad_market",
                coverage_ratio=0.25,
                reason_code="macro_watch_overlay",
                metadata_json={},
            ),
        ),
        binding_constraints=("own_event_block", "macro_watch_overlay"),
        metadata_json={"source": "planner"},
    )

    repository.save_portfolio_risk_snapshot(portfolio_snapshot)
    repository.save_portfolio_risk_intent(intent)
    loaded = repository.load_portfolio_risk_intents(trade_date=now.date())

    assert len(loaded) == 1
    assert loaded[0].portfolio_risk_snapshot_id == str(uuid.uuid5(uuid.NAMESPACE_URL, "risk-snapshot-1"))
    assert loaded[0].position_actions[0].action == "block_open"
    assert loaded[0].hedge_actions[0].target_underlier == "QQQ"


def test_sqlalchemy_repository_save_and_load_latest_macro_snapshot_by_decision_time():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    earlier = datetime(2026, 6, 16, 11, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    repository.save_macro_snapshot(
        MacroSnapshotRecord(
            macro_snapshot_id="macro-1",
            snapshot_time=earlier,
            trade_date=earlier.date(),
            regime="balanced",
            risk_budget_multiplier=1.0,
            volatility_state="normal",
            rates_state="stable",
            liquidity_state="ample",
            blocked_strategy_tags=(),
            invalidators=(),
            source_freshness={"macro_indicator_provider": {"status": "fresh"}},
            metadata_json={"basis_note": "early snapshot"},
        )
    )
    repository.save_macro_snapshot(
        MacroSnapshotRecord(
            macro_snapshot_id="macro-2",
            snapshot_time=later,
            trade_date=later.date(),
            regime="risk_off",
            risk_budget_multiplier=0.5,
            volatility_state="elevated",
            rates_state="restrictive",
            liquidity_state="tight",
            blocked_strategy_tags=("gap_and_go_v1",),
            invalidators=("fomc_same_day",),
            source_freshness={"macro_indicator_provider": {"status": "fresh"}},
            metadata_json={"basis_note": "later snapshot"},
        )
    )

    loaded = repository.load_latest_macro_snapshot(
        trade_date=earlier.date(),
        decision_time=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert session.query(MacroSnapshot).all()
    assert loaded is not None
    assert loaded.macro_snapshot_id == str(uuid.uuid5(uuid.NAMESPACE_URL, "macro-1"))
    assert loaded.regime == "balanced"


def test_sqlalchemy_repository_filters_calendar_events_by_decision_availability():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    earlier = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 16, 15, 0, tzinfo=timezone.utc)
    repository.save_calendar_events(
        (
            CalendarEventRecord(
                calendar_event_id="calendar-1",
                event_key="earnings:NVDA:2026-06-16",
                event_type="earnings",
                ticker="NVDA",
                event_time=later,
                published_at=earlier,
                available_for_decision_at=earlier,
                title="NVIDIA earnings",
                severity_hint="high",
                source="fixture",
                metadata_json={},
            ),
            CalendarEventRecord(
                calendar_event_id="calendar-2",
                event_key="macro:fomc:2026-06-17",
                event_type="macro",
                ticker=None,
                event_time=later,
                published_at=later,
                available_for_decision_at=later,
                title="FOMC",
                severity_hint="critical",
                source="fixture",
                metadata_json={},
            ),
        )
    )

    loaded = repository.load_calendar_events(
        decision_time=datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
        ticker="NVDA",
    )

    assert len(session.query(CalendarEvent).all()) == 2
    assert [item.calendar_event_id for item in loaded] == [
        str(uuid.uuid5(uuid.NAMESPACE_URL, "calendar-1"))
    ]


def test_sqlalchemy_repository_filters_event_risk_assessments_by_decision_availability():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    earlier = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 16, 15, 0, tzinfo=timezone.utc)
    repository.save_portfolio_event_risk_assessments(
        (
            PortfolioEventRiskAssessmentRecord(
                portfolio_event_risk_assessment_id="assessment-1",
                calendar_event_id="calendar-1",
                portfolio_risk_snapshot_id=None,
                decision_time=earlier,
                available_for_decision_at=earlier,
                ticker="NVDA",
                risk_source="own_event",
                severity="high",
                event_type="earnings",
                days_until_event=1,
                affects_existing_position=True,
                affects_pending_trade=False,
                recommended_action="block_open",
                rationale="Own earnings falls inside the lookahead window.",
                metadata_json={"summary_bucket": "earnings"},
            ),
            PortfolioEventRiskAssessmentRecord(
                portfolio_event_risk_assessment_id="assessment-2",
                calendar_event_id="calendar-2",
                portfolio_risk_snapshot_id=None,
                decision_time=later,
                available_for_decision_at=later,
                ticker="NVDA",
                risk_source="macro",
                severity="watch",
                event_type="macro",
                days_until_event=2,
                affects_existing_position=True,
                affects_pending_trade=True,
                recommended_action="tighten_risk",
                rationale="Macro risk grows later in the day.",
                metadata_json={"summary_bucket": "macro"},
            ),
        )
    )

    loaded = repository.load_portfolio_event_risk_assessments(
        decision_time=datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
        ticker="NVDA",
    )

    assert len(session.query(PortfolioEventRiskAssessment).all()) == 2
    assert [item.portfolio_event_risk_assessment_id for item in loaded] == [
        str(uuid.uuid5(uuid.NAMESPACE_URL, "assessment-1"))
    ]


def test_sqlalchemy_repository_loads_decision_visible_news_in_risk_macro_context():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    earlier = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    decision_time = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 16, 14, 0, tzinfo=timezone.utc)
    visible_macro_id = uuid.uuid4()
    future_macro_id = uuid.uuid4()
    visible_event_id = uuid.uuid4()
    other_event_id = uuid.uuid4()
    future_event_id = uuid.uuid4()

    session.add(
        SocialMacroItem(
            social_macro_item_id=visible_macro_id,
            ticker="NVDA",
            category="geopolitical_news",
            source_type="news",
            source_key="geopolitical_news",
            provider="global_context",
            title="Export-control update hits semis",
            summary="Policy risk is fresh for chip names.",
            direction="negative",
            sentiment_direction="negative",
            importance_score=0.8,
            importance_label="high",
            policy_headwind_flag=True,
            policy_tailwind_flag=False,
            explicit_ticker_mention_flag=True,
            explicit_theme_mention_flag=True,
            theme_tags_json=["semiconductors"],
            company_name_mentions_json=["NVIDIA"],
            source_refs_json=[],
            dedupe_key="macro-visible",
            event_time=earlier,
            published_at=earlier,
            ingested_at=earlier,
            available_for_decision_at=earlier,
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    session.add(
        SocialMacroItem(
            social_macro_item_id=future_macro_id,
            ticker="NVDA",
            category="geopolitical_news",
            source_type="news",
            source_key="geopolitical_news",
            provider="global_context",
            title="Future policy headline",
            summary="Not available to the decision yet.",
            direction="negative",
            sentiment_direction="negative",
            importance_score=0.9,
            importance_label="high",
            policy_headwind_flag=True,
            policy_tailwind_flag=False,
            explicit_ticker_mention_flag=True,
            explicit_theme_mention_flag=True,
            theme_tags_json=["semiconductors"],
            company_name_mentions_json=["NVIDIA"],
            source_refs_json=[],
            dedupe_key="macro-future",
            event_time=later,
            published_at=later,
            ingested_at=later,
            available_for_decision_at=later,
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    session.add(
        EventNewsItem(
            event_news_item_id=visible_event_id,
            ticker="NVDA",
            source_ticker=None,
            event_type="company_specific",
            direction="negative",
            sentiment="negative",
            importance="high",
            headline="NVIDIA export restriction update",
            summary="Fresh headline raises event risk.",
            provider="alpaca",
            source_refs_json=[],
            dedupe_key="event-visible",
            event_time=earlier,
            published_at=earlier,
            ingested_at=earlier,
            available_for_decision_at=earlier,
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    session.add(
        EventNewsItem(
            event_news_item_id=other_event_id,
            ticker="AMD",
            source_ticker=None,
            event_type="company_specific",
            direction="negative",
            sentiment="negative",
            importance="high",
            headline="AMD-only headline",
            summary="Different ticker should stay out of NVDA context.",
            provider="alpaca",
            source_refs_json=[],
            dedupe_key="event-other",
            event_time=earlier,
            published_at=earlier,
            ingested_at=earlier,
            available_for_decision_at=earlier,
            raw_payload_ref=None,
            metadata_json={},
        )
    )
    session.add(
        EventNewsItem(
            event_news_item_id=future_event_id,
            ticker="NVDA",
            source_ticker=None,
            event_type="company_specific",
            direction="negative",
            sentiment="negative",
            importance="high",
            headline="Future NVIDIA headline",
            summary="Not available to the decision yet.",
            provider="alpaca",
            source_refs_json=[],
            dedupe_key="event-future",
            event_time=later,
            published_at=later,
            ingested_at=later,
            available_for_decision_at=later,
            raw_payload_ref=None,
            metadata_json={},
        )
    )

    context = repository.load_decision_available_risk_macro_context(
        trade_date=decision_time.date(),
        decision_time=decision_time,
        ticker="NVDA",
    )

    assert [item.social_macro_item_id for item in context["macro_news"]] == [str(visible_macro_id)]
    assert [item.event_news_item_id for item in context["event_news"]] == [str(visible_event_id)]


def test_sqlalchemy_repository_persists_pr6_order_execution_snapshot_and_positions():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    order = PaperOrderRecord(
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        client_order_id="2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
        trading_decision_id="decision-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=date(2026, 6, 2),
        quantity=0.01,
        limit_price=227.15,
        status="filled",
        rejection_reason=None,
        created_at=now,
    )
    execution = PaperExecutionRecord(
        paper_execution_id="execution-1",
        paper_order_id="order-1",
        broker_order_id="broker-order-1",
        ticker="AAPL",
        quantity=0.01,
        fill_price=227.15,
        trade_date=date(2026, 6, 2),
        executed_at=now,
        net_cash_effect=-2.2715,
    )
    snapshot = PortfolioSnapshot(
        as_of=now,
        cash_balance=999997.73,
        account_equity=1000000.12,
        net_liquidation_value=1000000.12,
        buying_power=1999995.46,
        excess_liquidity=999999.44,
        stock_market_value=2.27,
        option_market_value=0.0,
        stock_margin_requirement=1.14,
        option_margin_requirement=0.0,
        total_margin_requirement=1.14,
        initial_margin_requirement=1.14,
        maintenance_margin_requirement=0.68,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_reported",
        day_pnl=0.12,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json={"broker": "alpaca"},
    )
    positions = (
        StockPosition(
            ticker="AAPL",
            quantity=0.01,
            average_cost=227.15,
            market_price=227.27,
            market_value=2.27,
            trade_identity="tactical_stock_trade",
            strategy_id="relative_strength_rotation_v1",
            opened_at=now,
            updated_at=now,
            direction="long",
        ),
    )

    repository.save_paper_order(order)
    repository.save_paper_order(order)
    repository.save_paper_execution(execution)
    repository.replace_paper_positions(positions)
    repository.save_portfolio_snapshot(snapshot)

    open_positions = repository.load_paper_positions()

    assert repository.has_paper_execution("execution-1") is True
    assert len(open_positions) == 1
    assert open_positions[0].ticker == "AAPL"
    assert open_positions[0].strategy_id == "relative_strength_rotation_v1"
    assert session.flush_calls >= 4


def test_sqlalchemy_repository_closes_missing_positions_on_replace():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.replace_paper_positions(
        (
            StockPosition(
                ticker="AAPL",
                quantity=0.01,
                average_cost=227.15,
                market_price=227.27,
                market_value=2.27,
                trade_identity="tactical_stock_trade",
                strategy_id="relative_strength_rotation_v1",
                opened_at=now,
                updated_at=now,
                direction="long",
            ),
        )
    )
    repository.replace_paper_positions(())

    assert repository.load_paper_positions() == ()


def test_sqlalchemy_repository_loads_refreshable_stock_orders_and_detects_order_execution():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    refreshable_order = PaperOrderRecord(
        paper_order_id="11111111-1111-4111-8111-111111111111",
        broker_order_id="broker-order-1",
        client_order_id="2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
        trading_decision_id="22222222-2222-4222-8222-222222222222",
        risk_decision_id="33333333-3333-4333-8333-333333333333",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=now.date(),
        quantity=0.01,
        limit_price=None,
        status="accepted",
        rejection_reason=None,
        created_at=now,
    )
    filled_order = PaperOrderRecord(
        paper_order_id="44444444-4444-4444-8444-444444444444",
        broker_order_id="broker-order-2",
        client_order_id="2026-06-02:MSFT:relative_strength_rotation_v1:enter_long",
        trading_decision_id="55555555-5555-4555-8555-555555555555",
        risk_decision_id="66666666-6666-4666-8666-666666666666",
        ticker="MSFT",
        strategy_id="relative_strength_rotation_v1",
        action="enter_long",
        trade_date=now.date(),
        quantity=0.02,
        limit_price=300.0,
        status="filled",
        rejection_reason=None,
        created_at=now,
    )
    repository.save_paper_order(refreshable_order)
    repository.save_paper_order(filled_order)
    repository.save_paper_execution(
        PaperExecutionRecord(
            paper_execution_id="77777777-7777-4777-8777-777777777777",
            paper_order_id=refreshable_order.paper_order_id,
            broker_order_id="broker-order-1",
            ticker="AAPL",
            quantity=0.01,
            fill_price=227.15,
            trade_date=now.date(),
            executed_at=now,
            net_cash_effect=-2.2715,
        )
    )

    refreshable = repository.load_refreshable_paper_orders()

    assert [order.ticker for order in refreshable] == ["AAPL"]
    assert repository.has_paper_execution_for_order_id(refreshable_order.paper_order_id) is True
    assert repository.has_paper_execution_for_order_id(filled_order.paper_order_id) is False


def test_sqlalchemy_repository_persists_pr7_option_artifacts():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_option_strategy_decision(
        OptionStrategyDecisionRecord(
            option_strategy_decision_id="option-decision-1",
            trading_decision_id="decision-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            decision_action="open_option_strategy",
            option_strategy_type="put_credit_spread",
            status="ready",
            rejection_reason=None,
            strategy_id="earnings_drift_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
            underlying_price=118.0,
            expiry=date(2026, 7, 17),
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            breakevens=(108.5,),
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            earnings_date=date(2026, 6, 20),
            event_through_expiry=True,
            strategy_pairing_method="vertical_by_expiry_and_width",
            assignment_plan="close_or_roll_before_expiry_if_itm",
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            profit_target_pct=0.5,
            max_loss_rule="close_at_2x_credit",
            roll_conditions=("7_dte_if_otm",),
            close_conditions=("take_profit_50pct",),
            metadata_json={},
            created_at=now,
        )
    )
    repository.save_option_strategy_legs(
        (
            OptionStrategyLegRecord(
                option_strategy_leg_id="leg-1",
                option_strategy_decision_id="option-decision-1",
                ticker="NVDA",
                contract_symbol="NVDA260717P00110000",
                option_type="put",
                side="sell",
                quantity=1,
                ratio_qty=1,
                strike=110.0,
                expiry=date(2026, 7, 17),
                dte=45,
                delta=-0.28,
                gamma=0.02,
                theta=0.01,
                vega=-0.07,
                iv_rank=0.61,
                bid=1.4,
                ask=1.6,
                mid=1.5,
                chosen_price=1.5,
                created_at=now,
                implied_volatility=0.34,
            ),
        )
    )
    repository.save_paper_option_order(
        PaperOptionOrderRecord(
            paper_option_order_id="option-order-1",
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            option_strategy_decision_id="option-decision-1",
            broker_order_id="alpaca-option-order-1",
            client_order_id="2026-06-02:NVDA:earnings_drift_v1:open_option_strategy",
            order_class="mleg",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            action="open_option_strategy",
            trade_identity="tactical_option_trade",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=-1.5,
            status="filled",
            rejection_reason=None,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            created_at=now,
        )
    )
    repository.save_paper_option_execution(
        PaperOptionExecutionRecord(
            paper_option_execution_id="option-execution-1",
            paper_option_order_id="option-order-1",
            broker_order_id="alpaca-option-order-1",
            ticker="NVDA",
            quantity=1,
            fill_price=-1.5,
            trade_date=date(2026, 6, 2),
            executed_at=now,
            net_cash_effect=150.0,
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 7, 17),
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            metadata_json={},
        )
    )
    repository.save_option_risk_snapshot(
        OptionRiskSnapshotRecord(
            option_risk_snapshot_id="risk-snapshot-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            option_strategy_type="put_credit_spread",
            underlying_price=118.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            worst_case_assignment_notional=11_000.0,
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            risk_status="approved",
            reason_code="within_limits",
            created_at=now,
            metadata_json={},
        )
    )
    repository.save_risk_hedge_decision(
        RiskHedgeDecisionRecord.create(
            risk_decision_id="risk-1",
            ticker="QQQ",
            action="open_option_strategy",
            option_strategy_type="long_put",
            rationale="risk_manager_generated_overlay",
            hedge_cost=250.0,
            protected_notional=20_000.0,
        )
    )

    assert repository.has_paper_option_execution("option-execution-1") is True
    assert repository.load_paper_option_positions()[0].ticker == "NVDA"
    persisted_leg = session.query(OptionStrategyLeg).one_or_none()
    assert persisted_leg is not None
    assert persisted_leg.contract_symbol == "NVDA260717P00110000"
    assert persisted_leg.ratio_qty == 1
    assert persisted_leg.implied_volatility == Decimal("0.34")
    persisted_order = session.query(PaperOptionOrder).one_or_none()
    assert persisted_order is not None
    assert persisted_order.client_order_id == "2026-06-02:NVDA:earnings_drift_v1:open_option_strategy"
    assert persisted_order.broker_order_id == "alpaca-option-order-1"
    assert persisted_order.order_class == "mleg"
    persisted_execution = session.query(PaperOptionExecution).one_or_none()
    assert persisted_execution is not None
    assert persisted_execution.broker_order_id == "alpaca-option-order-1"


def test_sqlalchemy_repository_preserves_null_option_strategy_decision_for_broker_only_position():
    now = datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="broker-only-option-position",
            option_strategy_decision_id=None,
            ticker="NVDA",
            strategy_id="broker_option_position",
            option_strategy_type="broker_option_position",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 7, 17),
            max_loss=1.0,
            margin_requirement=1.0,
            buying_power_effect=1.0,
            assignment_notional=0.0,
            metadata_json={
                "broker_leg_refs": [
                    {
                        "contract_symbol": "NVDA260717P00110000",
                        "position_intent": "broker_position",
                    }
                ]
            },
        )
    )

    loaded_position = repository.load_paper_option_positions()[0]

    assert loaded_position.option_strategy_decision_id is None


class _BrokerStub:
    def submit_order(self, request: Any) -> Any:
        return type(
            "Order",
            (),
            {
                "paper_order_id": "paper-order-1",
                "broker_order_id": "broker-order-1",
                "client_order_id": "2026-06-02:AAPL:relative_strength_rotation_v1:enter_long",
                "trading_decision_id": request.trading_decision_id,
                "risk_decision_id": request.risk_decision_id,
                "ticker": request.ticker,
                "strategy_id": request.strategy_id,
                "action": request.action,
                "trade_date": request.trade_date,
                "quantity": request.quantity,
                "limit_price": None,
                "status": "filled",
                "rejection_reason": None,
                "created_at": datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            },
        )()

    def find_execution_by_order_id(self, paper_order_id: str) -> Any:
        return PaperExecutionRecord(
            paper_execution_id="execution-1",
            paper_order_id=paper_order_id,
            broker_order_id="broker-order-1",
            ticker="AAPL",
            quantity=0.01,
            fill_price=227.15,
            trade_date=date(2026, 6, 2),
            executed_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            net_cash_effect=-2.2715,
        )

    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999997.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999995.46",
            "long_market_value": "2.27",
            "initial_margin": "1.14",
            "maintenance_margin": "0.68",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ]


def test_paper_execution_workflow_persists_into_sqlalchemy_repository():
    now = datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    workflow = PaperExecutionWorkflow(
        repository=repository,
        broker=_BrokerStub(),
        manual_request_service=ManualTickerRequestService(now=lambda: now),
    )

    trading_decision = TradingDecisionRecord(
        trading_decision_id="decision-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        risk_decision_id="risk-1",
        ticker="AAPL",
        decision="enter_long",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        selection_source="scanner",
        manual_request_id=None,
        confidence=0.78,
        target_weight=0.05,
        approved_weight=0.04,
        max_loss_pct=0.02,
        time_horizon="2w-3m",
        thesis="Relative strength remains intact.",
        invalidators=["trend break"],
        prompt_template=object(),
        prompt_run=object(),
        usage_events=[],
        decision_time=now,
        available_for_decision_at=now,
        paper_trade_authorized=True,
        metadata_json={"paper_trade_authorized": True},
    )
    risk_decision = RiskDecisionRecord(
        risk_decision_id="risk-1",
        candidate_score_id="candidate-1",
        trade_classification_id="classification-1",
        position_sizing_decision_id="sizing-1",
        ticker="AAPL",
        status="approved",
        reason_code="within_limits",
        approved_weight=0.000002,
        approved_notional=2.27,
        approved_quantity=0.01,
        portfolio_risk_snapshot_id="portfolio-risk-1",
        applied_rules=["single_name_limit_ok"],
        generated_hedge_action=None,
        decision_time=now,
        metadata_json={},
    )

    result = workflow.run(
        trading_decisions=(trading_decision,),
        risk_decisions=(risk_decision,),
        trade_date=now,
    )

    assert len(result.paper_orders) == 1
    assert repository.has_paper_execution("execution-1") is True
    assert repository.load_paper_positions()[0].ticker == "AAPL"


def test_load_intraday_request_contexts_includes_option_execution_metadata():
    now = datetime(2026, 6, 4, 16, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_trading_decision(
        TradingDecisionRecord(
            trading_decision_id="qqq-option-decision",
            candidate_score_id="qqq-candidate",
            trade_classification_id="qqq-classification",
            risk_decision_id="qqq-risk",
            ticker="QQQ",
            decision="open_option_strategy",
            strategy_id="risk_manager_hedge_overlay_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_directional_option",
            expression_bucket_version="v1",
            trade_identity="risk_hedge_overlay",
            instrument_type="option",
            selection_source="risk_manager",
            manual_request_id=None,
            confidence=0.55,
            target_weight=0.0,
            approved_weight=0.0,
            max_loss_pct=0.02,
            time_horizon="1w-4w",
            thesis="Macro hedge remains active.",
            invalidators=["macro risk normalized"],
            prompt_template=object(),
            prompt_run=object(),
            usage_events=[],
            decision_time=now,
            available_for_decision_at=now,
            paper_trade_authorized=True,
            metadata_json={
                "paper_trade_authorized": True,
                "option_strategy": {
                    "option_strategy_type": "long_put",
                    "underlying_price": 500.0,
                    "net_debit_or_credit": 3.2,
                },
            },
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="qqq-open-position",
            option_strategy_decision_id="qqq-option-strategy",
            ticker="QQQ",
            strategy_id="risk_manager_hedge_overlay_v1",
            option_strategy_type="long_put",
            trade_identity="risk_hedge_overlay",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=now.date(),
            max_loss=320.0,
            margin_requirement=320.0,
            buying_power_effect=320.0,
            assignment_notional=50000.0,
            metadata_json={"protected_notional": 25000.0},
        )
    )

    expected_position_id = repository.load_paper_option_positions()[0].paper_option_position_id

    context = repository.load_intraday_request_contexts(
        tickers=("QQQ",),
        trade_date=now.date(),
    )["QQQ"]

    assert context.instrument_type == "option"
    assert context.trade_identity == "risk_hedge_overlay"
    assert context.metadata_json["option_strategy"]["option_strategy_type"] == "long_put"
    assert context.metadata_json["option_strategy_type"] == "long_put"
    assert context.metadata_json["paper_option_position_id"] == expected_position_id


def test_sqlalchemy_repository_loads_active_and_shadow_learning_factors():
    now = datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc)
    reflection_id = uuid.uuid4()
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=reflection_id,
            trade_date=now.date(),
            status="succeeded",
            portfolio_summary_json={},
            reflection_json={},
            strategy_proposal_hints_json=[],
            metadata_json={},
            created_at=now,
        )
    ]
    session.rows_by_type[LearningFactor] = [
        SimpleNamespace(
            learning_factor_id=uuid.uuid4(),
            factor_key="lf-active",
            daily_reflection_id=reflection_id,
            trade_date=now.date(),
            title="Raise score",
            factor_type="candidate_filter",
            scope="strategy",
            status="active",
            strategy_id="relative_strength_rotation_v1",
            condition="relative_volume > 1.5",
            recommendation="Favor the setup.",
            confidence=Decimal("0.72"),
            activation_policy="shadow_promoted",
            effect_tags_json=["increase_score"],
            evidence_json=["worked recently"],
            metadata_json={},
            created_at=now,
        ),
        SimpleNamespace(
            learning_factor_id=uuid.uuid4(),
            factor_key="lf-shadow",
            daily_reflection_id=reflection_id,
            trade_date=now.date(),
            title="Reduce exposure",
            factor_type="risk_control",
            scope="risk",
            status="shadow",
            strategy_id=None,
            condition="event cluster",
            recommendation="Observe for now.",
            confidence=Decimal("0.61"),
            activation_policy="shadow",
            effect_tags_json=["reduce_exposure"],
            evidence_json=["one eventful session"],
            metadata_json={},
            created_at=now,
        ),
        SimpleNamespace(
            learning_factor_id=uuid.uuid4(),
            factor_key="lf-candidate",
            daily_reflection_id=reflection_id,
            trade_date=now.date(),
            title="Ignore",
            factor_type="candidate_filter",
            scope="strategy",
            status="candidate",
            strategy_id="relative_strength_rotation_v1",
            condition="unused",
            recommendation="Should not load.",
            confidence=Decimal("0.55"),
            activation_policy="candidate",
            effect_tags_json=[],
            evidence_json=[],
            metadata_json={},
            created_at=now,
        ),
    ]

    rows = repository.load_active_learning_factors()

    assert [row.factor_key for row in rows] == ["lf-active", "lf-shadow"]
    assert all(isinstance(row, LearningFactorRecord) for row in rows)


def test_sqlalchemy_repository_save_daily_reflection_updates_existing_trade_date():
    trade_date = date(2026, 6, 30)
    now = datetime(2026, 6, 30, 20, 20, tzinfo=timezone.utc)
    existing_id = uuid.uuid4()
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=existing_id,
            trade_date=trade_date,
            prompt_run_id=None,
            status="fallback",
            portfolio_summary_json={"day_pnl": 100.0},
            reflection_json={"fallback_action": "reflection_failed"},
            strategy_proposal_hints_json=[],
            metadata_json={"fallback_action": "reflection_failed"},
            created_at=now,
        )
    ]

    repository.save_daily_reflection(
        DailyReflectionRecord(
            daily_reflection_id=str(uuid.uuid4()),
            trade_date=trade_date,
            status="succeeded",
            prompt_template=None,
            prompt_run=PromptRunRecord(
                pipeline_name="reflection",
                rendered_prompt_hash="hash",
                rendered_prompt_redacted="prompt",
                input_context_json={},
                raw_output_text="{}",
                parsed_output_json={},
                parse_status="succeeded",
                validation_errors_json=[],
                fallback_action=None,
                error_message=None,
            ),
            usage_events=[],
            reflection_json={"what_worked": ["fixed"]},
            strategy_proposal_hints=(),
            metadata_json={"portfolio_outcome": {"day_pnl": 120.0}},
        )
    )

    rows = session.rows_by_type[DailyReflection]
    assert len(rows) == 1
    assert rows[0].daily_reflection_id == existing_id
    assert rows[0].status == "succeeded"
    assert rows[0].reflection_json == {"what_worked": ["fixed"]}


def test_sqlalchemy_repository_save_learning_factor_maps_retried_reflection_to_existing_trade_date():
    trade_date = date(2026, 6, 30)
    existing_id = uuid.uuid4()
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=existing_id,
            trade_date=trade_date,
            prompt_run_id=None,
            status="succeeded",
            portfolio_summary_json={},
            reflection_json={},
            strategy_proposal_hints_json=[],
            metadata_json={},
            created_at=datetime(2026, 6, 30, 20, 20, tzinfo=timezone.utc),
        )
    ]
    generated_retry_id = uuid.uuid4()

    repository.save_learning_factor(
        LearningFactorRecord(
            learning_factor_id=str(uuid.uuid4()),
            factor_key="lf-2026-06-30-01",
            trade_date=trade_date,
            title="Retry-safe factor",
            factor_type="observation",
            scope="portfolio",
            status="observation",
            strategy_id=None,
            condition="retry",
            recommendation="observe",
            confidence=0.5,
            activation_policy="observation",
            effect_tags=(),
            evidence=(),
            source_daily_reflection_id=str(generated_retry_id),
            metadata_json={},
        )
    )

    factors = session.rows_by_type[LearningFactor]
    assert len(factors) == 1
    assert factors[0].daily_reflection_id == existing_id


def test_sqlalchemy_repository_save_learning_factor_resolves_reflection_before_autoflush():
    trade_date = date(2026, 6, 30)
    existing_id = uuid.uuid4()
    session = _AutoflushFakeSession()
    repository = SqlAlchemyTradingRepository(session)
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=existing_id,
            trade_date=trade_date,
            prompt_run_id=None,
            status="succeeded",
            portfolio_summary_json={},
            reflection_json={},
            strategy_proposal_hints_json=[],
            metadata_json={},
            created_at=datetime(2026, 6, 30, 20, 20, tzinfo=timezone.utc),
        )
    ]

    repository.save_learning_factor(
        LearningFactorRecord(
            learning_factor_id=str(uuid.uuid4()),
            factor_key="lf-2026-06-30-autoflush",
            trade_date=trade_date,
            title="Autoflush-safe factor",
            factor_type="observation",
            scope="portfolio",
            status="observation",
            strategy_id=None,
            condition="retry",
            recommendation="observe",
            confidence=0.5,
            activation_policy="observation",
            effect_tags=(),
            evidence=(),
            source_daily_reflection_id=str(uuid.uuid4()),
            metadata_json={},
        )
    )

    factors = session.rows_by_type[LearningFactor]
    assert len(factors) == 1
    assert factors[0].title == "Autoflush-safe factor"
    assert factors[0].daily_reflection_id == existing_id


def test_sqlalchemy_repository_load_reflection_inputs_matches_expected_result_set_within_utc_day():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    trade_date = date(2026, 6, 4)
    window = (
        datetime(2026, 6, 4, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc),
    )
    risk_snapshot_id = uuid.uuid4()
    session.rows_by_type[PortfolioSnapshotModel] = [
        SimpleNamespace(
            snapshot_time=datetime(2026, 6, 4, 15, 45, tzinfo=timezone.utc),
            cash_balance=Decimal("50000"),
            account_equity=Decimal("100250"),
            net_liquidation_value=Decimal("100250"),
            buying_power=Decimal("150000"),
            day_pnl=Decimal("250"),
            realized_pnl=Decimal("125"),
            unrealized_pnl=Decimal("125"),
            metadata_json={"window": "in"},
        ),
        SimpleNamespace(
            snapshot_time=datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc),
            cash_balance=Decimal("50010"),
            account_equity=Decimal("100260"),
            net_liquidation_value=Decimal("100260"),
            buying_power=Decimal("150010"),
            day_pnl=Decimal("260"),
            realized_pnl=Decimal("130"),
            unrealized_pnl=Decimal("130"),
            metadata_json={"window": "out"},
        ),
    ]
    session.rows_by_type[PortfolioRiskSnapshot] = [
        SimpleNamespace(
            portfolio_risk_snapshot_id=risk_snapshot_id,
            decision_time=datetime(2026, 6, 4, 15, 46, tzinfo=timezone.utc),
            account_equity=Decimal("100250"),
            cash_balance=Decimal("50000"),
            buying_power=Decimal("150000"),
            net_exposure=Decimal("10000"),
            gross_exposure=Decimal("15000"),
            metadata_json={"window": "in"},
        ),
        SimpleNamespace(
            portfolio_risk_snapshot_id=uuid.uuid4(),
            decision_time=datetime(2026, 6, 5, 0, 1, tzinfo=timezone.utc),
            account_equity=Decimal("100260"),
            cash_balance=Decimal("50010"),
            buying_power=Decimal("150010"),
            net_exposure=Decimal("10010"),
            gross_exposure=Decimal("15010"),
            metadata_json={"window": "out"},
        ),
    ]
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            trade_date=trade_date,
            created_at=datetime(2026, 6, 4, 21, 0, tzinfo=timezone.utc),
            metadata_json={"learning_factors_used": [{"factor_key": "lf-in"}]},
        ),
        SimpleNamespace(
            trade_date=date(2026, 6, 5),
            created_at=datetime(2026, 6, 5, 21, 0, tzinfo=timezone.utc),
            metadata_json={"learning_factors_used": [{"factor_key": "lf-out"}]},
        ),
    ]
    session.rows_by_type[RiskHedgeDecision] = [
        SimpleNamespace(
            ticker="QQQ",
            action="adjust_hedge",
            option_strategy_type="long_put",
            rationale="protect gains",
            hedge_cost=Decimal("80"),
            protected_notional=Decimal("12000"),
            metadata_json={"generated_hedge_action": {"protected_exposure_basis": "net_exposure"}},
            created_at=datetime(2026, 6, 4, 19, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="SPY",
            action="open_hedge",
            option_strategy_type="long_put",
            rationale="too late",
            hedge_cost=Decimal("90"),
            protected_notional=Decimal("13000"),
            metadata_json={"generated_hedge_action": {"protected_exposure_basis": "gross_exposure"}},
            created_at=datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[CandidateScore] = [
        SimpleNamespace(
            ticker="AAPL",
            strategy_id="gap_reclaim_v1",
            strategy_version="v1",
            candidate_score=Decimal("0.77"),
            selection_source="scanner",
            manual_request_id=None,
            decision_time=datetime(2026, 6, 4, 15, 0, tzinfo=timezone.utc),
            rejection_reason="risk_limit",
        ),
        SimpleNamespace(
            ticker="MSFT",
            strategy_id="gap_reclaim_v1",
            strategy_version="v1",
            candidate_score=Decimal("0.66"),
            selection_source="scanner",
            manual_request_id=None,
            decision_time=datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc),
            rejection_reason="too_late",
        ),
    ]
    session.rows_by_type[ManualTickerRequest] = [
        SimpleNamespace(
            ticker="NVDA",
            mode="review_only",
            status="active",
            latest_result_status="queued",
            created_at=datetime(2026, 6, 4, 15, 30, tzinfo=timezone.utc),
            last_evaluated_at=None,
        ),
        SimpleNamespace(
            ticker="AMD",
            mode="review_only",
            status="active",
            latest_result_status="queued",
            created_at=datetime(2026, 6, 5, 0, 20, tzinfo=timezone.utc),
            last_evaluated_at=None,
        ),
    ]
    session.rows_by_type[TradingDecision] = [
        SimpleNamespace(
            ticker="AAPL",
            decision="enter_long",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            instrument_type="stock",
            selection_source="scanner",
            confidence=Decimal("0.74"),
            target_weight=Decimal("0.04"),
            approved_weight=Decimal("0.04"),
            key_drivers_json=["relative_strength"],
            counterarguments_json=[],
            invalidators_json=[],
            metadata_json={},
            decision_time=datetime(2026, 6, 4, 15, 31, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="NVDA",
            decision="no_trade",
            strategy_id="gap_reclaim_v1",
            trade_identity="watch_only",
            instrument_type="watch",
            selection_source="scanner",
            confidence=Decimal("0.55"),
            target_weight=Decimal("0"),
            approved_weight=Decimal("0"),
            key_drivers_json=[],
            counterarguments_json=[],
            invalidators_json=[],
            metadata_json={},
            decision_time=datetime(2026, 6, 4, 15, 32, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            decision="enter_long",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            instrument_type="stock",
            selection_source="scanner",
            confidence=Decimal("0.71"),
            target_weight=Decimal("0.03"),
            approved_weight=Decimal("0.03"),
            key_drivers_json=[],
            counterarguments_json=[],
            invalidators_json=[],
            metadata_json={},
            decision_time=datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[NewsAlert] = [
        SimpleNamespace(
            ticker="AAPL",
            alert_type="earnings",
            severity="high",
            sentiment="positive",
            headline="In window",
            summary="summary",
            action_required=True,
            published_at=datetime(2026, 6, 4, 15, 33, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 4, 15, 34, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            alert_type="earnings",
            severity="high",
            sentiment="positive",
            headline="Out of window",
            summary="summary",
            action_required=True,
            published_at=datetime(2026, 6, 5, 0, 33, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 5, 0, 34, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[IntradayRebalanceDecision] = [
        SimpleNamespace(
            ticker="AAPL",
            action="exit",
            status="approved",
            reason_code="protect_gains",
            confidence=Decimal("0.81"),
            decision_time=datetime(2026, 6, 4, 15, 35, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            action="exit",
            status="approved",
            reason_code="too_late",
            confidence=Decimal("0.70"),
            decision_time=datetime(2026, 6, 5, 0, 35, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[PaperOrder] = [
        SimpleNamespace(
            ticker="AAPL",
            action="buy",
            quantity=Decimal("10"),
            order_price=Decimal("200"),
            status="filled",
            trade_date=trade_date,
            created_at=datetime(2026, 6, 4, 15, 36, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            action="buy",
            quantity=Decimal("5"),
            order_price=Decimal("400"),
            status="filled",
            trade_date=date(2026, 6, 5),
            created_at=datetime(2026, 6, 5, 0, 36, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[PaperExecution] = [
        SimpleNamespace(
            ticker="AAPL",
            quantity=Decimal("10"),
            fill_price=Decimal("201"),
            trade_date=trade_date,
            executed_at=datetime(2026, 6, 4, 15, 37, tzinfo=timezone.utc),
            net_cash_effect=Decimal("-2010"),
        ),
        SimpleNamespace(
            ticker="MSFT",
            quantity=Decimal("5"),
            fill_price=Decimal("401"),
            trade_date=date(2026, 6, 5),
            executed_at=datetime(2026, 6, 5, 0, 37, tzinfo=timezone.utc),
            net_cash_effect=Decimal("-2005"),
        ),
    ]
    session.rows_by_type[RiskFactorExposure] = [
        SimpleNamespace(
            portfolio_risk_snapshot_id=risk_snapshot_id,
            factor_type="sector",
            factor_value="technology",
            gross_exposure=Decimal("10000"),
            net_exposure=Decimal("9000"),
            metadata_json={},
        ),
        SimpleNamespace(
            portfolio_risk_snapshot_id=uuid.uuid4(),
            factor_type="sector",
            factor_value="financials",
            gross_exposure=Decimal("2000"),
            net_exposure=Decimal("1000"),
            metadata_json={},
        ),
    ]
    session.rows_by_type[CandidateOutcomeEvaluation] = [
        SimpleNamespace(
            ticker="AAPL",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            evaluation_status="final",
            candidate_return=Decimal("0.03"),
            alpha=Decimal("0.02"),
            benchmark_returns_json={"QQQ": 0.01},
            decision_time=datetime(2026, 6, 4, 15, 38, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            evaluation_status="final",
            candidate_return=Decimal("0.01"),
            alpha=Decimal("0.00"),
            benchmark_returns_json={"QQQ": 0.01},
            decision_time=datetime(2026, 6, 5, 0, 38, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[OptionStrategyDecision] = [
        SimpleNamespace(
            ticker="AAPL",
            option_strategy_type="long_call",
            status="ready",
            decision_action="open_option_strategy",
            created_at=datetime(2026, 6, 4, 15, 39, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            option_strategy_type="long_call",
            status="ready",
            decision_action="open_option_strategy",
            created_at=datetime(2026, 6, 5, 0, 39, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[PaperOptionPositionModel] = [
        SimpleNamespace(
            ticker="AAPL",
            option_strategy_type="long_call",
            quantity=1,
            status="open",
            opened_at=datetime(2026, 6, 4, 15, 40, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            option_strategy_type="long_call",
            quantity=1,
            status="open",
            opened_at=datetime(2026, 6, 5, 0, 40, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[OptionRiskSnapshot] = [
        SimpleNamespace(
            ticker="AAPL",
            option_strategy_type="long_call",
            risk_status="approved",
            reason_code="within_limits",
            created_at=datetime(2026, 6, 4, 15, 41, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="MSFT",
            option_strategy_type="long_call",
            risk_status="approved",
            reason_code="within_limits",
            created_at=datetime(2026, 6, 5, 0, 41, tzinfo=timezone.utc),
        ),
    ]

    payload = repository.load_reflection_inputs(trade_date=trade_date, window=window)

    assert payload["portfolio_outcome"]["snapshot_time"] == "2026-06-04T15:45:00+00:00"
    assert [row["ticker"] for row in payload["strategy_candidates"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["manual_ticker_requests"]] == ["NVDA"]
    assert [row["ticker"] for row in payload["trading_decisions"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["rejected_decisions"]] == ["NVDA"]
    assert [row["ticker"] for row in payload["intraday_news_alerts"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["intraday_rebalance_decisions"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["paper_orders"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["paper_executions"]] == ["AAPL"]
    assert [row["factor_value"] for row in payload["risk_factor_exposures"]] == ["technology"]
    assert [row["ticker"] for row in payload["candidate_outcome_evaluations"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["paper_option_decisions"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["paper_option_positions"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["option_risk_snapshots"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["risk_hedge_overlays"]] == ["QQQ"]
    assert payload["learning_factors_used"] == ({"factor_key": "lf-in"},)


def test_sqlalchemy_repository_load_reflection_inputs_includes_late_local_day_rows():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    trade_date = date(2026, 6, 4)
    window = local_day_bounds_utc(trade_date, "America/New_York")
    risk_snapshot_id = uuid.uuid4()
    late_row_time = datetime(2026, 6, 5, 1, 30, tzinfo=timezone.utc)
    session.rows_by_type[PortfolioSnapshotModel] = [
        SimpleNamespace(
            snapshot_time=late_row_time,
            cash_balance=Decimal("50000"),
            account_equity=Decimal("100250"),
            net_liquidation_value=Decimal("100250"),
            buying_power=Decimal("150000"),
            day_pnl=Decimal("250"),
            realized_pnl=Decimal("125"),
            unrealized_pnl=Decimal("125"),
            metadata_json={},
        )
    ]
    session.rows_by_type[PortfolioRiskSnapshot] = [
        SimpleNamespace(
            portfolio_risk_snapshot_id=risk_snapshot_id,
            decision_time=late_row_time,
            account_equity=Decimal("100250"),
            cash_balance=Decimal("50000"),
            buying_power=Decimal("150000"),
            net_exposure=Decimal("10000"),
            gross_exposure=Decimal("15000"),
            metadata_json={},
        )
    ]
    session.rows_by_type[TradingDecision] = [
        SimpleNamespace(
            ticker="AAPL",
            decision="enter_long",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            instrument_type="stock",
            selection_source="scanner",
            confidence=Decimal("0.74"),
            target_weight=Decimal("0.04"),
            approved_weight=Decimal("0.04"),
            key_drivers_json=["relative_strength"],
            counterarguments_json=[],
            invalidators_json=[],
            metadata_json={},
            decision_time=late_row_time,
        )
    ]

    payload = repository.load_reflection_inputs(trade_date=trade_date, window=window)

    assert payload["portfolio_outcome"] is not None
    assert [row["ticker"] for row in payload["trading_decisions"]] == ["AAPL"]
    assert payload["portfolio_snapshots"][0]["snapshot_time"] == late_row_time.isoformat()


def test_sqlalchemy_repository_load_reflection_inputs_adds_long_horizon_context():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    trade_date = date(2026, 6, 30)
    window = (
        datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
    )
    current_reflection_id = uuid.uuid4()
    prior_reflection_id = uuid.uuid4()
    old_reflection_id = uuid.uuid4()
    session.rows_by_type[CandidateOutcomeEvaluation] = [
        SimpleNamespace(
            ticker="TODAY",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            evaluation_status="final",
            candidate_return=Decimal("0.03"),
            alpha=Decimal("0.02"),
            benchmark_returns_json={"QQQ": 0.01},
            decision_time=datetime(2026, 6, 30, 15, 30, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="PRIOR_IN_WINDOW",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            evaluation_status="final",
            candidate_return=Decimal("0.04"),
            alpha=Decimal("0.03"),
            benchmark_returns_json={"QQQ": 0.01},
            decision_time=datetime(2026, 6, 20, 15, 30, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="OLDER_THAN_LOOKBACK",
            strategy_id="gap_reclaim_v1",
            trade_identity="tactical_stock_trade",
            evaluation_status="final",
            candidate_return=Decimal("0.05"),
            alpha=Decimal("0.04"),
            benchmark_returns_json={"QQQ": 0.01},
            decision_time=datetime(2026, 4, 15, 15, 30, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=current_reflection_id,
            trade_date=trade_date,
            status="succeeded",
            reflection_json={"what_worked": ["today"]},
            strategy_proposal_hints_json=[],
            metadata_json={"learning_factors_used": []},
            created_at=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            daily_reflection_id=prior_reflection_id,
            trade_date=date(2026, 6, 20),
            status="succeeded",
            reflection_json={"what_failed": ["single-day chase"]},
            strategy_proposal_hints_json=[{"title": "gap context"}],
            metadata_json={},
            created_at=datetime(2026, 6, 20, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            daily_reflection_id=old_reflection_id,
            trade_date=date(2026, 4, 15),
            status="succeeded",
            reflection_json={"what_failed": ["old"]},
            strategy_proposal_hints_json=[],
            metadata_json={},
            created_at=datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc),
        ),
    ]

    payload = repository.load_reflection_inputs(trade_date=trade_date, window=window)

    assert [row["ticker"] for row in payload["candidate_outcome_evaluations"]] == ["TODAY"]
    assert [row["ticker"] for row in payload["historical_outcome_context"]] == ["PRIOR_IN_WINDOW"]
    assert payload["prior_reflection_context"][0]["daily_reflection_id"] == str(prior_reflection_id)
    assert payload["prior_reflection_context"][0]["trade_date"] == "2026-06-20"
    assert payload["prior_reflection_context"][0]["what_failed"] == ["single-day chase"]


def test_sqlalchemy_repository_load_strategy_evolution_inputs_uses_trailing_window():
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)
    trade_date = date(2026, 6, 30)
    current_reflection_id = uuid.uuid4()
    prior_reflection_id = uuid.uuid4()
    old_reflection_id = uuid.uuid4()
    current_factor_id = uuid.uuid4()
    prior_factor_id = uuid.uuid4()
    old_factor_id = uuid.uuid4()
    session.rows_by_type[DailyReflection] = [
        SimpleNamespace(
            daily_reflection_id=prior_reflection_id,
            trade_date=date(2026, 6, 20),
            prompt_run_id=None,
            status="succeeded",
            reflection_json={"what_worked": ["prior"]},
            strategy_proposal_hints_json=[{"title": "prior hint"}],
            metadata_json={},
            created_at=datetime(2026, 6, 20, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            daily_reflection_id=current_reflection_id,
            trade_date=trade_date,
            prompt_run_id=None,
            status="succeeded",
            reflection_json={"what_worked": ["current"]},
            strategy_proposal_hints_json=[{"title": "current hint"}],
            metadata_json={},
            created_at=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            daily_reflection_id=old_reflection_id,
            trade_date=date(2026, 4, 15),
            prompt_run_id=None,
            status="succeeded",
            reflection_json={"what_worked": ["old"]},
            strategy_proposal_hints_json=[{"title": "old hint"}],
            metadata_json={},
            created_at=datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[LearningFactor] = [
        SimpleNamespace(
            learning_factor_id=current_factor_id,
            factor_key="lf-current",
            daily_reflection_id=current_reflection_id,
            trade_date=trade_date,
            title="Current factor",
            factor_type="candidate_filter",
            scope="strategy",
            status="candidate",
            strategy_id="gap_reclaim_v1",
            condition="current",
            recommendation="observe",
            confidence=Decimal("0.65"),
            activation_policy="candidate",
            effect_tags_json=[],
            evidence_json=[],
            metadata_json={},
            created_at=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            learning_factor_id=prior_factor_id,
            factor_key="lf-prior",
            daily_reflection_id=prior_reflection_id,
            trade_date=date(2026, 6, 20),
            title="Prior factor",
            factor_type="candidate_filter",
            scope="strategy",
            status="observation",
            strategy_id="gap_reclaim_v1",
            condition="prior",
            recommendation="observe",
            confidence=Decimal("0.62"),
            activation_policy="observation",
            effect_tags_json=[],
            evidence_json=[],
            metadata_json={},
            created_at=datetime(2026, 6, 20, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            learning_factor_id=old_factor_id,
            factor_key="lf-old",
            daily_reflection_id=old_reflection_id,
            trade_date=date(2026, 4, 15),
            title="Old factor",
            factor_type="candidate_filter",
            scope="strategy",
            status="candidate",
            strategy_id="gap_reclaim_v1",
            condition="old",
            recommendation="observe",
            confidence=Decimal("0.61"),
            activation_policy="candidate",
            effect_tags_json=[],
            evidence_json=[],
            metadata_json={},
            created_at=datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[CandidateScore] = [
        SimpleNamespace(
            ticker="TODAY_REJECT",
            strategy_id="gap_reclaim_v1",
            strategy_version="v1",
            rejection_reason="risk_limit",
            selection_source="scanner",
            selection_reason="current reject",
            core_signal_evidence_json={},
            risk_tags_json=[],
            decision_time=datetime(2026, 6, 30, 15, 30, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="PRIOR_REJECT",
            strategy_id="gap_reclaim_v1",
            strategy_version="v1",
            rejection_reason="late_confirmation",
            selection_source="scanner",
            selection_reason="prior reject",
            core_signal_evidence_json={},
            risk_tags_json=[],
            decision_time=datetime(2026, 6, 20, 15, 30, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ticker="OLD_REJECT",
            strategy_id="gap_reclaim_v1",
            strategy_version="v1",
            rejection_reason="old",
            selection_source="scanner",
            selection_reason="old reject",
            core_signal_evidence_json={},
            risk_tags_json=[],
            decision_time=datetime(2026, 4, 15, 15, 30, tzinfo=timezone.utc),
        ),
    ]
    session.rows_by_type[CandidateOutcomeEvaluation] = [
        _candidate_outcome_row("TODAY", "outcome-current", datetime(2026, 6, 30, 15, 30, tzinfo=timezone.utc)),
        _candidate_outcome_row("PRIOR_IN_WINDOW", "outcome-prior", datetime(2026, 6, 20, 15, 30, tzinfo=timezone.utc)),
        _candidate_outcome_row("OLDER_THAN_LOOKBACK", "outcome-old", datetime(2026, 4, 15, 15, 30, tzinfo=timezone.utc)),
    ]

    payload = repository.load_strategy_evolution_inputs(trade_date=trade_date)

    assert [row.daily_reflection_id for row in payload["daily_reflections"]] == [
        str(current_reflection_id),
        str(prior_reflection_id),
    ]
    assert {row.factor_key for row in payload["learning_factors"]} == {"lf-current", "lf-prior"}
    assert {row.ticker for row in payload["candidate_outcome_evaluations"]} == {"TODAY", "PRIOR_IN_WINDOW"}
    assert {row["ticker"] for row in payload["rejected_candidates"]} == {"TODAY_REJECT", "PRIOR_REJECT"}


def _candidate_outcome_row(ticker: str, outcome_id: str, decision_time: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_outcome_evaluation_id=uuid.uuid5(uuid.NAMESPACE_DNS, outcome_id),
        historical_replay_run_id=None,
        candidate_score_id=None,
        trade_classification_id=None,
        ticker=ticker,
        strategy_id="gap_reclaim_v1",
        strategy_version="v1",
        expression_bucket_id="stock",
        trade_identity="tactical_stock_trade",
        direction="long",
        catalyst_type="earnings",
        confidence_bucket="gap_reclaim_v1|stock|tactical_stock_trade|long|earnings",
        decision_time=decision_time,
        horizon_start_at=decision_time,
        horizon_end_at=decision_time,
        evaluation_status="final",
        candidate_return=Decimal("0.03"),
        benchmark_returns_json={"QQQ": 0.01},
        peer_basket_id=None,
        peer_basket_return=None,
        alpha=Decimal("0.02"),
        max_favorable_excursion=Decimal("0.04"),
        max_adverse_excursion=Decimal("-0.01"),
        regime="neutral",
        sector_theme="semis",
        metadata_json={},
    )
