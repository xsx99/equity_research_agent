"""Pydantic input/output schemas for the research agent."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResearchPriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_price: Optional[float] = None
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_since_market_open: Optional[float] = None


class ResearchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector: Optional[str] = None
    company_name: Optional[str] = None
    earnings_in_days: Optional[int] = None


class ResearchFundamentals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pe_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    short_interest_pct_float: Optional[float] = None


class ResearchVolumeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_volume: Optional[int] = None
    avg_volume_20d: Optional[float] = None
    relative_volume: Optional[float] = None


class ResearchMomentumSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rsi_14: Optional[float] = None
    rsi_3: Optional[float] = None


class ResearchVolatilitySignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atr_14: Optional[float] = None
    yesterday_range: Optional[float] = None
    atr_multiple: Optional[float] = None


class ResearchTechnicalSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    momentum: ResearchMomentumSignals = Field(default_factory=ResearchMomentumSignals)
    volatility: ResearchVolatilitySignals = Field(default_factory=ResearchVolatilitySignals)


class ResearchNewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    published_at: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    signal_type: Optional[str] = None


class ResearchInsiderTradeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insider_name: str
    insider_title: Optional[str] = None
    transaction_type: Optional[str] = None
    transaction_date: Optional[str] = None
    filing_date: Optional[str] = None
    shares: Optional[int] = None
    price_per_share: Optional[float] = None
    total_value: Optional[float] = None
    filing_url: Optional[str] = None


class ResearchInsiderActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: Optional[int] = None
    purchase_count: int = 0
    sale_count: int = 0
    net_shares: Optional[float] = None
    net_value: Optional[float] = None
    recent_trades: list[ResearchInsiderTradeItem] = Field(default_factory=list, max_length=5)


class ResearchGlobalIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    source: str
    unit: str
    value: Optional[float] = None
    observed_on: Optional[str] = None


class ResearchGlobalEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    title: str
    summary: str = ""
    published_at: Optional[str] = None
    url: Optional[str] = None


class ResearchGlobalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: Any = None
    indicators: dict[str, ResearchGlobalIndicator] = Field(default_factory=dict)
    official_updates: list[ResearchGlobalEventItem] = Field(default_factory=list, max_length=5)
    trump_updates: list[ResearchGlobalEventItem] = Field(default_factory=list, max_length=5)
    geopolitical_news: list[ResearchGlobalEventItem] = Field(default_factory=list, max_length=5)


class ResearchInputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: Any  # datetime — kept as Any to accept both datetime and ISO string
    price_snapshot: ResearchPriceSnapshot
    context: ResearchContext = Field(default_factory=ResearchContext)
    fundamentals: ResearchFundamentals = Field(default_factory=ResearchFundamentals)
    volume_snapshot: ResearchVolumeSnapshot = Field(default_factory=ResearchVolumeSnapshot)
    technical_signals: ResearchTechnicalSignals = Field(default_factory=ResearchTechnicalSignals)
    news: list[ResearchNewsItem] = Field(default_factory=list, max_length=5)
    insider_activity: ResearchInsiderActivity = Field(default_factory=ResearchInsiderActivity)
    global_context: ResearchGlobalContext = Field(default_factory=ResearchGlobalContext)


class StructuredResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["bullish", "bearish", "neutral", "abstain"]
    confidence: float = Field(ge=0, le=1)
    time_horizon: Literal["1d"]
    time_horizon_rationale: Optional[str] = None
    actionability: Literal["abstain", "watch", "actionable"]
    thesis_summary: str = Field(min_length=1)
    key_drivers: list[str]
    counterarguments: list[str]
    invalidators: list[str]
