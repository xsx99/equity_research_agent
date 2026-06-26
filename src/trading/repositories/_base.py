"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from src.db.models.trading import (
    CalendarEvent,
    CandidateScore,
    CandidateOutcomeEvaluation,
    DailyReflection,
    EventNewsItem,
    IntradayRebalanceDecision,
    IntradaySignalScan,
    IntradaySignalSnapshot,
    LearningFactor,
    MacroSnapshot,
    NewsAlert,
    ManualTickerRequest,
    OptionRiskSnapshot,
    OptionStrategyDecision,
    OptionStrategyLeg,
    PaperExecution,
    PaperOptionExecution,
    PaperOptionOrder,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PaperPosition,
    PortfolioEventRiskAssessment,
    PortfolioRiskIntent,
    PortfolioRiskSnapshot,
    PortfolioSnapshot as PortfolioSnapshotModel,
    PositionSizingDecision,
    RiskDecision,
    RiskFactorExposure,
    RiskHedgeDecision,
    SignalSnapshot,
    StrategyDefinition,
    StrategyRun,
    StrategyEvaluationResult,
    StrategyProposal,
    TradeClassification,
    TradingDecision,
    TradingRuntimeRun,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
    WatchCandidate,
)
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.data_sources.universe import UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.brokers.paper_option import (
    PaperOptionExecutionRecord,
    PaperOptionOrderRecord,
    PaperOptionPosition,
)
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.intraday.news_alerts import NewsAlertRecord
from src.trading.manual_review.sqlalchemy import ManualReviewAuditRow
from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.lookahead import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyRunRecord
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.strategies.selector import WatchCandidateRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord

class _RepositoryBase:
    def __init__(self, session: Any) -> None:
        self.session = session
    def _require_universe_filter_config_row(self, config: UniverseFilterConfigRecord) -> UniverseFilterConfig:
        row = self.session.query(UniverseFilterConfig).filter_by(
            profile_name=config.profile_name,
            version=int(config.version),
        ).one_or_none()
        if row is None:
            raise RuntimeError(
                f"universe_filter_config_not_found:{config.profile_name}:v{config.version}"
            )
        return row
    def _to_event_news_item_record(self, row: Any) -> EventNewsItemRecord:
        return EventNewsItemRecord(
            event_news_item_id=str(row.event_news_item_id),
            ticker=row.ticker,
            source_ticker=row.source_ticker,
            event_type=row.event_type,
            direction=row.direction,
            sentiment=row.sentiment,
            importance=row.importance,
            headline=row.headline,
            summary=row.summary,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            dedupe_key=row.dedupe_key,
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            metadata_json=dict(row.metadata_json or {}),
        )

def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _legacy_option_client_order_id(order: PaperOptionOrderRecord) -> str:
    return (
        order.client_order_id
        or f"{order.trade_date.isoformat()}:{order.ticker}:{order.strategy_id}:{order.action}"
    )


def _format_option_contract_symbol(*, ticker: str, expiry: date, option_type: str, strike: float) -> str:
    option_code = "C" if option_type == "call" else "P"
    strike_component = f"{int(round(float(strike) * 1000)):08d}"
    return f"{ticker.upper()}{expiry.strftime('%y%m%d')}{option_code}{strike_component}"


def _portfolio_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "snapshot_time": row.snapshot_time.isoformat(),
        "cash_balance": _decimal_to_float(row.cash_balance),
        "account_equity": _decimal_to_float(row.account_equity),
        "net_liquidation_value": _decimal_to_float(row.net_liquidation_value),
        "buying_power": _decimal_to_float(row.buying_power),
        "day_pnl": _decimal_to_float(row.day_pnl),
        "realized_pnl": _decimal_to_float(row.realized_pnl),
        "unrealized_pnl": _decimal_to_float(row.unrealized_pnl),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _portfolio_outcome_payload(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "snapshot_time": row.snapshot_time.isoformat(),
        "account_equity": _decimal_to_float(row.account_equity),
        "day_pnl": _decimal_to_float(row.day_pnl),
        "realized_pnl": _decimal_to_float(row.realized_pnl),
        "unrealized_pnl": _decimal_to_float(row.unrealized_pnl),
    }


def _candidate_score_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "candidate_score": _decimal_to_float(row.candidate_score),
        "selection_source": row.selection_source,
        "manual_request_id": str(row.manual_request_id) if row.manual_request_id is not None else None,
        "decision_time": row.decision_time.isoformat(),
    }


