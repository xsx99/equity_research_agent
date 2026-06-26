"""Replay, reflection, and learning ORM models."""
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

class HistoricalReplayRun(Base):
    """Deterministic replay batch metadata."""

    __tablename__ = "historical_replay_runs"

    historical_replay_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    decision_filter_json = Column(JSONB, nullable=False, default=dict)
    outcome_horizon_policy_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    outcome_evaluations = relationship("CandidateOutcomeEvaluation", back_populates="historical_replay_run")

    __table_args__ = (
        CheckConstraint(
            "snapshot_type IN ('pre_open', 'intraday')",
            name="ck_historical_replay_runs_snapshot_type",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_historical_replay_runs_status",
        ),
    )

class CandidateOutcomeEvaluation(Base):
    """Outcome attribution for candidates, trades, rejected rows, and watch items."""

    __tablename__ = "candidate_outcome_evaluations"

    candidate_outcome_evaluation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    historical_replay_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("historical_replay_runs.historical_replay_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    strategy_id = Column(String(64), nullable=False, index=True)
    strategy_version = Column(String(16), nullable=False)
    expression_bucket_id = Column(String(64), nullable=False, index=True)
    trade_identity = Column(String(64), nullable=False, index=True)
    direction = Column(String(32), nullable=False, index=True)
    catalyst_type = Column(String(128), nullable=True, index=True)
    confidence_bucket = Column(String(255), nullable=False, index=True)
    decision_time = Column(DateTime(timezone=True), nullable=False, index=True)
    horizon_start_at = Column(DateTime(timezone=True), nullable=False)
    horizon_end_at = Column(DateTime(timezone=True), nullable=False, index=True)
    evaluation_status = Column(String(32), nullable=False, index=True)
    candidate_return = Column(Numeric, nullable=True)
    benchmark_returns_json = Column(JSONB, nullable=False, default=dict)
    peer_basket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("peer_baskets.peer_basket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    peer_basket_return = Column(Numeric, nullable=True)
    alpha = Column(Numeric, nullable=True)
    max_favorable_excursion = Column(Numeric, nullable=True)
    max_adverse_excursion = Column(Numeric, nullable=True)
    regime = Column(String(64), nullable=True, index=True)
    sector_theme = Column(String(128), nullable=True, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    historical_replay_run = relationship("HistoricalReplayRun", back_populates="outcome_evaluations")
    candidate_score = relationship("CandidateScore", back_populates="outcome_evaluations")
    trade_classification = relationship("TradeClassification", back_populates="outcome_evaluations")
    peer_basket = relationship("PeerBasket")

    __table_args__ = (
        CheckConstraint(
            f"trade_identity IN {TradeIdentity.check_in_sql()}",
            name="ck_candidate_outcome_evaluations_trade_identity",
        ),
        CheckConstraint(
            f"evaluation_status IN {CandidateOutcomeEvaluationStatus.check_in_sql()}",
            name="ck_candidate_outcome_evaluations_status",
        ),
        CheckConstraint(
            "horizon_end_at >= horizon_start_at",
            name="ck_candidate_outcome_evaluations_horizon_window",
        ),
        Index("ix_candidate_outcomes_strategy_bucket", "strategy_id", "confidence_bucket"),
        Index("ix_candidate_outcomes_ticker_horizon", "ticker", "horizon_end_at"),
    )

class DailyReflection(Base):
    """Persisted post-close reflection artifact and structured output."""

    __tablename__ = "daily_reflections"

    daily_reflection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_date = Column(Date, nullable=False, unique=True, index=True)
    prompt_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_prompt_runs.prompt_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(16), nullable=False, index=True)
    portfolio_summary_json = Column(JSONB, nullable=False, default=dict)
    reflection_json = Column(JSONB, nullable=False, default=dict)
    strategy_proposal_hints_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    prompt_run = relationship("LlmPromptRun")
    learning_factors = relationship("LearningFactor", back_populates="daily_reflection")

    __table_args__ = (
        CheckConstraint(
            f"status IN {DailyReflectionStatus.check_in_sql()}",
            name="ck_daily_reflections_status",
        ),
    )

class LearningFactor(Base):
    """Persisted structured lesson extracted from daily reflection."""

    __tablename__ = "learning_factors"

    learning_factor_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factor_key = Column(String(64), nullable=False, unique=True, index=True)
    daily_reflection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("daily_reflections.daily_reflection_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trade_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    factor_type = Column(String(64), nullable=False, index=True)
    scope = Column(String(32), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=True, index=True)
    condition = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    confidence = Column(Numeric, nullable=False)
    activation_policy = Column(String(32), nullable=False)
    effect_tags_json = Column(JSONB, nullable=False, default=list)
    evidence_json = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    daily_reflection = relationship("DailyReflection", back_populates="learning_factors")

    __table_args__ = (
        CheckConstraint(
            "scope IN ('strategy', 'portfolio', 'trade', 'watchlist', 'risk')",
            name="ck_learning_factors_scope",
        ),
        CheckConstraint(
            f"status IN {LearningFactorStatus.check_in_sql()}",
            name="ck_learning_factors_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_learning_factors_confidence_range",
        ),
    )
