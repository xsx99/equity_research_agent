"""Portfolio-pool trade identity classification for selected PR03 candidates."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from src.trading.portfolio.intents import PortfolioIntentConfig, is_core_holding_approved
from src.trading.strategies.selector import SelectedTradeRecord


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

    def classify(self, selected: SelectedTradeRecord) -> TradeClassificationRecord:
        candidate = selected.candidate
        if not candidate.is_actionable:
            raise ValueError("trade_classifier_requires_actionable_selected_trade")

        default_identity = selected.expression_bucket_config.get("default_trade_identity") or "tactical_stock_trade"
        if default_identity == "risk_hedge_overlay":
            raise ValueError("risk_hedge_overlay_is_risk_manager_owned")

        trade_identity = str(default_identity)
        watch_type: str | None = None
        result_status = "actionable_trade"
        reason = "selected candidate is eligible for the expression bucket"

        if trade_identity == "core_holding" and not is_core_holding_approved(candidate.ticker, self.portfolio_intents):
            raise ValueError("core_holding_requires_active_portfolio_intent")

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

    def classify_many(self, selected: Iterable[SelectedTradeRecord]) -> list[TradeClassificationRecord]:
        """Classify a batch of selected strategies."""
        return [self.classify(item) for item in selected]
