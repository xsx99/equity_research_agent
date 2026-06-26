from __future__ import annotations

from src.trading.repositories._base import *  # noqa: F401,F403


class ReflectionRepositoryMixin:
    def load_active_learning_factors(self) -> list[LearningFactorRecord]:
        return [
            _learning_factor_record(row)
            for row in self.session.query(LearningFactor).all()
            if row.status in {"active", "shadow"}
        ]
    def load_reflection_inputs(self, *, trade_date: date) -> dict[str, object]:
        latest_portfolio_snapshot = (
            self.session.query(PortfolioSnapshotModel)
            .filter(PortfolioSnapshotModel.snapshot_time >= datetime.combine(trade_date, datetime.min.time()))
            .all()
        )
        portfolio_rows = [row for row in latest_portfolio_snapshot if row.snapshot_time.date() == trade_date]
        latest_snapshot = max(portfolio_rows, key=lambda row: row.snapshot_time) if portfolio_rows else None
        latest_risk_snapshot = max(
            (row for row in self.session.query(PortfolioRiskSnapshot).all() if row.decision_time.date() == trade_date),
            key=lambda row: row.decision_time,
            default=None,
        )
        risk_snapshot_id = latest_risk_snapshot.portfolio_risk_snapshot_id if latest_risk_snapshot is not None else None
        latest_reflection = (
            max(
                (row for row in self.session.query(DailyReflection).all() if row.trade_date == trade_date),
                key=lambda row: row.created_at,
                default=None,
            )
        )
        hedge_rows = tuple(
            row
            for row in self.session.query(RiskHedgeDecision).all()
            if row.created_at.date() == trade_date
        )
        return {
            "portfolio_outcome": _portfolio_outcome_payload(latest_snapshot),
            "morning_macro_snapshot": {},
            "strategy_candidates": tuple(
                _candidate_score_payload(row)
                for row in self.session.query(CandidateScore).all()
                if row.decision_time.date() == trade_date
            ),
            "manual_ticker_requests": tuple(
                _manual_request_payload(row)
                for row in self.session.query(ManualTickerRequest).all()
                if (row.created_at and row.created_at.date() == trade_date)
                or (row.last_evaluated_at and row.last_evaluated_at.date() == trade_date)
            ),
            "trading_decisions": tuple(
                _trading_decision_payload(row)
                for row in self.session.query(TradingDecision).all()
                if row.decision_time.date() == trade_date and row.decision not in {"no_trade", "hold"}
            ),
            "rejected_decisions": tuple(
                _trading_decision_payload(row)
                for row in self.session.query(TradingDecision).all()
                if row.decision_time.date() == trade_date and row.decision in {"no_trade", "hold"}
            ),
            "intraday_news_alerts": tuple(
                _news_alert_payload(row)
                for row in self.session.query(NewsAlert).all()
                if row.created_at.date() == trade_date
            ),
            "intraday_rebalance_decisions": tuple(
                _intraday_rebalance_payload(row)
                for row in self.session.query(IntradayRebalanceDecision).all()
                if row.decision_time.date() == trade_date
            ),
            "paper_orders": tuple(
                _paper_order_payload(row)
                for row in self.session.query(PaperOrder).all()
                if row.trade_date == trade_date
            ),
            "paper_executions": tuple(
                _paper_execution_payload(row)
                for row in self.session.query(PaperExecution).all()
                if row.trade_date == trade_date
            ),
            "risk_snapshots": tuple(
                _portfolio_risk_snapshot_payload(row)
                for row in self.session.query(PortfolioRiskSnapshot).all()
                if row.decision_time.date() == trade_date
            ),
            "risk_factor_exposures": tuple(
                _risk_factor_exposure_payload(row)
                for row in self.session.query(RiskFactorExposure).all()
                if risk_snapshot_id is not None and row.portfolio_risk_snapshot_id == risk_snapshot_id
            ),
            "portfolio_snapshots": tuple(_portfolio_snapshot_payload(row) for row in portfolio_rows),
            "candidate_outcome_evaluations": tuple(
                _candidate_outcome_payload(row)
                for row in self.session.query(CandidateOutcomeEvaluation).all()
                if row.decision_time.date() == trade_date
            ),
            "benchmark_peer_returns": {},
            "paper_option_decisions": tuple(
                _paper_option_decision_payload(row)
                for row in self.session.query(OptionStrategyDecision).all()
                if row.created_at.date() == trade_date
            ),
            "paper_option_positions": tuple(
                _paper_option_position_payload(row)
                for row in self.session.query(PaperOptionPositionModel).all()
                if row.opened_at.date() == trade_date
            ),
            "option_risk_snapshots": tuple(
                _option_risk_snapshot_payload(row)
                for row in self.session.query(OptionRiskSnapshot).all()
                if row.created_at.date() == trade_date
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
        row = self.session.query(DailyReflection).filter_by(
            daily_reflection_id=_to_uuid(reflection.daily_reflection_id)
        ).one_or_none()
        if row is None:
            row = DailyReflection(daily_reflection_id=_to_uuid(reflection.daily_reflection_id))
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
        row = self.session.query(LearningFactor).filter_by(
            learning_factor_id=_to_uuid(learning_factor.learning_factor_id)
        ).one_or_none()
        if row is None:
            row = LearningFactor(learning_factor_id=_to_uuid(learning_factor.learning_factor_id))
            self.session.add(row)
        row.factor_key = learning_factor.factor_key
        row.daily_reflection_id = _to_uuid_or_none(learning_factor.source_daily_reflection_id)
        row.trade_date = learning_factor.trade_date
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
