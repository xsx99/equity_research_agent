"""Primary strategy and expression-bucket selection for PR03."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord


@dataclass(frozen=True)
class SelectedTradeRecord:
    """Selected trade-path strategy plus frozen expression context."""

    candidate: CandidateScoreRecord
    selected_expression_bucket_id: str
    selected_expression_bucket_version: str
    selected_expression_bucket_config: dict[str, Any]
    fallback_expression_bucket_ids: tuple[str, ...]
    expression_selection_context: dict[str, Any]
    selection_context: dict[str, Any]

    @property
    def strategy_id(self) -> str:
        return self.candidate.strategy_id

    @property
    def expression_bucket_id(self) -> str:
        return self.selected_expression_bucket_id

    @property
    def expression_bucket_version(self) -> str:
        return self.selected_expression_bucket_version

    @property
    def expression_bucket_config(self) -> dict[str, Any]:
        return self.selected_expression_bucket_config


@dataclass(frozen=True)
class ExpressionSelectionPlan:
    """Concrete expression choice and ordered same-strategy fallbacks."""

    selected_expression: StrategyDefinitionRecord
    fallback_expressions: tuple[StrategyDefinitionRecord, ...]
    context: dict[str, Any]


@dataclass(frozen=True)
class WatchCandidateRecord:
    """Retained non-trade outcome with explicit watch semantics."""

    watch_candidate_id: str
    candidate: CandidateScoreRecord
    watch_strategy_id: str
    watch_strategy_version: str
    watch_type: str | None
    result_status: str
    watch_reason: str
    selection_context: dict[str, Any]


@dataclass(frozen=True)
class PrimarySelectionResult:
    """Split selector output for trade-path and watch-path outcomes."""

    selected_trades: tuple[SelectedTradeRecord, ...]
    watch_candidates: tuple[WatchCandidateRecord, ...]


# Backward-compatible alias while downstream modules are migrated.
SelectedStrategyRecord = SelectedTradeRecord


def advance_selected_trade_expression(
    selected_trade: SelectedTradeRecord,
    expression_definitions: Iterable[StrategyDefinitionRecord],
) -> SelectedTradeRecord | None:
    """Advance to the next persisted same-strategy fallback expression, if any."""
    remaining_ids = list(selected_trade.fallback_expression_bucket_ids)
    if not remaining_ids:
        return None
    expressions = {
        definition.strategy_id: definition
        for definition in expression_definitions
        if definition.strategy_layer == "expression_bucket" and definition.is_active
    }
    while remaining_ids:
        next_id = remaining_ids.pop(0)
        next_expression = expressions.get(next_id)
        if next_expression is None:
            continue
        return SelectedTradeRecord(
            candidate=selected_trade.candidate,
            selected_expression_bucket_id=next_expression.strategy_id,
            selected_expression_bucket_version=next_expression.version,
            selected_expression_bucket_config=dict(next_expression.config_json),
            fallback_expression_bucket_ids=tuple(remaining_ids),
            expression_selection_context={
                **selected_trade.expression_selection_context,
                "selected_expression_bucket_id": next_expression.strategy_id,
                "fallback_expression_bucket_ids": list(remaining_ids),
                "advanced_from_expression_bucket_id": selected_trade.selected_expression_bucket_id,
            },
            selection_context=dict(selected_trade.selection_context),
        )
    return None


class ExpressionSelector:
    """Rank allowed expression buckets for a chosen tactical strategy."""

    def select(
        self,
        candidate: CandidateScoreRecord,
        strategy_definition: StrategyDefinitionRecord | None,
        expressions: dict[str, StrategyDefinitionRecord],
    ) -> ExpressionSelectionPlan | None:
        if strategy_definition is None:
            return None
        allowed_bucket_ids = _allowed_expression_bucket_ids(strategy_definition)
        if not allowed_bucket_ids:
            return None
        ranked = _rank_allowed_expressions(candidate, allowed_bucket_ids, expressions)
        if not ranked:
            return None
        selected_expression, selected_score, selected_reason = ranked[0]
        fallback_expressions = tuple(expression for expression, _, _ in ranked[1:])
        ranking_reasons = {
            expression.strategy_id: reason
            for expression, _, reason in ranked
        }
        return ExpressionSelectionPlan(
            selected_expression=selected_expression,
            fallback_expressions=fallback_expressions,
            context={
                "selected_expression_bucket_id": selected_expression.strategy_id,
                "fallback_expression_bucket_ids": tuple(
                    expression.strategy_id for expression in fallback_expressions
                ),
                "allowed_expression_bucket_ids": allowed_bucket_ids,
                "ranking_reasons": ranking_reasons,
                "ranking_scores": {
                    expression.strategy_id: score
                    for expression, score, _ in ranked
                },
                "selected_score": selected_score,
                "selected_reason": selected_reason,
            },
        )


class PrimaryStrategySelector:
    """Choose trade-path selections and separate watch-path outcomes."""

    def __init__(self, expression_selector: ExpressionSelector | None = None) -> None:
        self.expression_selector = expression_selector or ExpressionSelector()

    def select(
        self,
        candidates: Iterable[CandidateScoreRecord],
        strategy_definitions: Iterable[StrategyDefinitionRecord],
    ) -> PrimarySelectionResult:
        expressions = {
            definition.strategy_id: definition
            for definition in strategy_definitions
            if definition.strategy_layer == "expression_bucket" and definition.is_active
        }
        tactical_definitions = {
            definition.strategy_id: definition
            for definition in strategy_definitions
            if definition.strategy_layer == "tactical_pattern" and definition.is_active
        }

        selected_trades: list[SelectedTradeRecord] = []
        watch_candidates: list[WatchCandidateRecord] = []
        for group in _group_candidates(candidates).values():
            actionable = _choose_actionable(group)
            if actionable is not None:
                expression_plan = self.expression_selector.select(
                    actionable,
                    tactical_definitions.get(actionable.strategy_id),
                    expressions,
                )
                if expression_plan is not None:
                    selected_trades.append(
                        SelectedTradeRecord(
                            candidate=actionable,
                            selected_expression_bucket_id=expression_plan.selected_expression.strategy_id,
                            selected_expression_bucket_version=expression_plan.selected_expression.version,
                            selected_expression_bucket_config=dict(expression_plan.selected_expression.config_json),
                            fallback_expression_bucket_ids=tuple(
                                expression.strategy_id
                                for expression in expression_plan.fallback_expressions
                            ),
                            expression_selection_context=dict(expression_plan.context),
                            selection_context=_selection_context(actionable),
                        )
                    )
                    continue
                watch_candidates.append(
                    _watch_candidate_for_candidate(
                        actionable,
                        watch_reason="strategy has no eligible active expression bucket mapping",
                        result_status="ordinary_watch",
                        watch_type="ordinary_watch",
                    )
                )
                continue

            watchable = _choose_watch_candidate(group)
            if watchable is not None:
                watch_candidates.append(_watch_candidate_for_candidate(watchable))
        return PrimarySelectionResult(
            selected_trades=tuple(selected_trades),
            watch_candidates=tuple(watch_candidates),
        )


def _group_candidates(candidates: Iterable[CandidateScoreRecord]) -> dict[tuple[str, str], list[CandidateScoreRecord]]:
    grouped: dict[tuple[str, str], list[CandidateScoreRecord]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate.ticker, candidate.action), []).append(candidate)
    return grouped


def _choose_actionable(candidates: list[CandidateScoreRecord]) -> CandidateScoreRecord | None:
    actionable = [candidate for candidate in candidates if candidate.is_actionable]
    if not actionable:
        return None
    return max(actionable, key=lambda item: item.candidate_score)


def _choose_watch_candidate(candidates: list[CandidateScoreRecord]) -> CandidateScoreRecord | None:
    watchable = [
        candidate
        for candidate in candidates
        if candidate.candidate_status in {"watch", "blocked"}
        or candidate.rejection_reason is not None
        or candidate.action == "no_trade"
    ]
    if not watchable:
        return None
    return max(watchable, key=_watch_sort_key)


def _watch_sort_key(candidate: CandidateScoreRecord) -> tuple[int, float]:
    priority = 1
    if candidate.rejection_reason == "no_clean_entry" and _has_high_move_potential(candidate):
        priority = 4
    elif candidate.rejection_reason == "unsupported_missing_signal_family":
        priority = 0
    elif candidate.rejection_reason in {"direct_negative_catalyst", "macro_regime_blocked"}:
        priority = 2
    elif candidate.action == "no_trade":
        priority = 3
    return priority, candidate.candidate_score


def _choose_expression(
    candidate: CandidateScoreRecord,
    strategy_definition: StrategyDefinitionRecord | None,
    expressions: dict[str, StrategyDefinitionRecord],
) -> StrategyDefinitionRecord | None:
    del candidate
    if strategy_definition is None:
        return None
    for bucket_id in _allowed_expression_bucket_ids(strategy_definition):
        expression = expressions.get(str(bucket_id))
        if expression is not None:
            return expression
    return None


def _watch_candidate_for_candidate(
    candidate: CandidateScoreRecord,
    *,
    watch_reason: str | None = None,
    result_status: str | None = None,
    watch_type: str | None = None,
) -> WatchCandidateRecord:
    resolved_watch_type, resolved_result_status, resolved_reason = _watch_state_for_candidate(candidate)
    return WatchCandidateRecord(
        watch_candidate_id=str(uuid.uuid4()),
        candidate=candidate,
        watch_strategy_id=candidate.strategy_id,
        watch_strategy_version=candidate.strategy_version,
        watch_type=watch_type if watch_type is not None else resolved_watch_type,
        result_status=result_status if result_status is not None else resolved_result_status,
        watch_reason=watch_reason if watch_reason is not None else resolved_reason,
        selection_context=_selection_context(candidate),
    )


def _watch_state_for_candidate(candidate: CandidateScoreRecord) -> tuple[str | None, str, str]:
    if candidate.rejection_reason == "unsupported_missing_signal_family":
        return "ordinary_watch", "blocked_by_missing_data", "required source family is missing or unsupported"
    if candidate.rejection_reason == "no_clean_entry" and _has_high_move_potential(candidate):
        return "catalyst_watch", "catalyst_watch", "move potential is high but direction or entry is uncertain"
    if candidate.rejection_reason == "direct_negative_catalyst":
        return "ordinary_watch", "no_trade", "direct negative catalyst blocks the candidate"
    if candidate.rejection_reason == "macro_regime_blocked":
        return "ordinary_watch", "no_trade", "macro regime blocks the strategy"
    if candidate.missing_required_signals:
        return "ordinary_watch", "blocked_by_missing_data", "required decision-time signals are still missing"
    if candidate.action == "no_trade":
        return "ordinary_watch", "ordinary_watch", "candidate is intentionally retained as a no-trade watch"
    return "ordinary_watch", "ordinary_watch", "candidate is not trade-eligible"


def _selection_context(candidate: CandidateScoreRecord) -> dict[str, Any]:
    return {
        "candidate_score_id": candidate.candidate_score_id,
        "candidate_score": candidate.candidate_score,
        "strategy_id": candidate.strategy_id,
        "strategy_version": candidate.strategy_version,
        "candidate_status": candidate.candidate_status,
        "rejection_reason": candidate.rejection_reason,
        "selection_reason": candidate.selection_reason,
        "benchmark_context": candidate.benchmark_context,
    }


def _has_high_move_potential(candidate: CandidateScoreRecord) -> bool:
    catalyst_quality = candidate.core_signal_evidence.get("events_news.catalyst_quality_score")
    high_signal_count = candidate.core_signal_evidence.get("events_news.high_signal_news_count_24h")
    return (
        isinstance(catalyst_quality, (int, float))
        and float(catalyst_quality) >= 0.75
    ) or (
        isinstance(high_signal_count, (int, float))
        and float(high_signal_count) >= 1
        and candidate.candidate_score >= 0.55
    )


def _allowed_expression_bucket_ids(strategy_definition: StrategyDefinitionRecord) -> tuple[str, ...]:
    selection_policy = dict(strategy_definition.config_json.get("selection_policy") or {})
    bucket_ids = tuple(selection_policy.get("allowed_expression_bucket_ids") or ())
    if bucket_ids:
        return bucket_ids
    return tuple(selection_policy.get("eligible_expression_bucket_ids") or ())


def _rank_allowed_expressions(
    candidate: CandidateScoreRecord,
    allowed_bucket_ids: tuple[str, ...],
    expressions: dict[str, StrategyDefinitionRecord],
) -> list[tuple[StrategyDefinitionRecord, int, str]]:
    ranked: list[tuple[StrategyDefinitionRecord, int, str]] = []
    for index, bucket_id in enumerate(allowed_bucket_ids):
        expression = expressions.get(str(bucket_id))
        if expression is None:
            continue
        score, reason = _expression_rank(candidate, expression)
        ranked.append((expression, score * 100 - index, reason))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def _expression_rank(
    candidate: CandidateScoreRecord,
    expression: StrategyDefinitionRecord,
) -> tuple[int, str]:
    evidence = candidate.core_signal_evidence
    suitability = dict(expression.config_json.get("suitability") or {})
    stock_entry_clean = _evidence_bool(evidence.get("entry_signal.stock_entry_clean"))
    directional_clarity = _evidence_bool(evidence.get("signal_direction.directional_clarity"))
    defined_risk_preferred = _evidence_bool(evidence.get("risk_shape.defined_risk_preferred"))
    binary_event_in_horizon = _evidence_bool(evidence.get("event_context.binary_event_in_horizon"))
    event_volatility_matters = _evidence_bool(evidence.get("event_context.event_volatility_matters"))

    score = 0
    reasons: list[str] = []
    if suitability.get("prefers_stock_when_entry_clean"):
        if stock_entry_clean:
            score += 4
            reasons.append("clean stock entry")
        else:
            score -= 2
    if suitability.get("prefers_defined_risk") and defined_risk_preferred:
        score += 3
        reasons.append("defined risk preferred")
    if suitability.get("requires_directional_clarity"):
        if directional_clarity:
            score += 2
            reasons.append("directional clarity present")
        else:
            score -= 3
    if suitability.get("prefers_event_volatility"):
        if binary_event_in_horizon and event_volatility_matters:
            score += 5
            reasons.append("event volatility setup")
        else:
            score -= 1
    if suitability.get("penalize_binary_event_through_horizon") and binary_event_in_horizon:
        score -= 4
    if expression.strategy_id == "long_stock" and not stock_entry_clean:
        score -= 1
    if expression.strategy_id == "volatility_event_option" and binary_event_in_horizon and event_volatility_matters:
        score += 1
    if not reasons:
        reasons.append("declared order fallback")
    return score, ", ".join(reasons)


def _evidence_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) > 0
    return bool(value)
