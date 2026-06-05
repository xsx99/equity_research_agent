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
IntradayActionLiteral = Literal[
    "hold",
    "reduce",
    "exit",
    "add",
    "open_new",
    "close_option_strategy",
    "roll_option_strategy",
    "adjust_option_strategy",
    "avoid_event_option",
]


class TradingDecisionInput(BaseModel):
    """Validated input payload passed into the PR05 trading agent."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    decision_time: datetime
    available_for_decision_at: datetime
    has_existing_position: bool = False
    signal_snapshot: dict[str, Any]
    candidate_context: dict[str, Any]
    classification_context: dict[str, Any]
    risk_context: dict[str, Any] = Field(default_factory=dict)
    manual_request_context: dict[str, Any] = Field(default_factory=dict)

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
    key_drivers: list[str]
    counterarguments: list[str]
    risk_checks: list[str] = Field(default_factory=list)
    invalidators: list[str]
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


class IntradayRebalanceInput(BaseModel):
    """Validated input payload passed into the PR08 intraday rebalance agent."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    strategy_id: str
    expression_bucket_id: str
    trade_identity: TradeIdentityLiteral
    instrument_type: InstrumentTypeLiteral
    selection_source: SelectionSourceLiteral
    decision_time: datetime
    available_for_decision_at: datetime
    current_price: float = Field(gt=0)
    atr_pct: float = Field(ge=0)
    average_daily_dollar_volume: float = Field(ge=0)
    existing_position: bool = False
    current_position_quantity: float = Field(ge=0)
    current_position_market_value: float = Field(ge=0)
    candidate_score: float = Field(ge=0, le=1)
    target_weight: float = Field(ge=0, le=1)
    signal_freshness: dict[str, Any] = Field(default_factory=dict)
    delta_vs_baseline_json: dict[str, Any] = Field(default_factory=dict)
    delta_vs_previous_json: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    allow_open_new: bool = False
    direct_company_negative_evidence: bool = False
    bearish_signal_sources: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IntradayRebalanceOutput(BaseModel):
    """Validated structured intraday rebalance decision emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: IntradayActionLiteral
    thesis: str
    confidence: float = Field(ge=0, le=1)
    target_weight: float = Field(ge=0, le=1)
    max_loss_pct: float = Field(ge=0, le=1)
    urgency: Literal["critical", "high", "medium", "low"]
    rationale: list[str] = Field(default_factory=list)
    risk_checks: list[str] = Field(default_factory=list)
    schema_version: str
    generated_at: datetime


class IntradayRebalanceOutputFallback(BaseModel):
    """Safe fallback artifact persisted when intraday LLM output is unusable."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: Literal["hold"]
    fallback_reason: str
    schema_version: str
    generated_at: datetime
