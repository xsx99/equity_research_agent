"""Compatibility shim for intraday rebalance orchestration."""
from __future__ import annotations

import sys

from src.trading.phases.intraday import rebalance as _canonical

AgentRunner = _canonical.AgentRunner
IntradayRebalanceDecisionRecord = _canonical.IntradayRebalanceDecisionRecord
IntradayRebalancePipeline = _canonical.IntradayRebalancePipeline
IntradayRebalancePipelineResult = _canonical.IntradayRebalancePipelineResult
IntradayRebalanceRequest = _canonical.IntradayRebalanceRequest
_binding_constraint = _canonical._binding_constraint
_execution_summary = _canonical._execution_summary
_generated_hedge_action = _canonical._generated_hedge_action
_lookahead_risk_source = _canonical._lookahead_risk_source
_matching_planner_position_action = _canonical._matching_planner_position_action
_normalize_intraday_rebalance_output_candidate = _canonical._normalize_intraday_rebalance_output_candidate
_repair_prompt = _canonical._repair_prompt

__all__ = [
    "AgentRunner",
    "IntradayRebalanceDecisionRecord",
    "IntradayRebalancePipeline",
    "IntradayRebalancePipelineResult",
    "IntradayRebalanceRequest",
    "_binding_constraint",
    "_execution_summary",
    "_generated_hedge_action",
    "_lookahead_risk_source",
    "_matching_planner_position_action",
    "_normalize_intraday_rebalance_output_candidate",
    "_repair_prompt",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
