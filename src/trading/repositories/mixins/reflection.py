from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_

from src.core import config as app_config
from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    DailyReflection,
    IntradayRebalanceDecision,
    LearningFactor,
    ManualTickerRequest,
    NewsAlert,
    OptionRiskSnapshot,
    OptionStrategyDecision,
    PaperExecution,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PortfolioRiskSnapshot,
    PortfolioSnapshot as PortfolioSnapshotModel,
    RiskFactorExposure,
    RiskHedgeDecision,
    TradingDecision,
)
from src.trading.post_close.reflection import LearningFactorRecord
from src.trading.repositories._base_common import _to_uuid, _to_uuid_or_none
from src.trading.repositories._base_manual_review import _manual_request_payload
from src.trading.repositories._base_payloads import (
    _candidate_outcome_payload,
    _candidate_score_payload,
    _hedge_effectiveness_payload,
    _intraday_rebalance_payload,
    _news_alert_payload,
    _option_risk_snapshot_payload,
    _paper_execution_payload,
    _paper_option_decision_payload,
    _paper_option_position_payload,
    _paper_order_payload,
    _portfolio_outcome_payload,
    _portfolio_risk_snapshot_payload,
    _portfolio_snapshot_payload,
    _risk_factor_exposure_payload,
    _risk_hedge_overlay_payload,
    _trading_decision_payload,
)
from src.trading.repositories._base_records import _learning_factor_record
from src.trading.trade_day import local_day_bounds_utc


LONG_HORIZON_LOOKBACK_DAYS = 60


