"""Risk management ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.db.models.base import Base
from src.db.models.trading.enums import *

class PositionSizingDecision(Base):
    """Deterministic position sizing output before final risk approval."""

    __tablename__ = "position_sizing_decisions"

    position_sizing_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    risk_appetite = Column(String(32), nullable=False, index=True)
    base_weight = Column(Numeric, nullable=False)
    volatility_adjusted_weight = Column(Numeric, nullable=False)
    liquidity_capped_weight = Column(Numeric, nullable=False)
    final_weight = Column(Numeric, nullable=False)
    final_notional = Column(Numeric, nullable=False)
    applied_caps_json = Column(JSONB, nullable=False, default=list)
    binding_constraint = Column(String(128), nullable=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    risk_decisions = relationship("RiskDecision", back_populates="position_sizing_decision")

    __table_args__ = (
        CheckConstraint(
            f"risk_appetite IN {RiskAppetite.check_in_sql()}",
            name="ck_position_sizing_decisions_risk_appetite",
        ),
        CheckConstraint(
            "base_weight >= 0 AND base_weight <= 1 "
            "AND volatility_adjusted_weight >= 0 AND volatility_adjusted_weight <= 1 "
            "AND liquidity_capped_weight >= 0 AND liquidity_capped_weight <= 1 "
            "AND final_weight >= 0 AND final_weight <= 1",
            name="ck_position_sizing_decisions_weight_range",
        ),
    )

class PortfolioRiskSnapshot(Base):
    """Account-level risk snapshot persisted before later order wiring."""

    __tablename__ = "portfolio_risk_snapshots"

    portfolio_risk_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_appetite = Column(String(32), nullable=False, index=True)
    resolver_version = Column(String(64), nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    account_equity = Column(Numeric, nullable=False)
    cash_balance = Column(Numeric, nullable=False)
    buying_power = Column(Numeric, nullable=False)
    excess_liquidity = Column(Numeric, nullable=False)
    stock_margin_requirement = Column(Numeric, nullable=False)
    option_margin_requirement = Column(Numeric, nullable=False)
    total_margin_requirement = Column(Numeric, nullable=False)
    initial_margin_requirement = Column(Numeric, nullable=True)
    maintenance_margin_requirement = Column(Numeric, nullable=True)
    margin_requirement_source = Column(String(64), nullable=False)
    net_exposure = Column(Numeric, nullable=False)
    gross_exposure = Column(Numeric, nullable=False)
    beta_adjusted_net_exposure = Column(Numeric, nullable=False)
    concentration_flags_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_intents = relationship("PortfolioRiskIntent", back_populates="portfolio_risk_snapshot")
    portfolio_event_risk_assessments = relationship(
        "PortfolioEventRiskAssessment",
        back_populates="portfolio_risk_snapshot",
    )
    risk_factor_exposures = relationship("RiskFactorExposure", back_populates="portfolio_risk_snapshot")
    risk_decisions = relationship("RiskDecision", back_populates="portfolio_risk_snapshot")

    __table_args__ = (
        CheckConstraint(
            f"risk_appetite IN {RiskAppetite.check_in_sql()}",
            name="ck_portfolio_risk_snapshots_risk_appetite",
        ),
    )

class PortfolioRiskIntent(Base):
    """Persisted lookahead risk intent emitted before final risk approvals."""

    __tablename__ = "portfolio_risk_intents"

    portfolio_risk_intent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_window = Column(String(32), nullable=False)
    aggregate_risk_state = Column(String(32), nullable=False, index=True)
    position_actions_json = Column(JSONB, nullable=False, default=list)
    hedge_actions_json = Column(JSONB, nullable=False, default=list)
    binding_constraints_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="portfolio_risk_intents")

class RiskFactorExposure(Base):
    """Approximate factor concentration snapshot."""

    __tablename__ = "risk_factor_exposures"

    risk_factor_exposure_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    factor_type = Column(String(64), nullable=False, index=True)
    factor_value = Column(String(128), nullable=False, index=True)
    gross_exposure = Column(Numeric, nullable=False)
    net_exposure = Column(Numeric, nullable=False)
    long_exposure = Column(Numeric, nullable=False)
    short_exposure = Column(Numeric, nullable=False)
    position_count = Column(Integer, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="risk_factor_exposures")

    __table_args__ = (
        CheckConstraint("position_count >= 0", name="ck_risk_factor_exposures_position_count"),
        Index("ix_risk_factor_exposures_type_value", "factor_type", "factor_value"),
    )

class RiskDecision(Base):
    """Final deterministic risk outcome for one candidate/trade request."""

    __tablename__ = "risk_decisions"

    risk_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_score_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate_scores.candidate_score_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trade_classifications.trade_classification_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position_sizing_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("position_sizing_decisions.position_sizing_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    portfolio_risk_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_risk_snapshots.portfolio_risk_snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    reason_code = Column(String(128), nullable=False, index=True)
    approved_weight = Column(Numeric, nullable=False)
    approved_notional = Column(Numeric, nullable=False)
    approved_quantity = Column(Numeric, nullable=False)
    applied_rules_json = Column(JSONB, nullable=False, default=list)
    generated_hedge_action_json = Column(JSONB, nullable=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    position_sizing_decision = relationship("PositionSizingDecision", back_populates="risk_decisions")
    portfolio_risk_snapshot = relationship("PortfolioRiskSnapshot", back_populates="risk_decisions")

    __table_args__ = (
        CheckConstraint(
            f"status IN {RiskDecisionStatus.check_in_sql()}",
            name="ck_risk_decisions_status",
        ),
        CheckConstraint(
            "approved_weight >= 0 AND approved_weight <= 1",
            name="ck_risk_decisions_weight_range",
        ),
    )

class OptionRiskSnapshot(Base):
    """Persisted strategy-level option risk snapshot."""

    __tablename__ = "option_risk_snapshots"

    option_risk_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    underlying_price = Column(Numeric, nullable=False)
    portfolio_delta = Column(Numeric, nullable=False)
    portfolio_gamma = Column(Numeric, nullable=False)
    portfolio_theta = Column(Numeric, nullable=False)
    portfolio_vega = Column(Numeric, nullable=False)
    net_debit_or_credit = Column(Numeric, nullable=False)
    max_loss = Column(Numeric, nullable=False)
    max_profit = Column(Numeric, nullable=True)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    worst_case_assignment_notional = Column(Numeric, nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    risk_status = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class RiskHedgeDecision(Base):
    """Persisted paper-only risk hedge overlay decision."""

    __tablename__ = "risk_hedge_decisions"

    risk_hedge_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    risk_decision_id = Column(UUID(as_uuid=True), ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    rationale = Column(Text, nullable=False)
    hedge_cost = Column(Numeric, nullable=False)
    protected_notional = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
