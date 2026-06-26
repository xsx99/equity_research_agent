"""Trading execution and portfolio ORM models."""
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

class TradingDecision(Base):
    """Persisted PR05 trading decision artifact before any paper-order wiring."""

    __tablename__ = "trading_decisions"

    trading_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    risk_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    decision = Column(String(64), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    expression_bucket_version = Column(String(16), nullable=False)
    trade_identity = Column(String(64), nullable=False, index=True)
    instrument_type = Column(String(32), nullable=False)
    selection_source = Column(String(32), nullable=False, index=True)
    manual_request_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    confidence = Column(Numeric, nullable=False)
    target_weight = Column(Numeric, nullable=False)
    approved_weight = Column(Numeric, nullable=False)
    max_loss_pct = Column(Numeric, nullable=False)
    time_horizon = Column(String(32), nullable=False)
    thesis = Column(Text, nullable=False)
    key_drivers_json = Column(JSONB, nullable=False, default=list)
    counterarguments_json = Column(JSONB, nullable=False, default=list)
    invalidators_json = Column(JSONB, nullable=False, default=list)
    fallback_action = Column(String(64), nullable=True)
    paper_trade_authorized = Column(Boolean, nullable=False, default=False, server_default="false")
    context_snapshot_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    available_for_decision_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate_score = relationship("CandidateScore")
    trade_classification = relationship("TradeClassification")
    risk_decision = relationship("RiskDecision")
    prompt_run = relationship("LlmPromptRun")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('enter_long', 'enter_short', 'hold', 'reduce', 'exit', "
            "'no_trade', 'open_option_strategy', 'close_option_strategy', "
            "'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_trading_decisions_decision",
        ),
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_trading_decisions_trade_identity",
        ),
        CheckConstraint(
            "instrument_type IN ('stock', 'option', 'watch')",
            name="ck_trading_decisions_instrument_type",
        ),
        CheckConstraint(
            "selection_source IN ('scanner', 'manual_request', 'watchlist_pin', 'risk_manager')",
            name="ck_trading_decisions_selection_source",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1 "
            "AND target_weight >= 0 AND target_weight <= 1 "
            "AND approved_weight >= 0 AND approved_weight <= 1 "
            "AND max_loss_pct >= 0 AND max_loss_pct <= 1",
            name="ck_trading_decisions_weight_ranges",
        ),
        Index("ix_trading_decisions_ticker_decision_time", "ticker", "decision_time"),
    )

class PaperOrder(Base):
    """Paper stock order staged from a validated trading decision and risk approval."""

    __tablename__ = "paper_orders"

    paper_order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_order_id = Column(String(128), nullable=True, index=True)
    client_order_id = Column(String(255), nullable=False)
    trading_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    risk_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric, nullable=False)
    order_price = Column(Numeric, nullable=True)
    status = Column(String(32), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    trading_decision = relationship("TradingDecision")
    risk_decision = relationship("RiskDecision")
    executions = relationship("PaperExecution", back_populates="paper_order")

    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_paper_orders_client_order_id"),
        CheckConstraint(
            "action IN ('enter_long', 'enter_short', 'reduce', 'exit')",
            name="ck_paper_orders_action",
        ),
        CheckConstraint(
            "status IN ('new', 'accepted', 'pending_new', 'partially_filled', 'filled', "
            "'canceled', 'expired', 'rejected')",
            name="ck_paper_orders_status",
        ),
    )

class PaperExecution(Base):
    """Paper fill record for a stock order."""

    __tablename__ = "paper_executions"

    paper_execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paper_orders.paper_order_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    broker_order_id = Column(String(128), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    quantity = Column(Numeric, nullable=False)
    fill_price = Column(Numeric, nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    net_cash_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    paper_order = relationship("PaperOrder", back_populates="executions")

class PaperPosition(Base):
    """Open or closed stock position in the unified paper margin account."""

    __tablename__ = "paper_positions"

    paper_position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=True, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    direction = Column(String(16), nullable=False, default="long", server_default="long")
    quantity = Column(Numeric, nullable=False)
    average_cost = Column(Numeric, nullable=False)
    market_price = Column(Numeric, nullable=False)
    market_value = Column(Numeric, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_paper_positions_trade_identity",
        ),
        CheckConstraint(
            "direction IN ('long', 'short')",
            name="ck_paper_positions_direction",
        ),
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="ck_paper_positions_status",
        ),
    )

