"""Compatibility shim for lookahead risk orchestration helpers."""
from __future__ import annotations

import sys

from src.trading.risk import lookahead_risk as _canonical

LookaheadRiskWorkflowHelper = _canonical.LookaheadRiskWorkflowHelper
_dominant_protected_exposure_basis = _canonical._dominant_protected_exposure_basis
_earnings_in_days = _canonical._earnings_in_days
_hedge_option_strategy_type = _canonical._hedge_option_strategy_type
_hedge_protected_exposure = _canonical._hedge_protected_exposure
_hedge_underlying_price = _canonical._hedge_underlying_price
_intraday_cluster_assessment = _canonical._intraday_cluster_assessment
_intraday_event_assessment = _canonical._intraday_event_assessment
_materialized_protected_notional = _canonical._materialized_protected_notional
_planner_macro_risk_state = _canonical._planner_macro_risk_state
_protected_exposure_basis = _canonical._protected_exposure_basis
_sector_from_baseline = _canonical._sector_from_baseline
_sector_from_snapshot = _canonical._sector_from_snapshot

__all__ = [
    "LookaheadRiskWorkflowHelper",
    "_dominant_protected_exposure_basis",
    "_earnings_in_days",
    "_hedge_option_strategy_type",
    "_hedge_protected_exposure",
    "_hedge_underlying_price",
    "_intraday_cluster_assessment",
    "_intraday_event_assessment",
    "_materialized_protected_notional",
    "_planner_macro_risk_state",
    "_protected_exposure_basis",
    "_sector_from_baseline",
    "_sector_from_snapshot",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
