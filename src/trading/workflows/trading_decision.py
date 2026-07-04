"""PR05 trading decision workflow."""
from __future__ import annotations

from src.trading.decision.pipeline import (
    TradingDecisionPipeline,
    TradingDecisionPipelineResult,
    TradingDecisionRecord,
    _WINDOWED_EVENT_NEWS_FIELDS,
    _build_option_strategy_payloads,
    _classification_instrument_type,
    _collapse_missing_signals_for_llm,
    _evidence_priority,
    _news_evidence_limit,
    _render_news_source_text,
    _resolve_expression_fallback_plan,
    _round_nested_floats,
)


__all__ = [
    "TradingDecisionPipeline",
    "TradingDecisionPipelineResult",
    "TradingDecisionRecord",
    "_WINDOWED_EVENT_NEWS_FIELDS",
    "_build_option_strategy_payloads",
    "_classification_instrument_type",
    "_collapse_missing_signals_for_llm",
    "_evidence_priority",
    "_news_evidence_limit",
    "_render_news_source_text",
    "_resolve_expression_fallback_plan",
    "_round_nested_floats",
]