def _rejected_candidate_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "rejection_reason": row.rejection_reason,
        "selection_source": row.selection_source,
        "selection_reason": row.selection_reason,
        "core_signal_evidence": dict(row.core_signal_evidence_json or {}),
        "risk_tags": list(row.risk_tags_json or ()),
    }


def _manual_request_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "mode": row.mode,
        "status": row.status,
        "latest_result_status": row.latest_result_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "last_evaluated_at": row.last_evaluated_at.isoformat() if row.last_evaluated_at is not None else None,
    }


def _manual_review_execution_path_state(
    *,
    request: Any,
    decision: Any | None,
    risk: Any | None,
    order: Any | None,
    execution: Any | None,
    latest_signal_snapshot_id: str | None,
) -> tuple[str, str | None]:
    if latest_signal_snapshot_id is None:
        return "pending_evaluation", None
    if decision is None:
        return "snapshot_only", None
    if risk is not None and getattr(risk, "status", None) == "rejected":
        return "risk_blocked", getattr(risk, "reason_code", None)
    if order is None:
        if _manual_review_actionable_decision(decision):
            if getattr(request, "mode", None) == "review_only":
                return "eligible_no_order", "manual_request_review_only"
            return "eligible_no_order", "paper_order_not_submitted"
        return "decision_recorded", None
    if getattr(order, "status", None) == "rejected":
        return "order_rejected", getattr(order, "rejection_reason", None)
    if execution is not None or getattr(order, "status", None) == "filled":
        return "filled", None
    return "order_submitted", getattr(order, "rejection_reason", None)


def _manual_review_linkage_state(
    *,
    latest_signal_snapshot_id: str | None,
    decision: Any | None,
    risk: Any | None,
    order: Any | None,
    execution: Any | None,
) -> str:
    if latest_signal_snapshot_id is None:
        return "pending_evaluation"
    if decision is None:
        return "snapshot_only"
    if execution is not None:
        return "execution_linked"
    if order is not None:
        return "order_linked"
    if risk is not None:
        return "risk_linked"
    return "decision_linked"


def _manual_review_actionable_decision(decision: Any | None) -> bool:
    if decision is None:
        return False
    action = str(getattr(decision, "decision", "") or "").strip()
    metadata_json = dict(getattr(decision, "metadata_json", {}) or {})
    return bool(metadata_json.get("paper_trade_authorized", False)) and action not in {"", "hold", "no_trade"}


def _latest_row_sort_key(row: Any, timestamp_field: str, id_field: str) -> tuple[datetime, str]:
    timestamp = getattr(row, timestamp_field, None) or datetime.min.replace(tzinfo=timezone.utc)
    return timestamp, str(getattr(row, id_field, "") or "")


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _trading_decision_payload(row: Any) -> dict[str, Any]:
    metadata_json = dict(getattr(row, "metadata_json", {}) or {})
    return {
        "ticker": row.ticker,
        "decision": row.decision,
        "strategy_id": row.strategy_id,
        "trade_identity": row.trade_identity,
        "instrument_type": row.instrument_type,
        "selection_source": row.selection_source,
        "confidence": _decimal_to_float(row.confidence),
        "target_weight": _decimal_to_float(row.target_weight),
        "approved_weight": _decimal_to_float(row.approved_weight),
        "key_drivers": list(getattr(row, "key_drivers_json", None) or metadata_json.get("key_drivers") or []),
        "counterarguments": list(
            getattr(row, "counterarguments_json", None) or metadata_json.get("counterarguments") or []
        ),
        "invalidators": list(getattr(row, "invalidators_json", None) or []),
        "decision_time": row.decision_time.isoformat(),
        "metadata_json": metadata_json,
    }


def _news_alert_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "sentiment": row.sentiment,
        "headline": row.headline,
        "summary": row.summary,
        "action_required": bool(row.action_required),
        "published_at": row.published_at.isoformat(),
    }


def _intraday_rebalance_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "action": row.action,
        "status": row.status,
        "reason_code": row.reason_code,
        "confidence": _decimal_to_float(row.confidence),
        "decision_time": row.decision_time.isoformat(),
    }


def _paper_order_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "action": row.action,
        "quantity": _decimal_to_float(row.quantity),
        "order_price": _decimal_to_float(row.order_price),
        "status": row.status,
        "trade_date": row.trade_date.isoformat(),
        "created_at": row.created_at.isoformat(),
    }


def _paper_execution_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "quantity": _decimal_to_float(row.quantity),
        "fill_price": _decimal_to_float(row.fill_price),
        "trade_date": row.trade_date.isoformat(),
        "executed_at": row.executed_at.isoformat(),
        "net_cash_effect": _decimal_to_float(row.net_cash_effect),
    }


