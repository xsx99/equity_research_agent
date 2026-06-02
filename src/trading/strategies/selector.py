"""Primary strategy and expression-bucket selection for PR03."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


@dataclass(frozen=True)
class SelectedStrategyRecord:
    """Selected primary strategy plus frozen expression context."""

    candidate: CandidateScoreRecord
    expression_bucket_id: str
    expression_bucket_version: str
    expression_bucket_config: dict[str, Any]
    selection_context: dict[str, Any]

    @property
    def strategy_id(self) -> str:
        return self.candidate.strategy_id


class PrimaryStrategySelector:
    """Choose one primary strategy and expression bucket per ticker/action."""

    def select(
        self,
        candidates: Iterable[CandidateScoreRecord],
        expression_buckets: Iterable[StrategyDefinitionRecord],
    ) -> list[SelectedStrategyRecord]:
        expressions = {
            expression.strategy_id: expression
            for expression in expression_buckets
            if expression.strategy_layer == "expression_bucket" and expression.is_active
        }
        selected: list[SelectedStrategyRecord] = []
        for group in _group_candidates(candidates).values():
            primary = _choose_primary(group)
            if primary is None:
                continue
            expression = _choose_expression(primary, expressions)
            selected.append(
                SelectedStrategyRecord(
                    candidate=primary,
                    expression_bucket_id=expression.strategy_id,
                    expression_bucket_version=expression.version,
                    expression_bucket_config=dict(expression.config_json),
                    selection_context={
                        "candidate_score_id": primary.candidate_score_id,
                        "candidate_score": primary.candidate_score,
                        "strategy_id": primary.strategy_id,
                        "strategy_version": primary.strategy_version,
                        "rejection_reason": primary.rejection_reason,
                        "selection_reason": primary.selection_reason,
                        "benchmark_context": primary.benchmark_context,
                    },
                )
            )
        return selected


def _group_candidates(candidates: Iterable[CandidateScoreRecord]) -> dict[tuple[str, str], list[CandidateScoreRecord]]:
    grouped: dict[tuple[str, str], list[CandidateScoreRecord]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate.ticker, candidate.action), []).append(candidate)
    return grouped


def _choose_primary(candidates: list[CandidateScoreRecord]) -> CandidateScoreRecord | None:
    actionable = [candidate for candidate in candidates if candidate.is_actionable]
    if actionable:
        return max(actionable, key=lambda item: item.candidate_score)
    watchable = [
        candidate
        for candidate in candidates
        if candidate.rejection_reason in {"no_clean_entry", "direct_negative_catalyst", "unsupported_missing_signal_family"}
    ]
    if watchable:
        return max(watchable, key=lambda item: item.candidate_score)
    return None


def _choose_expression(
    candidate: CandidateScoreRecord,
    expressions: dict[str, StrategyDefinitionRecord],
) -> StrategyDefinitionRecord:
    if candidate.strategy_id == "core_accumulation_on_pullback_v1" and "core_stock_accumulation" in expressions:
        return expressions["core_stock_accumulation"]
    return expressions.get("long_stock") or _fallback_long_stock_expression()


def _fallback_long_stock_expression() -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id="long_stock-fallback",
        strategy_id="long_stock",
        version="v1",
        display_name="Long Stock",
        strategy_layer="expression_bucket",
        typical_horizon="intraday-3m",
        config_json={
            "default_trade_identity": "tactical_stock_trade",
            "default_exit_policy": "strategy_invalidators_or_target_horizon",
        },
        lifecycle_status="active",
        is_active=True,
    )
