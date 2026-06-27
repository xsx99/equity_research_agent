"""Row-to-record adapters for SQLAlchemy trading repositories."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from src.db.models.trading import PortfolioRiskSnapshot
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.risk.lookahead import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord

from src.trading.repositories._base_common import _decimal_to_float


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
