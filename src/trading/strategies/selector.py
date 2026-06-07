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
    expression_bucket_id: str
    expression_bucket_version: str
    expression_bucket_config: dict[str, Any]
    selection_context: dict[str, Any]

    @property
    def strategy_id(self) -> str:
        return self.candidate.strategy_id


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


class PrimaryStrategySelector:
    """Choose trade-path selections and separate watch-path outcomes."""

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
                expression = _choose_expression(
                    actionable,
                    tactical_definitions.get(actionable.strategy_id),
                    expressions,
                )
                if expression is not None:
                    if _expression_is_deferred_option_path(expression):
                        watch_candidates.append(
                            _watch_candidate_for_candidate(
                                actionable,
                                watch_reason="eligible option expression is deferred until option-chain data is available",
                                result_status="ordinary_watch",
                                watch_type="ordinary_watch",
                            )
                        )
                        continue
                    selected_trades.append(
                        SelectedTradeRecord(
                            candidate=actionable,
                            expression_bucket_id=expression.strategy_id,
                            expression_bucket_version=expression.version,
                            expression_bucket_config=dict(expression.config_json),
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
    if strategy_definition is None:
        return None
    selection_policy = dict(strategy_definition.config_json.get("selection_policy") or {})
    bucket_ids = tuple(selection_policy.get("eligible_expression_bucket_ids") or ())
    for bucket_id in bucket_ids:
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


def _expression_is_deferred_option_path(expression: StrategyDefinitionRecord) -> bool:
    return str(expression.config_json.get("default_trade_identity") or "") == "tactical_option_trade"


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