def _portfolio_risk_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "decision_time": row.decision_time.isoformat(),
        "account_equity": _decimal_to_float(row.account_equity),
        "cash_balance": _decimal_to_float(row.cash_balance),
        "buying_power": _decimal_to_float(row.buying_power),
        "net_exposure": _decimal_to_float(row.net_exposure),
        "gross_exposure": _decimal_to_float(row.gross_exposure),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _position_risk_action_payload(action: PositionRiskActionRecord) -> dict[str, Any]:
    return {
        "ticker": action.ticker,
        "trade_identity": action.trade_identity,
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "max_allowed_weight_override": action.max_allowed_weight_override,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _hedge_action_payload(action: HedgeActionRecord) -> dict[str, Any]:
    return {
        "action": action.action,
        "risk_source": action.risk_source,
        "severity": action.severity,
        "target_underlier": action.target_underlier,
        "target_exposure_type": action.target_exposure_type,
        "coverage_ratio": action.coverage_ratio,
        "reason_code": action.reason_code,
        "metadata_json": dict(action.metadata_json),
    }


def _position_risk_action_record(payload: dict[str, Any]) -> PositionRiskActionRecord:
    return PositionRiskActionRecord(
        ticker=str(payload.get("ticker", "")),
        trade_identity=str(payload.get("trade_identity", "")),
        action=str(payload.get("action", "")),
        risk_source=str(payload.get("risk_source", "")),
        severity=str(payload.get("severity", "")),
        max_allowed_weight_override=_decimal_to_float(payload.get("max_allowed_weight_override")),
        reason_code=str(payload.get("reason_code", "")),
        metadata_json=dict(payload.get("metadata_json") or {}),
    )


def _hedge_action_record(payload: dict[str, Any]) -> HedgeActionRecord:
    return HedgeActionRecord(
        action=str(payload.get("action", "")),
        risk_source=str(payload.get("risk_source", "")),
        severity=str(payload.get("severity", "")),
        target_underlier=str(payload.get("target_underlier", "")),
        target_exposure_type=str(payload.get("target_exposure_type", "")),
        coverage_ratio=float(payload.get("coverage_ratio", 0.0)),
        reason_code=str(payload.get("reason_code", "")),
        metadata_json=dict(payload.get("metadata_json") or {}),
    )


def _macro_snapshot_record(row: Any) -> MacroSnapshotRecord:
    return MacroSnapshotRecord(
        macro_snapshot_id=str(row.macro_snapshot_id),
        snapshot_time=row.snapshot_time,
        trade_date=row.trade_date,
        regime=row.regime,
        risk_budget_multiplier=_decimal_to_float(row.risk_budget_multiplier) or 0.0,
        volatility_state=row.volatility_state,
        rates_state=row.rates_state,
        liquidity_state=row.liquidity_state,
        blocked_strategy_tags=tuple(row.blocked_strategy_tags_json or ()),
        invalidators=tuple(row.invalidators_json or ()),
        source_freshness=dict(row.source_freshness_json or {}),
        metadata_json=dict(row.metadata_json or {}),
    )


def _calendar_event_record(row: Any) -> CalendarEventRecord:
    return CalendarEventRecord(
        calendar_event_id=str(row.calendar_event_id),
        event_key=row.event_key,
        event_type=row.event_type,
        ticker=row.ticker,
        event_time=row.event_time,
        published_at=row.published_at,
        available_for_decision_at=row.available_for_decision_at,
        title=row.title,
        severity_hint=row.severity_hint,
        source=row.source,
        metadata_json=dict(row.metadata_json or {}),
    )


def _portfolio_event_risk_assessment_record(row: Any) -> PortfolioEventRiskAssessmentRecord:
    return PortfolioEventRiskAssessmentRecord(
        portfolio_event_risk_assessment_id=str(row.portfolio_event_risk_assessment_id),
        calendar_event_id=str(row.calendar_event_id) if row.calendar_event_id is not None else None,
        portfolio_risk_snapshot_id=(
            str(row.portfolio_risk_snapshot_id) if row.portfolio_risk_snapshot_id is not None else None
        ),
        decision_time=row.decision_time,
        available_for_decision_at=row.available_for_decision_at,
        ticker=row.ticker,
        risk_source=row.risk_source,
        severity=row.severity,
        event_type=row.event_type,
        days_until_event=row.days_until_event,
        affects_existing_position=bool(row.affects_existing_position),
        affects_pending_trade=bool(row.affects_pending_trade),
        recommended_action=row.recommended_action,
        rationale=row.rationale,
        metadata_json=dict(row.metadata_json or {}),
    )


def _portfolio_risk_intent_record(row: Any) -> PortfolioRiskIntentRecord:
    return PortfolioRiskIntentRecord(
        portfolio_risk_intent_id=str(row.portfolio_risk_intent_id),
        portfolio_risk_snapshot_id=(
            str(row.portfolio_risk_snapshot_id) if row.portfolio_risk_snapshot_id is not None else None
        ),
        decision_time=row.decision_time,
        risk_window=row.risk_window,
        aggregate_risk_state=row.aggregate_risk_state,
        position_actions=tuple(
            _position_risk_action_record(payload)
            for payload in list(row.position_actions_json or ())
        ),
        hedge_actions=tuple(
            _hedge_action_record(payload)
            for payload in list(row.hedge_actions_json or ())
        ),
        binding_constraints=tuple(row.binding_constraints_json or ()),
        metadata_json=dict(row.metadata_json or {}),
    )


def _portfolio_event_risk_assessment_storage_key(
    assessment: PortfolioEventRiskAssessmentRecord,
) -> str:
    if assessment.portfolio_event_risk_assessment_id:
        return assessment.portfolio_event_risk_assessment_id
    return "|".join(
        (
            assessment.calendar_event_id or "synthetic",
            assessment.portfolio_risk_snapshot_id or "no_snapshot",
            assessment.ticker,
            assessment.risk_source,
            assessment.available_for_decision_at.isoformat() if assessment.available_for_decision_at else "na",
        )
    )


def _risk_factor_exposure_payload(row: Any) -> dict[str, Any]:
    return {
        "factor_type": row.factor_type,
        "factor_value": row.factor_value,
        "gross_exposure": _decimal_to_float(row.gross_exposure),
        "net_exposure": _decimal_to_float(row.net_exposure),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _candidate_outcome_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "trade_identity": row.trade_identity,
        "evaluation_status": row.evaluation_status,
        "candidate_return": _decimal_to_float(row.candidate_return),
        "alpha": _decimal_to_float(row.alpha),
        "benchmark_returns": dict(row.benchmark_returns_json or {}),
        "decision_time": row.decision_time.isoformat(),
    }


def _daily_reflection_record(row: Any) -> DailyReflectionRecord:
    return DailyReflectionRecord(
        daily_reflection_id=str(row.daily_reflection_id),
        trade_date=row.trade_date,
        status=row.status,
        prompt_template=None,
        prompt_run=SimpleNamespace(prompt_run_id=str(row.prompt_run_id) if row.prompt_run_id is not None else None),
        usage_events=[],
        reflection_json=dict(row.reflection_json or {}),
        strategy_proposal_hints=tuple(row.strategy_proposal_hints_json or ()),
        metadata_json=dict(row.metadata_json or {}),
    )


def _learning_factor_record(row: Any) -> LearningFactorRecord:
    return LearningFactorRecord(
        learning_factor_id=str(row.learning_factor_id),
        factor_key=row.factor_key,
        trade_date=row.trade_date,
        title=row.title,
        factor_type=row.factor_type,
        scope=row.scope,
        status=row.status,
        strategy_id=row.strategy_id,
        condition=row.condition,
        recommendation=row.recommendation,
        confidence=_decimal_to_float(row.confidence) or 0.0,
        activation_policy=row.activation_policy,
        effect_tags=tuple(row.effect_tags_json or ()),
        evidence=tuple(row.evidence_json or ()),
        source_daily_reflection_id=str(row.daily_reflection_id) if row.daily_reflection_id is not None else "",
        metadata_json=dict(row.metadata_json or {}),
    )


def _candidate_outcome_record(row: Any) -> CandidateOutcomeEvaluationRecord:
    return CandidateOutcomeEvaluationRecord(
        candidate_outcome_evaluation_id=str(row.candidate_outcome_evaluation_id),
        historical_replay_run_id=str(row.historical_replay_run_id) if row.historical_replay_run_id is not None else None,
        candidate_score_id=str(row.candidate_score_id) if row.candidate_score_id is not None else None,
        trade_classification_id=str(row.trade_classification_id) if row.trade_classification_id is not None else None,
        ticker=row.ticker,
        strategy_id=row.strategy_id,
        strategy_version=row.strategy_version,
        expression_bucket_id=row.expression_bucket_id,
        trade_identity=row.trade_identity,
        direction=row.direction,
        catalyst_type=row.catalyst_type,
        confidence_bucket=row.confidence_bucket,
        decision_time=row.decision_time,
        horizon_start_at=row.horizon_start_at,
        horizon_end_at=row.horizon_end_at,
        evaluation_status=row.evaluation_status,
        candidate_return=_decimal_to_float(row.candidate_return),
        benchmark_returns={str(key): float(value) for key, value in dict(row.benchmark_returns_json or {}).items()},
        peer_basket_id=str(row.peer_basket_id) if row.peer_basket_id is not None else None,
        peer_basket_return=_decimal_to_float(row.peer_basket_return),
        alpha=_decimal_to_float(row.alpha),
        max_favorable_excursion=_decimal_to_float(row.max_favorable_excursion),
        max_adverse_excursion=_decimal_to_float(row.max_adverse_excursion),
        regime=row.regime,
        sector_theme=row.sector_theme,
        metadata_json=dict(row.metadata_json or {}),
    )


def _paper_option_decision_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "status": row.status,
        "decision_action": row.decision_action,
        "created_at": row.created_at.isoformat(),
    }