class ReflectionRepositoryMixin:
    def load_active_learning_factors(self) -> list[LearningFactorRecord]:
        return [
            _learning_factor_record(row)
            for row in self.session.query(LearningFactor).all()
            if row.status in {"active", "shadow"}
        ]

    # PR 36 column audit:
    # DateTime windowed in UTC: PortfolioSnapshot.snapshot_time,
    # PortfolioRiskSnapshot.decision_time, RiskHedgeDecision.created_at,
    # CandidateScore.decision_time, ManualTickerRequest.created_at /
    # last_evaluated_at, TradingDecision.decision_time, NewsAlert.created_at,
    # IntradayRebalanceDecision.decision_time, CandidateOutcomeEvaluation.decision_time,
    # OptionStrategyDecision.created_at, PaperOptionPosition.opened_at,
    # OptionRiskSnapshot.created_at.
    # Date equality: DailyReflection.trade_date, PaperOrder.trade_date,
    # PaperExecution.trade_date.
    # FK keyed: RiskFactorExposure.portfolio_risk_snapshot_id.
    def load_reflection_inputs(
        self,
        *,
        trade_date: date,
        window: tuple[datetime, datetime],
    ) -> dict[str, object]:
        start_utc, end_utc = window
        lookback_start_utc, _ = local_day_bounds_utc(
            trade_date - timedelta(days=LONG_HORIZON_LOOKBACK_DAYS),
            app_config.SCHEDULER_TIMEZONE,
        )
        prior_reflection_start = trade_date - timedelta(days=LONG_HORIZON_LOOKBACK_DAYS)
        portfolio_rows = (
            self.session.query(PortfolioSnapshotModel)
            .filter(
                PortfolioSnapshotModel.snapshot_time >= start_utc,
                PortfolioSnapshotModel.snapshot_time < end_utc,
            )
            .all()
        )
        latest_snapshot = max(portfolio_rows, key=lambda row: row.snapshot_time) if portfolio_rows else None
        risk_snapshot_rows = (
            self.session.query(PortfolioRiskSnapshot)
            .filter(
                PortfolioRiskSnapshot.decision_time >= start_utc,
                PortfolioRiskSnapshot.decision_time < end_utc,
            )
            .all()
        )
        latest_risk_snapshot = max(
            risk_snapshot_rows,
            key=lambda row: row.decision_time,
            default=None,
        )
        risk_snapshot_id = latest_risk_snapshot.portfolio_risk_snapshot_id if latest_risk_snapshot is not None else None
        latest_reflection = max(
            self.session.query(DailyReflection).filter(DailyReflection.trade_date == trade_date).all(),
            key=lambda row: row.created_at,
            default=None,
        )
        hedge_rows = tuple(
            self.session.query(RiskHedgeDecision)
            .filter(
                RiskHedgeDecision.created_at >= start_utc,
                RiskHedgeDecision.created_at < end_utc,
            )
            .all()
        )
        return {
            "portfolio_outcome": _portfolio_outcome_payload(latest_snapshot),
            "morning_macro_snapshot": {},
            "strategy_candidates": tuple(
                _candidate_score_payload(row)
                for row in self.session.query(CandidateScore)
                .filter(
                    CandidateScore.decision_time >= start_utc,
                    CandidateScore.decision_time < end_utc,
                )
                .all()
            ),
            "manual_ticker_requests": tuple(
                _manual_request_payload(row)
                for row in self.session.query(ManualTickerRequest)
                .filter(
                    or_(
                        and_(
                            ManualTickerRequest.created_at >= start_utc,
                            ManualTickerRequest.created_at < end_utc,
                        ),
                        and_(
                            ManualTickerRequest.last_evaluated_at >= start_utc,
                            ManualTickerRequest.last_evaluated_at < end_utc,
                        ),
                    )
                )
                .all()
            ),
            "trading_decisions": tuple(
                _trading_decision_payload(row)
                for row in self.session.query(TradingDecision)
                .filter(
                    TradingDecision.decision_time >= start_utc,
                    TradingDecision.decision_time < end_utc,
                    TradingDecision.decision.notin_(("no_trade", "hold")),
                )
                .all()
            ),
            "rejected_decisions": tuple(
                _trading_decision_payload(row)
                for row in self.session.query(TradingDecision)
                .filter(
                    TradingDecision.decision_time >= start_utc,
                    TradingDecision.decision_time < end_utc,
                    TradingDecision.decision.in_(("no_trade", "hold")),
                )
                .all()
            ),
            "intraday_news_alerts": tuple(
                _news_alert_payload(row)
                for row in self.session.query(NewsAlert)
                .filter(
                    NewsAlert.created_at >= start_utc,
                    NewsAlert.created_at < end_utc,
                )
                .all()
            ),
            "intraday_rebalance_decisions": tuple(
                _intraday_rebalance_payload(row)
                for row in self.session.query(IntradayRebalanceDecision)
                .filter(
                    IntradayRebalanceDecision.decision_time >= start_utc,
                    IntradayRebalanceDecision.decision_time < end_utc,
                )
                .all()
            ),
            "paper_orders": tuple(
                _paper_order_payload(row)
                for row in self.session.query(PaperOrder)
                .filter(PaperOrder.trade_date == trade_date)
                .all()
            ),
            "paper_executions": tuple(
                _paper_execution_payload(row)
                for row in self.session.query(PaperExecution)
                .filter(PaperExecution.trade_date == trade_date)
                .all()
            ),
            "risk_snapshots": tuple(
                _portfolio_risk_snapshot_payload(row)
                for row in risk_snapshot_rows
            ),
            "risk_factor_exposures": tuple(
                _risk_factor_exposure_payload(row)
                for row in self.session.query(RiskFactorExposure)
                .filter(RiskFactorExposure.portfolio_risk_snapshot_id == risk_snapshot_id)
                .all()
                if risk_snapshot_id is not None
            ),
            "portfolio_snapshots": tuple(_portfolio_snapshot_payload(row) for row in portfolio_rows),
            "candidate_outcome_evaluations": tuple(
                _candidate_outcome_payload(row)
                for row in self.session.query(CandidateOutcomeEvaluation)
                .filter(
                    CandidateOutcomeEvaluation.decision_time >= start_utc,
                    CandidateOutcomeEvaluation.decision_time < end_utc,
                )
                .all()
            ),
            "historical_outcome_context": tuple(
                _candidate_outcome_payload(row)
                for row in sorted(
                    self.session.query(CandidateOutcomeEvaluation)
                    .filter(
                        CandidateOutcomeEvaluation.decision_time >= lookback_start_utc,
                        CandidateOutcomeEvaluation.decision_time < start_utc,
                    )
                    .all(),
                    key=lambda item: item.decision_time,
                    reverse=True,
                )
            ),
            "prior_reflection_context": tuple(
                _prior_reflection_context_payload(row)
                for row in sorted(
                    self.session.query(DailyReflection)
                    .filter(
                        DailyReflection.trade_date >= prior_reflection_start,
                        DailyReflection.trade_date < trade_date,
                    )
                    .all(),
                    key=lambda item: item.trade_date,
                    reverse=True,
                )
            ),
            "benchmark_peer_returns": {},
            "paper_option_decisions": tuple(
                _paper_option_decision_payload(row)
                for row in self.session.query(OptionStrategyDecision)
                .filter(
                    OptionStrategyDecision.created_at >= start_utc,
                    OptionStrategyDecision.created_at < end_utc,
                )
                .all()
            ),
            "paper_option_positions": tuple(
                _paper_option_position_payload(row)
                for row in self.session.query(PaperOptionPositionModel)
                .filter(
                    PaperOptionPositionModel.opened_at >= start_utc,
                    PaperOptionPositionModel.opened_at < end_utc,
                )
                .all()
            ),
            "option_risk_snapshots": tuple(
                _option_risk_snapshot_payload(row)
                for row in self.session.query(OptionRiskSnapshot)
                .filter(
                    OptionRiskSnapshot.created_at >= start_utc,
                    OptionRiskSnapshot.created_at < end_utc,
                )
                .all()
            ),
            "worst_case_assignment_snapshots": (),
            "risk_hedge_overlays": tuple(_risk_hedge_overlay_payload(row) for row in hedge_rows),
            "hedge_effectiveness": _hedge_effectiveness_payload(hedge_rows),
            "learning_factors_used": tuple(
                latest_reflection.metadata_json.get("learning_factors_used", ())
                if latest_reflection is not None and isinstance(latest_reflection.metadata_json, dict)
                else ()
            ),
        }

    def save_daily_reflection(self, reflection: Any) -> None:
        reflection_id = _to_uuid(reflection.daily_reflection_id)
        row = self.session.query(DailyReflection).filter_by(
            daily_reflection_id=reflection_id
        ).one_or_none()
        if row is None:
            row = self.session.query(DailyReflection).filter_by(trade_date=reflection.trade_date).one_or_none()
        if row is None:
            row = DailyReflection(daily_reflection_id=reflection_id)
            self.session.add(row)
        row.trade_date = reflection.trade_date
        row.prompt_run_id = None
        row.status = reflection.status
        row.portfolio_summary_json = dict(reflection.metadata_json.get("portfolio_outcome", {}))
        row.reflection_json = dict(reflection.reflection_json)
        row.strategy_proposal_hints_json = list(reflection.strategy_proposal_hints)
        row.metadata_json = dict(reflection.metadata_json)
        self.session.flush()
    def save_learning_factor(self, learning_factor: Any) -> None:
        source_daily_reflection_id = _to_uuid_or_none(learning_factor.source_daily_reflection_id)
        if source_daily_reflection_id is not None:
            reflection = self.session.query(DailyReflection).filter_by(
                daily_reflection_id=source_daily_reflection_id
            ).one_or_none()
            if reflection is None:
                reflection = self.session.query(DailyReflection).filter_by(
                    trade_date=learning_factor.trade_date
                ).one_or_none()
            if reflection is not None:
                source_daily_reflection_id = reflection.daily_reflection_id
        row = self.session.query(LearningFactor).filter_by(
            learning_factor_id=_to_uuid(learning_factor.learning_factor_id)
        ).one_or_none()
        if row is None:
            row = LearningFactor(learning_factor_id=_to_uuid(learning_factor.learning_factor_id))
            self.session.add(row)
        row.factor_key = learning_factor.factor_key
        row.trade_date = learning_factor.trade_date
        row.daily_reflection_id = source_daily_reflection_id
        row.title = learning_factor.title
        row.factor_type = learning_factor.factor_type
        row.scope = learning_factor.scope
        row.status = learning_factor.status
        row.strategy_id = learning_factor.strategy_id
        row.condition = learning_factor.condition
        row.recommendation = learning_factor.recommendation
        row.confidence = Decimal(str(learning_factor.confidence))
        row.activation_policy = learning_factor.activation_policy
        row.effect_tags_json = list(learning_factor.effect_tags)
        row.evidence_json = list(learning_factor.evidence)
        row.metadata_json = dict(learning_factor.metadata_json)
        self.session.flush()


def _prior_reflection_context_payload(row: Any) -> dict[str, Any]:
    reflection_json = dict(row.reflection_json or {})
    return {
        "daily_reflection_id": str(row.daily_reflection_id),
        "trade_date": row.trade_date.isoformat(),
        "status": row.status,
        "what_worked": list(reflection_json.get("what_worked") or ()),
        "what_failed": list(reflection_json.get("what_failed") or ()),
        "strategy_proposal_hints": list(row.strategy_proposal_hints_json or ()),
    }
