"""Pydantic contracts for PR05 trading decisions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DecisionLiteral = Literal[
    "enter_long",
    "enter_short",
    "hold",
    "reduce",
    "exit",
    "no_trade",
    "open_option_strategy",
    "close_option_strategy",
    "roll_option_strategy",
    "adjust_option_strategy",
    "avoid_event_option",
]
InstrumentTypeLiteral = Literal["stock", "option", "watch"]
SelectionSourceLiteral = Literal["scanner", "manual_request", "watchlist_pin"]
TradeIdentityLiteral = Literal[
    "core_holding",
    "tactical_stock_trade",
    "tactical_option_trade",
    "risk_hedge_overlay",
    "watch_only",
]
FallbackActionLiteral = Literal["no_trade", "hold"]


class TradingDecisionInput(BaseModel):
    """Validated input payload passed into the PR05 trading agent."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    strategy_id: str
    expression_bucket_id: str
    trade_identity: TradeIdentityLiteral
    instrument_type: InstrumentTypeLiteral
    selection_source: SelectionSourceLiteral
    manual_request_id: str | None = None
    manual_request_mode: Literal["review_only", "paper_trade_eligible"] | None = None
    decision_time: datetime
    available_for_decision_at: datetime
    has_existing_position: bool = False
    candidate_score: float = Field(ge=0, le=1)
    classification_result_status: str | None = None
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
    confidence_basis: dict[str, Any] = Field(default_factory=dict)
    risk_context: dict[str, Any] = Field(default_factory=dict)
    source_availability: dict[str, Any] = Field(default_factory=dict)
    historical_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    selected_strategy_context: dict[str, Any] = Field(default_factory=dict)

    @property
    def fallback_action(self) -> FallbackActionLiteral:
        return "hold" if self.has_existing_position else "no_trade"


class TradingDecisionOutput(BaseModel):
    """Validated structured decision emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    decision: DecisionLiteral
    strategy_id: str
    expression_bucket_id: str
    trade_identity: TradeIdentityLiteral
    instrument_type: InstrumentTypeLiteral
    selection_source: SelectionSourceLiteral
    manual_request_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_basis: dict[str, Any] = Field(default_factory=dict)
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
    target_weight: float = Field(ge=0, le=1)
    max_loss_pct: float = Field(ge=0, le=1)
    time_horizon: str
    entry_plan: str
    exit_plan: str
    thesis: str
    key_signals: list[str] = Field(default_factory=list)
    risk_checks: list[str] = Field(default_factory=list)
    invalidators: list[str] = Field(default_factory=list)
    learning_factors_used: list[str] = Field(default_factory=list)
    schema_version: str
    generated_at: datetime


class TradingDecisionOutputFallback(BaseModel):
    """Safe fallback artifact persisted when the LLM output is unusable."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    decision: Literal["no_trade", "hold"]
    fallback_action: FallbackActionLiteral
    fallback_reason: str
    schema_version: str
    generated_at: datetime