def _paper_option_position_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "quantity": row.quantity,
        "status": row.status,
        "opened_at": row.opened_at.isoformat(),
    }


def _intraday_context_metadata(*, decision: Any | None, option_position: Any | None) -> dict[str, Any]:
    metadata_json: dict[str, Any] = {}
    decision_metadata = dict(getattr(decision, "metadata_json", {}) or {})
    option_strategy = decision_metadata.get("option_strategy")
    if isinstance(option_strategy, dict):
        metadata_json["option_strategy"] = dict(option_strategy)
    option_strategy_type = None
    if option_position is not None:
        metadata_json["paper_option_position_id"] = option_position.paper_option_position_id
        option_strategy_type = option_position.option_strategy_type
    elif isinstance(option_strategy, dict):
        option_strategy_type = option_strategy.get("option_strategy_type")
    if isinstance(option_strategy_type, str) and option_strategy_type:
        metadata_json["option_strategy_type"] = option_strategy_type
    return metadata_json


def _option_risk_snapshot_payload(row: Any) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "option_strategy_type": row.option_strategy_type,
        "risk_status": row.risk_status,
        "reason_code": row.reason_code,
        "created_at": row.created_at.isoformat(),
    }


def _risk_hedge_overlay_payload(row: Any) -> dict[str, Any]:
    metadata_json = dict(row.metadata_json or {})
    generated_hedge_action = dict(metadata_json.get("generated_hedge_action") or {})
    return {
        "ticker": row.ticker,
        "action": row.action,
        "option_strategy_type": row.option_strategy_type,
        "rationale": row.rationale,
        "hedge_cost": _decimal_to_float(row.hedge_cost),
        "protected_notional": _decimal_to_float(row.protected_notional),
        "target_exposure_type": generated_hedge_action.get("target_exposure_type"),
        "protected_exposure_basis": generated_hedge_action.get("protected_exposure_basis"),
        "created_at": row.created_at.isoformat(),
        "metadata_json": metadata_json,
    }