class PortfolioSnapshot(Base):
    """Unified simulated margin-account snapshot after stock paper executions."""

    __tablename__ = "portfolio_snapshots"

    portfolio_snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_time = Column(DateTime(timezone=True), nullable=False, index=True)
    cash_balance = Column(Numeric, nullable=False)
    account_equity = Column(Numeric, nullable=False)
    net_liquidation_value = Column(Numeric, nullable=False)
    buying_power = Column(Numeric, nullable=False)
    excess_liquidity = Column(Numeric, nullable=False)
    stock_market_value = Column(Numeric, nullable=False)
    option_market_value = Column(Numeric, nullable=False)
    stock_margin_requirement = Column(Numeric, nullable=False)
    option_margin_requirement = Column(Numeric, nullable=False)
    total_margin_requirement = Column(Numeric, nullable=False)
    initial_margin_requirement = Column(Numeric, nullable=False)
    maintenance_margin_requirement = Column(Numeric, nullable=False)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    day_pnl = Column(Numeric, nullable=False)
    realized_pnl = Column(Numeric, nullable=False)
    unrealized_pnl = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class OptionStrategyDecision(Base):
    """Persisted PR7 paper option strategy decision."""

    __tablename__ = "option_strategy_decisions"

    option_strategy_decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trading_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    decision_action = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    expression_bucket_version = Column(String(16), nullable=False)
    underlying_price = Column(Numeric, nullable=False)
    expiry = Column(Date, nullable=False, index=True)
    net_debit_or_credit = Column(Numeric, nullable=False)
    max_loss = Column(Numeric, nullable=False)
    max_profit = Column(Numeric, nullable=True)
    breakevens_json = Column(JSONB, nullable=False, default=list)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    portfolio_delta = Column(Numeric, nullable=False)
    portfolio_gamma = Column(Numeric, nullable=False)
    portfolio_theta = Column(Numeric, nullable=False)
    portfolio_vega = Column(Numeric, nullable=False)
    earnings_date = Column(Date, nullable=True)
    event_through_expiry = Column(Boolean, nullable=False, default=False, server_default="false")
    strategy_pairing_method = Column(String(64), nullable=False)
    assignment_plan = Column(Text, nullable=True)
    margin_model_profile = Column(String(128), nullable=False)
    margin_model_version = Column(String(32), nullable=False)
    margin_requirement_source = Column(String(64), nullable=False)
    profit_target_pct = Column(Numeric, nullable=False)
    max_loss_rule = Column(String(128), nullable=False)
    roll_conditions_json = Column(JSONB, nullable=False, default=list)
    close_conditions_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_option_strategy_decisions_trade_identity",
        ),
        CheckConstraint(
            "decision_action IN ('open_option_strategy', 'close_option_strategy', 'roll_option_strategy', 'adjust_option_strategy', 'avoid_event_option')",
            name="ck_option_strategy_decisions_action",
        ),
        CheckConstraint(
            "option_strategy_type IN ('long_call', 'long_put', 'put_credit_spread', 'call_credit_spread', 'long_straddle', 'long_strangle')",
            name="ck_option_strategy_decisions_type",
        ),
        CheckConstraint("status IN ('ready', 'rejected')", name="ck_option_strategy_decisions_status"),
    )

class OptionStrategyLeg(Base):
    """Per-leg option strategy metadata."""

    __tablename__ = "option_strategy_legs"

    option_strategy_leg_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    contract_symbol = Column(String(32), nullable=False, index=True)
    option_type = Column(String(8), nullable=False)
    side = Column(String(8), nullable=False)
    quantity = Column(Integer, nullable=False)
    ratio_qty = Column(Integer, nullable=False, default=1, server_default="1")
    strike = Column(Numeric, nullable=False)
    expiry = Column(Date, nullable=False, index=True)
    dte = Column(Integer, nullable=False)
    delta = Column(Numeric, nullable=False)
    gamma = Column(Numeric, nullable=False)
    theta = Column(Numeric, nullable=False)
    vega = Column(Numeric, nullable=False)
    implied_volatility = Column(Numeric, nullable=True)
    iv_rank = Column(Numeric, nullable=True)
    bid = Column(Numeric, nullable=False)
    ask = Column(Numeric, nullable=False)
    mid = Column(Numeric, nullable=False)
    chosen_price = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class PaperOptionOrder(Base):
    """Paper-only option order state."""

    __tablename__ = "paper_option_orders"

    paper_option_order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trading_decision_id = Column(UUID(as_uuid=True), ForeignKey("trading_decisions.trading_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    risk_decision_id = Column(UUID(as_uuid=True), ForeignKey("risk_decisions.risk_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    broker_order_id = Column(String(128), nullable=True, index=True)
    client_order_id = Column(String(255), nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    order_class = Column(String(16), nullable=False, default="simple", server_default="simple")
    trade_identity = Column(String(64), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Numeric, nullable=False)
    status = Column(String(16), nullable=False, index=True)
    rejection_reason = Column(String(128), nullable=True)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("client_order_id", name="uq_paper_option_orders_client_order_id"),)

class PaperOptionExecution(Base):
    """Paper-only option fill record."""

    __tablename__ = "paper_option_executions"

    paper_option_execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_option_order_id = Column(UUID(as_uuid=True), ForeignKey("paper_option_orders.paper_option_order_id", ondelete="CASCADE"), nullable=False, index=True)
    broker_order_id = Column(String(128), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    fill_price = Column(Numeric, nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    net_cash_effect = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class PaperOptionPosition(Base):
    """Open option strategy state persisted locally."""

    __tablename__ = "paper_option_positions"

    paper_option_position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    option_strategy_decision_id = Column(UUID(as_uuid=True), ForeignKey("option_strategy_decisions.option_strategy_decision_id", ondelete="SET NULL"), nullable=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    option_strategy_type = Column(String(64), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    max_loss = Column(Numeric, nullable=False)
    margin_requirement = Column(Numeric, nullable=False)
    buying_power_effect = Column(Numeric, nullable=False)
    assignment_notional = Column(Numeric, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
