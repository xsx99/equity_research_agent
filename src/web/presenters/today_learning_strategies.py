"""Presenter helpers for learning-factor and strategy-evolution observability."""
from __future__ import annotations

from typing import Any


def build_today_learning_strategies(
    *,
    reflection: dict[str, Any] | None,
    learning_factors: tuple[dict[str, Any], ...],
    strategy_performance: tuple[dict[str, Any], ...],
    strategy_proposals: tuple[dict[str, Any], ...],
    strategy_definitions: tuple[dict[str, Any], ...],
    strategy_evaluation_results: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    promoted_rows = tuple(
        row for row in strategy_evaluation_results if str(row.get("evaluation_status") or "") == "promoted"
    )
    weight_inputs = tuple(
        sorted(
            (
                {
                    "factor_key": str(row.get("factor_key") or ""),
                    "title": row.get("title") or "Unnamed factor",
                    "scope_label": row.get("scope_label") or _humanize(str(row.get("scope") or "")),
                    "effect_summary": _effect_summary(tuple(row.get("effect_tags") or ())),
                }
                for row in learning_factors
                if str(row.get("status") or "") == "active"
                and str(row.get("scope") or "") in {"strategy", "risk", "portfolio"}
                and tuple(row.get("effect_tags") or ())
            ),
            key=lambda row: (row["scope_label"], row["title"]),
        )
    )
    promotion_breakdown = tuple(
        {
            "label": label,
            "count": sum(1 for row in promoted_rows if str(row.get("new_lifecycle_status") or "") == lifecycle_status),
        }
        for lifecycle_status, label in (
            ("shadow", "Shadow"),
            ("experimental", "Experimental"),
            ("active", "Active"),
        )
    )
    return {
        "reflection": reflection,
        "learning_factors": learning_factors,
        "strategy_performance": strategy_performance,
        "strategy_proposals": strategy_proposals,
        "strategy_definitions": strategy_definitions,
        "strategy_evaluation_results": strategy_evaluation_results,
        "observability": {
            "funnel": (
                {"label": "Learning Factors Created", "count": len(learning_factors)},
                {"label": "Applied Today", "count": len(weight_inputs) + sum(1 for row in learning_factors if str(row.get("status") or "") == "shadow")},
                {"label": "Strategy Proposals", "count": len(strategy_proposals)},
                {"label": "New Strategy Definitions", "count": len(strategy_definitions)},
                {"label": "Promoted", "count": len(promoted_rows)},
            ),
            "promotion_breakdown": promotion_breakdown,
            "weight_inputs": weight_inputs,
        },
    }


def _effect_summary(tags: tuple[str, ...]) -> str:
    return ", ".join(_humanize(tag) for tag in tags if str(tag).strip())


def _humanize(value: str) -> str:
    text = value.strip().replace("-", " ").replace("_", " ")
    return " ".join(part.lower() for part in text.split())
