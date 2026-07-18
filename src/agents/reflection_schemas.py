"""Pydantic contracts for PR09 reflection and learning factors."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


LearningFactorScope = Literal["strategy", "portfolio", "trade", "watchlist", "risk"]
ActivationPolicy = Literal["candidate", "observation", "shadow", "auto_risk_tightening"]
ReflectionFallbackAction = Literal["reflection_failed"]
_LEARNING_FACTOR_SCOPES = {"strategy", "portfolio", "trade", "watchlist", "risk"}
_CONFIDENCE_LABELS = {"low": 0.3, "medium": 0.5, "high": 0.8}


def _json_summary(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        ticker = value.get("ticker") or value.get("symbol")
        analysis = value.get("analysis") or value.get("summary") or value.get("description")
        if ticker and analysis:
            return f"{ticker}: {analysis}"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _normalize_attribution_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "strategy_id": "portfolio",
            "result": "mixed",
            "root_cause": str(value),
            "evidence": [],
        }
    root_cause = (
        value.get("root_cause")
        or value.get("analysis")
        or value.get("summary")
        or value.get("description")
        or _json_summary(value)
    )
    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        evidence = value.get("drivers") if isinstance(value.get("drivers"), list) else []
    return {
        "strategy_id": str(value.get("strategy_id") or value.get("ticker") or value.get("symbol") or "portfolio"),
        "result": str(value.get("result") or value.get("outcome") or "mixed"),
        "root_cause": str(root_cause),
        "evidence": [str(item) for item in evidence],
    }


def _normalize_object_section(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    return {"value": value}


class ReflectionLearningFactorInput(BaseModel):
    """Structured learning-factor proposal emitted by reflection."""

    model_config = ConfigDict(extra="ignore")

    factor_type: str
    scope: LearningFactorScope
    title: str
    strategy_id: str | None = None
    condition: str
    recommendation: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    activation_policy: ActivationPolicy = "observation"
    effect_tags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_loose_factor(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        description = data.get("description")
        application = data.get("application")
        if not data.get("title"):
            data["title"] = description or data.get("condition") or "Reflection observation"
        if not data.get("factor_type"):
            data["factor_type"] = "observation"
        if data.get("scope") not in _LEARNING_FACTOR_SCOPES:
            data["scope"] = "portfolio"
        if not data.get("condition"):
            data["condition"] = description or data["title"]
        if not data.get("recommendation"):
            data["recommendation"] = application or description or data["title"]
        if not data.get("activation_policy"):
            data["activation_policy"] = "observation"
        return data

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _CONFIDENCE_LABELS.get(value.strip().lower(), value)
        return value


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
    historical_outcome_context: list[dict[str, Any]] = Field(default_factory=list)
    prior_reflection_context: list[dict[str, Any]] = Field(default_factory=list)
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
    portfolio_analysis: dict[str, Any] = Field(default_factory=dict)
    confidence_calibration: dict[str, Any] = Field(default_factory=dict)
    factor_concentration: dict[str, Any] = Field(default_factory=dict)
    candidate_misses: dict[str, Any] = Field(default_factory=dict)
    manual_ticker_requests_evaluation: dict[str, Any] = Field(default_factory=dict)
    what_worked: list[str] = Field(default_factory=list)
    what_failed: list[str] = Field(default_factory=list)
    attribution: list[ReflectionAttributionItem] = Field(default_factory=list)
    learning_factors: list[ReflectionLearningFactorInput] = Field(default_factory=list)
    strategy_proposal_hints: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str
    generated_at: datetime

    @field_validator(
        "portfolio_analysis",
        "confidence_calibration",
        "factor_concentration",
        "candidate_misses",
        "manual_ticker_requests_evaluation",
        mode="before",
    )
    @classmethod
    def normalize_object_sections(cls, value: Any) -> dict[str, Any]:
        return _normalize_object_section(value)

    @field_validator("what_worked", "what_failed", mode="before")
    @classmethod
    def normalize_summary_points(cls, value: Any) -> Any:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        return [_json_summary(item) for item in items]

    @field_validator("attribution", mode="before")
    @classmethod
    def normalize_attribution(cls, value: Any) -> Any:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        return [_normalize_attribution_item(item) for item in items]

    @field_validator("learning_factors", mode="before")
    @classmethod
    def normalize_learning_factors(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict) and isinstance(value.get("factors"), list):
            return value["factors"]
        return value

    @field_validator("strategy_proposal_hints", mode="before")
    @classmethod
    def normalize_strategy_proposal_hints(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


class ReflectionOutputFallback(BaseModel):
    """Safe fallback artifact persisted when the LLM output is unusable."""

    model_config = ConfigDict(extra="forbid")

    trade_date: date
    reflection_status: Literal["reflection_failed"]
    fallback_action: ReflectionFallbackAction
    fallback_reason: str
    schema_version: str
    generated_at: datetime
