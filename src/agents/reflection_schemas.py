"""Pydantic contracts for PR09 reflection and learning factors."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


LearningFactorScope = Literal["strategy", "portfolio", "trade", "watchlist", "risk"]
ActivationPolicy = Literal["candidate", "observation", "shadow", "auto_risk_tightening"]
ReflectionFallbackAction = Literal["reflection_failed"]


class ReflectionLearningFactorInput(BaseModel):
    """Structured learning-factor proposal emitted by reflection."""

    model_config = ConfigDict(extra="forbid")

    factor_type: str
    scope: LearningFactorScope
    title: str
    strategy_id: str | None = None
    condition: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    activation_policy: ActivationPolicy
    effect_tags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ReflectionAttributionItem(BaseModel):
    """Attribution row for what worked or failed."""

    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    result: str
    root_cause: str
    evidence: list[str] = Field(default_factory=list)


class ReflectionInput(BaseModel):
    """Validated reflection payload passed into the PR09 reflection agent."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    decision_time: datetime
    available_for_decision_at: datetime
    portfolio_outcome: dict[str, Any] = Field(default_factory=dict)
    morning_macro_snapshot: dict[str, Any] = Field(default_factory=dict)
    strategy_candidates: list[dict[str, Any]] = Field(default_factory=list)
    manual_ticker_requests: list[dict[str, Any]] = Field(default_factory=list)
    trading_decisions: list[dict[str, Any]] = Field(default_factory=list)
    rejected_decisions: list[dict[str, Any]] = Field(default_factory=list)
    intraday_news_alerts: list[dict[str, Any]] = Field(default_factory=list)
    intraday_rebalance_decisions: list[dict[str, Any]] = Field(default_factory=list)
    paper_orders: list[dict[str, Any]] = Field(default_factory=list)
    paper_executions: list[dict[str, Any]] = Field(default_factory=list)
    risk_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    risk_factor_exposures: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    candidate_outcome_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    benchmark_peer_returns: dict[str, Any] = Field(default_factory=dict)
    paper_option_decisions: list[dict[str, Any]] = Field(default_factory=list)
    paper_option_positions: list[dict[str, Any]] = Field(default_factory=list)
    option_risk_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    worst_case_assignment_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    risk_hedge_overlays: list[dict[str, Any]] = Field(default_factory=list)
    hedge_effectiveness: dict[str, Any] = Field(default_factory=dict)
    learning_factors_used: list[dict[str, Any] | str] = Field(default_factory=list)


class ReflectionOutput(BaseModel):
    """Validated reflection output emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    portfolio_summary: dict[str, Any] = Field(default_factory=dict)
    what_worked: list[str] = Field(default_factory=list)
    what_failed: list[str] = Field(default_factory=list)
    attribution: list[ReflectionAttributionItem] = Field(default_factory=list)
    learning_factors: list[ReflectionLearningFactorInput] = Field(default_factory=list)
    strategy_proposal_hints: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str
    generated_at: datetime


class ReflectionOutputFallback(BaseModel):
    """Safe fallback artifact persisted when the LLM output is unusable."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    reflection_status: Literal["reflection_failed"]
    fallback_action: ReflectionFallbackAction
    fallback_reason: str
    schema_version: str
    generated_at: datetime
