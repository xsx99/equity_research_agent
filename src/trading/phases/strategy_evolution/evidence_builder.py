"""Deterministically bound strategy-evolution evidence before prompt rendering."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


MAX_PROMPT_BYTES = 120 * 1024


@dataclass(frozen=True)
class StrategyEvolutionEvidence:
    payload: dict[str, object]
    rendered_json: str | None
    skip_reason: str | None


class StrategyEvolutionEvidenceBuilder:
    """Apply cardinality limits before any LLM provider is invoked."""

    def __init__(self, *, max_prompt_bytes: int = MAX_PROMPT_BYTES) -> None:
        self.max_prompt_bytes = max_prompt_bytes

    def build(
        self,
        *,
        trade_date: str,
        decision_time: str,
        reflections: Iterable[dict[str, Any]],
        learning_factors: Iterable[dict[str, Any]],
        rejected_candidates: Iterable[dict[str, Any]],
        outcomes: Iterable[dict[str, Any]],
        existing_strategies: Iterable[dict[str, Any]],
    ) -> StrategyEvolutionEvidence:
        rejected_groups, rejected_examples = _bounded_rejections(rejected_candidates)
        payload: dict[str, object] = {
            "trade_date": trade_date,
            "decision_time": decision_time,
            "strategy_proposal_hints": _cap_rows(reflections, 20, _confidence_sort_key),
            "learning_factors": _cap_rows(learning_factors, 30, _confidence_sort_key),
            "rejected_candidate_groups": rejected_groups,
            "rejected_candidate_examples": rejected_examples,
            "outcome_performance_summaries": _cap_rows(outcomes, 100, _outcome_sort_key),
            "existing_strategies": _compact_strategies(existing_strategies),
        }
        rendered = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
        if len(rendered.encode("utf-8")) > self.max_prompt_bytes:
            return StrategyEvolutionEvidence(payload=payload, rendered_json=None, skip_reason="input_budget_exceeded")
        return StrategyEvolutionEvidence(payload=payload, rendered_json=rendered, skip_reason=None)


def _bounded_rejections(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("strategy_id") or "unknown"),
            str(row.get("rejection_reason") or "unknown"),
            str(row.get("decision_time") or "")[:10],
        )
        groups.setdefault(key, []).append(dict(row))
    ordered = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), -_latest_time(item[1]), item[0]),
    )[:50]
    aggregates: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    for index, (key, values) in enumerate(ordered):
        strategy_id, reason, trade_date = key
        aggregates.append(
            {
                "strategy_id": strategy_id,
                "rejection_reason": reason,
                "trade_date": trade_date,
                "count": len(values),
            }
        )
        if index >= 20:
            continue
        for row in sorted(values, key=lambda item: (-_time_value(item), str(item.get("ticker") or ""), str(item.get("candidate_score_id") or "")))[:2]:
            if len(examples) >= 40:
                break
            examples.append(
                {
                    "candidate_score_id": row.get("candidate_score_id"),
                    "ticker": row.get("ticker"),
                    "strategy_id": row.get("strategy_id"),
                    "rejection_reason": row.get("rejection_reason"),
                    "decision_time": row.get("decision_time"),
                }
            )
    return aggregates, examples


def _compact_strategies(rows: Iterable[dict[str, Any]]) -> list[dict[str, object]]:
    keys = ("strategy_id", "display_name", "typical_horizon", "lifecycle_status", "source", "core_thesis", "required_signals", "risk_tags")
    return [
        {key: row.get(key) for key in keys if row.get(key) not in (None, "", (), [])}
        for row in sorted(rows, key=lambda item: str(item.get("strategy_id") or ""))
    ]


def _cap_rows(rows: Iterable[dict[str, Any]], limit: int, key) -> list[dict[str, Any]]:
    return [dict(row) for row in sorted(rows, key=key)[:limit]]


def _confidence_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    return (-float(row.get("confidence") or 0), str(row.get("factor_key") or row.get("title") or ""))


def _outcome_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    return (-float(row.get("alpha") or 0), str(row.get("candidate_outcome_evaluation_id") or ""))


def _time_value(row: dict[str, Any]) -> int:
    return int("".join(char for char in str(row.get("decision_time") or "") if char.isdigit())[:14] or 0)


def _latest_time(rows: Iterable[dict[str, Any]]) -> int:
    return max((_time_value(row) for row in rows), default=0)
