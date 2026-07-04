from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from src.core import config as app_config
from src.db.models.trading import (
    OptionRiskSnapshot,
    PortfolioRiskIntent,
    PortfolioRiskSnapshot,
    PositionSizingDecision,
    RiskDecision,
    RiskFactorExposure,
    RiskHedgeDecision,
)
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.lookahead import PortfolioRiskIntentRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.repositories._base_common import _decimal_or_none, _to_uuid, _to_uuid_or_none
from src.trading.repositories._base_payloads import (
    _hedge_action_payload,
    _position_risk_action_payload,
)
from src.trading.repositories._base_records import (
    _latest_portfolio_risk_snapshot_id,
    _portfolio_risk_intent_record,
)
from src.trading.trade_day import local_day_bounds_utc


def _trade_day_window(trade_date: date) -> tuple[object, object]:
    return local_day_bounds_utc(trade_date, app_config.SCHEDULER_TIMEZONE)


class RiskRepositoryMixin:
    def save_position_sizing_decision(self, decision: Any) -> None:
        row = self.session.query(PositionSizingDecision).filter_by(
            position_sizing_decision_id=_to_uuid(decision.position_sizing_decision_id)
        ).one_or_none()
        if row is None:
            row = PositionSizingDecision(
                position_sizing_decision_id=_to_uuid(decision.position_sizing_decision_id)
            )
            self.session.add(row)
        row.candidate_score_id = _to_uuid_or_none(decision.candidate_score_id)
        row.trade_classification_id = _to_uuid_or_none(decision.trade_classification_id)
        row.ticker = decision.ticker
        row.risk_appetite = decision.risk_appetite
        row.base_weight = Decimal(str(decision.base_weight))
        row.volatility_adjusted_weight = Decimal(str(decision.volatility_adjusted_weight))
        row.liquidity_capped_weight = Decimal(str(decision.liquidity_capped_weight))
        row.final_weight = Decimal(str(decision.final_weight))
        row.final_notional = Decimal(str(decision.final_notional))
        row.applied_caps_json = list(decision.applied_caps)
        row.binding_constraint = decision.binding_constraint
        row.decision_time = decision.decision_time
        row.metadata_json = dict(decision.metadata_json)
        self.session.flush()
    def save_portfolio_risk_snapshot(self, snapshot: Any) -> None:
        row = self.session.query(PortfolioRiskSnapshot).filter_by(
            portfolio_risk_snapshot_id=_to_uuid(snapshot.portfolio_risk_snapshot_id)
        ).one_or_none()
        if row is None:
            row = PortfolioRiskSnapshot(
                portfolio_risk_snapshot_id=_to_uuid(snapshot.portfolio_risk_snapshot_id)
            )
            self.session.add(row)
        row.decision_time = snapshot.decision_time
        row.risk_appetite = snapshot.risk_appetite
        row.resolver_version = snapshot.resolver_version
        row.margin_model_profile = snapshot.margin_model_profile
        row.margin_model_version = snapshot.margin_model_version
        row.account_equity = Decimal(str(snapshot.account_equity))
        row.cash_balance = Decimal(str(snapshot.cash_balance))
        row.buying_power = Decimal(str(snapshot.buying_power))
        row.excess_liquidity = Decimal(str(snapshot.excess_liquidity))
        row.stock_margin_requirement = Decimal(str(snapshot.stock_margin_requirement))
        row.option_margin_requirement = Decimal(str(snapshot.option_margin_requirement))
        row.total_margin_requirement = Decimal(str(snapshot.total_margin_requirement))
        row.initial_margin_requirement = _decimal_or_none(snapshot.initial_margin_requirement)
        row.maintenance_margin_requirement = _decimal_or_none(snapshot.maintenance_margin_requirement)
        row.margin_requirement_source = snapshot.margin_requirement_source
        row.net_exposure = Decimal(str(snapshot.net_exposure))
        row.gross_exposure = Decimal(str(snapshot.gross_exposure))
        row.beta_adjusted_net_exposure = Decimal(str(snapshot.beta_adjusted_net_exposure))
        row.concentration_flags_json = list(snapshot.concentration_flags)
        row.metadata_json = dict(snapshot.metadata_json)
        self.session.flush()
    def save_portfolio_risk_intent(self, intent: PortfolioRiskIntentRecord) -> None:
        row = self.session.query(PortfolioRiskIntent).filter_by(
            portfolio_risk_intent_id=_to_uuid(intent.portfolio_risk_intent_id)
        ).one_or_none()
        if row is None:
            row = PortfolioRiskIntent(
                portfolio_risk_intent_id=_to_uuid(intent.portfolio_risk_intent_id)
            )
            self.session.add(row)
        row.portfolio_risk_snapshot_id = _to_uuid_or_none(intent.portfolio_risk_snapshot_id)
        row.decision_time = intent.decision_time
        row.risk_window = intent.risk_window
        row.aggregate_risk_state = intent.aggregate_risk_state
        row.position_actions_json = [_position_risk_action_payload(action) for action in intent.position_actions]
        row.hedge_actions_json = [_hedge_action_payload(action) for action in intent.hedge_actions]
        row.binding_constraints_json = list(intent.binding_constraints)
        row.metadata_json = dict(intent.metadata_json)
        self.session.flush()
    def load_portfolio_risk_intents(self, *, trade_date: date) -> tuple[PortfolioRiskIntentRecord, ...]:
        start_utc, end_utc = _trade_day_window(trade_date)
        rows = (
            self.session.query(PortfolioRiskIntent)
            .filter(
                PortfolioRiskIntent.decision_time >= start_utc,
                PortfolioRiskIntent.decision_time < end_utc,
            )
            .all()
        )
        rows.sort(key=lambda row: row.decision_time)
        return tuple(_portfolio_risk_intent_record(row) for row in rows)
    def save_risk_factor_exposures(
        self,
        exposures: list[Any] | tuple[Any, ...],
    ) -> None:
        for exposure in exposures:
            row = RiskFactorExposure(
                risk_factor_exposure_id=uuid.uuid4(),
                portfolio_risk_snapshot_id=_to_uuid(exposure.metadata_json["portfolio_risk_snapshot_id"])
                if "portfolio_risk_snapshot_id" in exposure.metadata_json
                else _latest_portfolio_risk_snapshot_id(self.session),
                factor_type=exposure.factor_type,
                factor_value=exposure.factor_value,
                gross_exposure=Decimal(str(exposure.gross_exposure)),
                net_exposure=Decimal(str(exposure.net_exposure)),
                long_exposure=Decimal(str(exposure.long_exposure)),
                short_exposure=Decimal(str(exposure.short_exposure)),
                position_count=int(exposure.position_count),
                metadata_json=dict(exposure.metadata_json),
            )
            self.session.add(row)
        self.session.flush()
    def save_risk_decision(self, decision: Any) -> None:
        row = self.session.query(RiskDecision).filter_by(
            risk_decision_id=_to_uuid(decision.risk_decision_id)
        ).one_or_none()
        if row is None:
            row = RiskDecision(risk_decision_id=_to_uuid(decision.risk_decision_id))
            self.session.add(row)
        row.candidate_score_id = _to_uuid_or_none(decision.candidate_score_id)
        row.trade_classification_id = _to_uuid_or_none(decision.trade_classification_id)
        row.position_sizing_decision_id = _to_uuid_or_none(decision.position_sizing_decision_id)
        row.portfolio_risk_snapshot_id = _to_uuid_or_none(decision.portfolio_risk_snapshot_id)
        row.ticker = decision.ticker
        row.status = decision.status
        row.reason_code = decision.reason_code
        row.approved_weight = Decimal(str(decision.approved_weight))
        row.approved_notional = Decimal(str(decision.approved_notional))
        row.approved_quantity = Decimal(str(decision.approved_quantity))
        row.applied_rules_json = list(decision.applied_rules)
        row.generated_hedge_action_json = (
            dict(decision.generated_hedge_action) if decision.generated_hedge_action is not None else None
        )
        row.decision_time = decision.decision_time
        metadata_json = dict(decision.metadata_json)
        if getattr(decision, "binding_constraint", None) is not None:
            metadata_json.setdefault("binding_constraint", decision.binding_constraint)
        if getattr(decision, "lookahead_risk_source", None) is not None:
            metadata_json.setdefault("lookahead_risk_source", decision.lookahead_risk_source)
        row.metadata_json = metadata_json
        self.session.flush()
    def save_option_risk_snapshot(self, snapshot: OptionRiskSnapshotRecord) -> None:
        row = OptionRiskSnapshot(
            option_risk_snapshot_id=_to_uuid(snapshot.option_risk_snapshot_id),
            ticker=snapshot.ticker,
            trade_identity=snapshot.trade_identity,
            option_strategy_type=snapshot.option_strategy_type,
            underlying_price=Decimal(str(snapshot.underlying_price)),
            portfolio_delta=Decimal(str(snapshot.portfolio_delta)),
            portfolio_gamma=Decimal(str(snapshot.portfolio_gamma)),
            portfolio_theta=Decimal(str(snapshot.portfolio_theta)),
            portfolio_vega=Decimal(str(snapshot.portfolio_vega)),
            net_debit_or_credit=Decimal(str(snapshot.net_debit_or_credit)),
            max_loss=Decimal(str(snapshot.max_loss)),
            max_profit=_decimal_or_none(snapshot.max_profit),
            margin_requirement=Decimal(str(snapshot.margin_requirement)),
            buying_power_effect=Decimal(str(snapshot.buying_power_effect)),
            assignment_notional=Decimal(str(snapshot.assignment_notional)),
            worst_case_assignment_notional=Decimal(str(snapshot.worst_case_assignment_notional)),
            margin_model_profile=snapshot.margin_model_profile,
            margin_model_version=snapshot.margin_model_version,
            margin_requirement_source=snapshot.margin_requirement_source,
            risk_status=snapshot.risk_status,
            reason_code=snapshot.reason_code,
            metadata_json=dict(snapshot.metadata_json),
            created_at=snapshot.created_at,
        )
        self.session.add(row)
        self.session.flush()
    def save_risk_hedge_decision(self, decision: RiskHedgeDecisionRecord) -> None:
        row = RiskHedgeDecision(
            risk_hedge_decision_id=_to_uuid(decision.risk_hedge_decision_id),
            risk_decision_id=_to_uuid_or_none(decision.risk_decision_id),
            ticker=decision.ticker,
            trade_identity=decision.trade_identity,
            action=decision.action,
            option_strategy_type=decision.option_strategy_type,
            rationale=decision.rationale,
            hedge_cost=Decimal(str(decision.hedge_cost)),
            protected_notional=Decimal(str(decision.protected_notional)),
            metadata_json=dict(decision.metadata_json),
            created_at=decision.created_at,
        )
        self.session.add(row)
        self.session.flush()