def _hedge_effectiveness_payload(rows: tuple[Any, ...]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    exposure_basis_counts: dict[str, int] = {}
    assignment_overlay_count = 0
    protected_notional = 0.0
    hedge_cost = 0.0
    for row in rows:
        action_counts[row.action] = action_counts.get(row.action, 0) + 1
        protected_notional += _decimal_to_float(row.protected_notional)
        hedge_cost += _decimal_to_float(row.hedge_cost)
        metadata_json = dict(row.metadata_json or {})
        generated_hedge_action = dict(metadata_json.get("generated_hedge_action") or {})
        target_exposure_type = generated_hedge_action.get("target_exposure_type")
        if target_exposure_type == "assignment":
            assignment_overlay_count += 1
        basis = generated_hedge_action.get("protected_exposure_basis")
        if isinstance(basis, str) and basis:
            exposure_basis_counts[basis] = exposure_basis_counts.get(basis, 0) + 1
    return {
        "overlay_count": len(rows),
        "assignment_overlay_count": assignment_overlay_count,
        "protected_notional": protected_notional,
        "hedge_cost": hedge_cost,
        "action_counts": action_counts,
        "protected_exposure_basis_counts": exposure_basis_counts,
    }


def _latest_portfolio_risk_snapshot_id(session: Any) -> uuid.UUID:
    rows = session.query(PortfolioRiskSnapshot).all()
    if not rows:
        raise RuntimeError("portfolio_risk_snapshot_not_found_for_exposure")
    latest = max(
        rows,
        key=lambda row: (
            getattr(row, "decision_time", None),
            getattr(row, "created_at", None),
        ),
    )
    return latest.portfolio_risk_snapshot_id


__all__ = [name for name in globals() if not name.startswith("__")]
