"""Pydantic contracts for PR10 strategy evolution."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyProposalOutputItem(BaseModel):
    """Structured strategy proposal emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    proposed_strategy_id: str
    display_name: str
    source_reflection_ids: list[str] = Field(default_factory=list)
    supporting_outcome_ids: list[str] = Field(default_factory=list)
    supporting_learning_factor_keys: list[str] = Field(default_factory=list)
    core_thesis: str
    typical_horizon: str
    required_signals: list[str] = Field(default_factory=list)
    optional_signals: list[str] = Field(default_factory=list)
    scoring_rules: dict[str, Any] = Field(default_factory=dict)
    risk_tags: list[str] = Field(default_factory=list)
    macro_blocked_regimes: list[str] = Field(default_factory=list)
    invalidators: list[str] = Field(default_factory=list)
    evidence_summary: str


class StrategyEvolutionInput(BaseModel):
    """Validated payload passed into the PR10 synthesis agent."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    decision_time: datetime
    available_for_decision_at: datetime
    strategy_proposal_hints: list[dict[str, Any]] = Field(default_factory=list)
    candidate_learning_factors: list[dict[str, Any]] = Field(default_factory=list)
    observation_learning_factors: list[dict[str, Any]] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    outcome_performance_summaries: list[dict[str, Any]] = Field(default_factory=list)
    existing_strategies: list[dict[str, Any]] = Field(default_factory=list)


class StrategyEvolutionOutput(BaseModel):
    """Validated proposal synthesis output."""

    model_config = ConfigDict(extra="forbid")

    proposals: list[StrategyProposalOutputItem] = Field(default_factory=list)
    schema_version: str
    generated_at: datetime


class StrategyEvolutionOutputFallback(BaseModel):
    """Safe fallback when synthesis cannot be validated."""

    model_config = ConfigDict(extra="forbid")

    proposals: list[dict[str, Any]] = Field(default_factory=list)
    fallback_action: str = "proposal_failed"
    fallback_reason: str
    schema_version: str
    generated_at: datetime
