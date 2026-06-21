"""Presenter helpers for learning-factor and strategy-evolution observability."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
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
    strategy_performance_with_summary = tuple(
        {
            **row,
            "learning_summary": _synthesize_strategy_summary(row, learning_factors),
        }
        for row in strategy_performance
    )
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
        "strategy_performance": strategy_performance_with_summary,
        "strategy_proposals": strategy_proposals,
        "strategy_definitions": strategy_definitions,
        "strategy_evaluation_results": strategy_evaluation_results,
        "learning_summary_text": _synthesize_learning_overview(
            strategy_performance_with_summary=strategy_performance_with_summary,
            learning_factors=learning_factors,
        ),
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


def _synthesize_strategy_summary(
    perf_row: dict[str, Any],
    learning_factors: tuple[dict[str, Any], ...],
) -> str:
    strategy_id = str(perf_row.get("strategy_id") or "Unknown strategy")
    lifecycle = str(perf_row.get("lifecycle_status_label") or perf_row.get("lifecycle_status") or "Unknown").lower()
    performance_bits = [f"{strategy_id} - {lifecycle}"]

    win_rate = _format_win_rate(perf_row.get("win_rate"))
    if win_rate is not None:
        performance_bits.append(f"{win_rate} win rate")

    total_pnl = _format_currency(perf_row.get("total_pnl"))
    if total_pnl is not None:
        performance_bits.append(f"{total_pnl} total P&L")

    sentence = ", ".join(performance_bits[:2])
    if len(performance_bits) > 2:
        sentence += f" ({', '.join(performance_bits[2:])})."
    else:
        sentence += "."

    learning_factor = _highest_confidence_learning_factor(strategy_id, learning_factors)
    if learning_factor is None:
        return sentence

    confidence = _format_confidence(learning_factor.get("confidence"))
    title = str(learning_factor.get("title") or "Unnamed learning")
    recommendation = str(learning_factor.get("recommendation") or "").strip()
    learning_sentence = f" Latest learning: {title}"
    if confidence is not None:
        learning_sentence += f" (confidence {confidence})"
    if recommendation:
        learning_sentence += f"; recommendation: {recommendation}"
    if not learning_sentence.endswith("."):
        learning_sentence += "."
    return sentence + learning_sentence


def _synthesize_learning_overview(
    *,
    strategy_performance_with_summary: tuple[dict[str, Any], ...],
    learning_factors: tuple[dict[str, Any], ...],
) -> str:
    if not strategy_performance_with_summary:
        if learning_factors:
            return "No strategy performance records yet; learning factors are available for review."
        return "No strategy performance or learning factors recorded yet."

    active_count = sum(
        1 for row in strategy_performance_with_summary if str(row.get("lifecycle_status") or "").strip().lower() == "active"
    )
    top_performer = max(
        strategy_performance_with_summary,
        key=lambda row: _decimal_or_default(row.get("total_pnl"), Decimal("-Infinity")),
    )
    parts = [
        f"{active_count} active strateg{'y' if active_count == 1 else 'ies'} tracked today",
        f"top performer: {top_performer.get('strategy_id') or 'unknown'} ({_format_currency(top_performer.get('total_pnl')) or '—'} total P&L)",
    ]
    key_learning = _highest_confidence_learning_factor(None, learning_factors)
    if key_learning is not None:
        key_learning_text = str(key_learning.get("title") or "Unnamed learning")
        confidence = _format_confidence(key_learning.get("confidence"))
        if confidence is not None:
            parts.append(f"key new learning: {key_learning_text} (confidence {confidence})")
        else:
            parts.append(f"key new learning: {key_learning_text}")
    return ". ".join(parts) + "."


def _highest_confidence_learning_factor(
    strategy_id: str | None,
    learning_factors: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    relevant = [
        row
        for row in learning_factors
        if str(row.get("status") or "").strip().lower() == "active"
        and (strategy_id is None or str(row.get("strategy_id") or "").strip() == strategy_id)
    ]
    if not relevant:
        return None
    return max(
        relevant,
        key=lambda row: (
            _decimal_or_default(row.get("confidence"), Decimal("-1")),
            str(row.get("title") or ""),
        ),
    )


def _effect_summary(tags: tuple[str, ...]) -> str:
    return ", ".join(_humanize(tag) for tag in tags if str(tag).strip())


def _format_currency(value: Any) -> str | None:
    number = _decimal_or_none(value)
    if number is None:
        return None
    sign = "+" if number > 0 else ""
    return f"{sign}${number:,.2f}"


def _format_win_rate(value: Any) -> str | None:
    number = _decimal_or_none(value)
    if number is None:
        return None
    return f"{number:.1f}%"


def _format_confidence(value: Any) -> str | None:
    number = _decimal_or_none(value)
    if number is None:
        return None
    return f"{number:.2f}"


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal_or_default(value: Any, default: Decimal) -> Decimal:
    number = _decimal_or_none(value)
    return number if number is not None else default


def _humanize(value: str) -> str:
    text = value.strip().replace("-", " ").replace("_", " ")
    return " ".join(part.lower() for part in text.split())
