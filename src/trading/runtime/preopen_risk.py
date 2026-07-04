"""Compatibility shim for preopen risk assembly."""
from __future__ import annotations

import sys

from src.trading.phases.preopen import risk as _canonical

_LiveRiskWorkflow = _canonical._LiveRiskWorkflow
_build_preopen_calendar_events = _canonical._build_preopen_calendar_events
_build_preopen_event_assessments = _canonical._build_preopen_event_assessments
_build_preopen_option_risk_input = _canonical._build_preopen_option_risk_input
_build_trade_risk_request = _canonical._build_trade_risk_request
_classification_instrument_type = _canonical._classification_instrument_type
_earnings_date = _canonical._earnings_date
_earnings_in_days = _canonical._earnings_in_days
_evaluate_with_optional_lookahead = _canonical._evaluate_with_optional_lookahead
_latest_option_contracts = _canonical._latest_option_contracts
_latest_price_from_sources = _canonical._latest_price_from_sources
_option_price_proxy = _canonical._option_price_proxy
_preopen_option_strategy_payload = _canonical._preopen_option_strategy_payload
_sector_from_snapshot = _canonical._sector_from_snapshot

__all__ = [
    "_LiveRiskWorkflow",
    "_build_preopen_calendar_events",
    "_build_preopen_event_assessments",
    "_build_preopen_option_risk_input",
    "_build_trade_risk_request",
    "_classification_instrument_type",
    "_earnings_date",
    "_earnings_in_days",
    "_evaluate_with_optional_lookahead",
    "_latest_option_contracts",
    "_latest_price_from_sources",
    "_option_price_proxy",
    "_preopen_option_strategy_payload",
    "_sector_from_snapshot",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
