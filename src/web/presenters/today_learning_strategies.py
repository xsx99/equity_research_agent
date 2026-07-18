"""Presenter helpers for learning-factor and strategy-evolution observability."""
from __future__ import annotations

import json
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
    reflection_display = _normalize_reflection(reflection)
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
    learning_factors_enriched = tuple(
        {
            **row,
            "effect_summary": _effect_summary(tuple(row.get("effect_tags") or ())),
            "applied_today": (
                str(row.get("status") or "") == "active"
                and str(row.get("scope") or "") in {"strategy", "risk", "portfolio"}
                and bool(tuple(row.get("effect_tags") or ()))
            ),
        }
        for row in learning_factors
    )
    learning_factors_display = _dedupe_learning_factors(learning_factors_enriched)
    strategy_proposals_display = _dedupe_strategy_proposals(strategy_proposals)
    return {
        "reflection": reflection_display,
        "learning_factors": learning_factors_display,
        "strategy_performance": strategy_performance_with_summary,
        "strategy_proposals": strategy_proposals_display,
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


def _dedupe_learning_factors(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("title") or ""),
            str(row.get("status") or ""),
            str(row.get("scope") or ""),
            str(row.get("effect_summary") or ""),
            bool(row.get("applied_today")),
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {**row, "occurrence_count": 1}
        else:
            existing["occurrence_count"] += 1
    return tuple(grouped.values())


def _dedupe_strategy_proposals(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("proposed_strategy_id") or row.get("display_name") or "").strip()
        grouped.setdefault(key, []).append(row)

    deduped = []
    for items in grouped.values():
        ranked_items = sorted(items, key=_proposal_status_rank)
        preferred = ranked_items[0]
        status_labels = _unique_labels(
            item.get("proposal_status_label") or item.get("proposal_status") for item in ranked_items
        )
        deduped.append(
            {
                **preferred,
                "proposal_status_label": " + ".join(status_labels),
                "proposal_count": len(items),
            }
        )
    return tuple(deduped)


def _proposal_status_rank(row: dict[str, Any]) -> tuple[int, str]:
    status = str(row.get("proposal_status") or "").strip().lower()
    priority = {
        "accepted": 0,
        "promoted": 1,
        "duplicate_rejected": 2,
        "insufficient_evidence_rejected": 3,
        "rejected": 4,
        "proposal_failed": 5,
    }
    return (priority.get(status, 99), str(row.get("proposed_strategy_id") or ""))


def _unique_labels(labels: Any) -> tuple[str, ...]:
    seen = []
    for label in labels:
        text = str(label or "").strip()
        if text and text not in seen:
            seen.append(text)
    return tuple(seen)


def _normalize_reflection(reflection: dict[str, Any] | None) -> dict[str, Any] | None:
    if reflection is None:
        return None
    return {
        **reflection,
        "what_worked": tuple(_normalize_reflection_point(item) for item in reflection.get("what_worked") or ()),
        "what_failed": tuple(_normalize_reflection_point(item) for item in reflection.get("what_failed") or ()),
        "attribution": tuple(_normalize_attribution(item) for item in reflection.get("attribution") or ()),
    }


def _normalize_reflection_point(item: Any) -> dict[str, Any]:
    item = _parse_json_string(item)
    if not isinstance(item, dict):
        return {"summary": str(item), "reason": "", "tags": ()}

    summary = _first_text(item, "contribution", "summary", "observation", "title", "result")
    reason = _first_text(item, "reason", "rationale", "explanation")
    tags = tuple(
        tag
        for tag in (
            str(item.get("ticker") or "").strip().upper(),
            _title_label(str(item.get("strategy") or item.get("strategy_id") or "")),
        )
        if tag
    )
    return {
        "summary": summary or "Reflection observation",
        "reason": reason,
        "tags": tags,
    }


def _normalize_attribution(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "strategy_id": "portfolio",
            "result": "",
            "root_cause_summary": str(item),
        }
    return {
        **item,
        "root_cause_summary": _root_cause_summary(item.get("root_cause")),
    }


def _root_cause_summary(root_cause: Any) -> str:
    root_cause = _parse_json_string(root_cause)
    if not isinstance(root_cause, dict):
        return str(root_cause or "").strip()

    parts = []
    for key, label in (
        ("bullish_trades", "Bullish trades"),
        ("bearish_trades", "Bearish trades"),
        ("risk_off_trades", "Risk-off trades"),
    ):
        trades = tuple(root_cause.get(key) or ())
        if not trades:
            continue
        parts.append(f"{label}: {', '.join(_trade_summary(trade) for trade in trades)}")

    other_pnl = _format_decimal_value(root_cause.get("other_pnl"))
    if other_pnl is not None:
        parts.append(f"Other P&L: {other_pnl}")
    return "; ".join(parts) if parts else "No specific root cause recorded."


def _trade_summary(trade: Any) -> str:
    if not isinstance(trade, dict):
        return str(trade)
    ticker = str(trade.get("ticker") or "Portfolio").strip().upper()
    strategy = str(trade.get("strategy") or trade.get("strategy_id") or "").strip()
    pnl = _format_decimal_value(trade.get("pnl"))
    bits = [ticker]
    if strategy:
        bits.append(f"via {strategy}")
    if pnl is not None:
        bits.append(f"({pnl} P&L)")
    return " ".join(bits)


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


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


def _format_decimal_value(value: Any) -> str | None:
    number = _decimal_or_none(value)
    if number is None:
        return None
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.4f}"


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


def _title_label(value: str) -> str:
    text = value.strip().replace("-", " ").replace("_", " ")
    return " ".join(part.capitalize() for part in text.split())
