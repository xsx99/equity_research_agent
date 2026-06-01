"""Portfolio-pool trade identity classification for selected PR03 candidates."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from src.trading.portfolio_intents import PortfolioIntentConfig, is_core_holding_approved
from src.trading.primary_strategy_selector import SelectedStrategyRecord


@dataclass(frozen=True)
class TradeClassificationRecord:
    """Persistable trade identity and selected strategy context."""

    trade_classification_id: str
    candidate_score_id: str
    strategy_run_id: str
    ticker: str
    selected_strategy_id: str
    selected_strategy_version: str
    expression_bucket_id: str
    expression_bucket_version: str
    trade_identity: str
    watch_type: str | None
    direction: str
    intended_horizon: str
    exit_policy: str
    result_status: str
    classification_reason: str
    selected_strategy_context_json: dict[str, Any]
    decision_time: datetime


class TradeClassifier:
    """Classify selected candidates into portfolio-pool identities."""

    def __init__(self, portfolio_intents: Iterable[PortfolioIntentConfig] = ()) -> None:
        self.portfolio_intents = tuple(portfolio_intents)

    def classify(self, selected: SelectedStrategyRecord) -> TradeClassificationRecord:
        candidate = selected.candidate
        default_identity = selected.expression_bucket_config.get("default_trade_identity") or "tactical_stock_trade"
        if default_identity == "risk_hedge_overlay":
            raise ValueError("risk_hedge_overlay_is_risk_manager_owned")

        trade_identity = str(default_identity)
        watch_type: str | None = None
        result_status = "actionable_trade"
        reason = "selected candidate is eligible for the expression bucket"

        if candidate.rejection_reason is not None:
            trade_identity = "watch_only"
            watch_type, result_status, reason = _watch_state_for_rejection(candidate)
        elif trade_identity == "core_holding" and not is_core_holding_approved(candidate.ticker, self.portfolio_intents):
            trade_identity = "watch_only"
            watch_type = "ordinary_watch"
            result_status = "no_trade"
            reason = "core_holding requires an active portfolio intent"
        elif trade_identity == "tactical_option_trade":
            trade_identity = "watch_only"
            watch_type = "catalyst_watch" if _has_high_move_potential(candidate) else "ordinary_watch"
            result_status = watch_type
            reason = "option-chain strategy data is deferred until a later PR"

        return TradeClassificationRecord(
            trade_classification_id=str(uuid.uuid4()),
            candidate_score_id=candidate.candidate_score_id,
            strategy_run_id=candidate.strategy_run_id,
            ticker=candidate.ticker,
            selected_strategy_id=candidate.strategy_id,
            selected_strategy_version=candidate.strategy_version,
            expression_bucket_id=selected.expression_bucket_id,
            expression_bucket_version=selected.expression_bucket_version,
            trade_identity=trade_identity,
            watch_type=watch_type,
            direction=candidate.direction,
            intended_horizon=candidate.typical_horizon,
            exit_policy=str(
                selected.expression_bucket_config.get("default_exit_policy")
                or "strategy_invalidators_or_target_horizon"
            ),
            result_status=result_status,
            classification_reason=reason,
            selected_strategy_context_json={
                **selected.selection_context,
                "core_signal_evidence": dict(candidate.core_signal_evidence),
                "invalidators": list(candidate.invalidators),
                "risk_tags": list(candidate.risk_tags),
                "benchmark_context": dict(candidate.benchmark_context),
            },
            decision_time=candidate.decision_time,
        )

    def classify_many(self, selected: Iterable[SelectedStrategyRecord]) -> list[TradeClassificationRecord]:
        """Classify a batch of selected strategies."""
        return [self.classify(item) for item in selected]


def _watch_state_for_rejection(candidate: Any) -> tuple[str, str, str]:
    if candidate.rejection_reason == "unsupported_missing_signal_family":
        return "ordinary_watch", "blocked_by_missing_data", "required source family is missing or unsupported"
    if candidate.rejection_reason == "no_clean_entry" and _has_high_move_potential(candidate):
        return "catalyst_watch", "catalyst_watch", "move potential is high but direction or entry is uncertain"
    if candidate.rejection_reason == "direct_negative_catalyst":
        return "ordinary_watch", "no_trade", "direct negative catalyst blocks the candidate"
    return "ordinary_watch", "ordinary_watch", "candidate is not actionable"


def _has_high_move_potential(candidate: Any) -> bool:
    catalyst_quality = candidate.core_signal_evidence.get("events_news.catalyst_quality_score")
    high_signal_count = candidate.core_signal_evidence.get("events_news.high_signal_news_count_24h")
    return (
        isinstance(catalyst_quality, (int, float))
        and catalyst_quality >= 0.75
    ) or (
        isinstance(high_signal_count, (int, float))
        and high_signal_count >= 1
        and candidate.candidate_score >= 0.55
    )
