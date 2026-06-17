"""Presenter helpers for candidate and manual-review queue surfaces."""
from __future__ import annotations

from typing import Any


def build_today_candidates_view(
    *,
    rows: tuple[dict[str, Any], ...],
    manual_requests: tuple[dict[str, Any], ...],
    themes: tuple[dict[str, Any], ...],
    active_universe_filter: dict[str, Any] | None,
    portfolio_intents: tuple[dict[str, Any], ...],
    relationships: tuple[dict[str, Any], ...],
    peer_baskets: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    decision_readout = _group_candidate_rows(rows)
    manual_review_queue = _normalize_manual_review_rows(manual_requests)
    action_queue = _build_action_queue(decision_readout, manual_review_queue)
    return {
        "summary": {
            "action_queue": action_queue,
            "theme_count": len(themes),
        },
        "action_queue": action_queue,
        "manual_review_queue": manual_review_queue,
        "decision_readout": decision_readout,
        "rows": rows,
        "manual_requests": manual_requests,
        "active_universe_filter": active_universe_filter,
        "portfolio_intents": portfolio_intents,
        "relationships": relationships,
        "peer_baskets": peer_baskets,
        "themes": themes,
    }


def _group_candidate_rows(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append({**row, "ticker": ticker})

    groups: list[dict[str, Any]] = []
    for ticker, items in grouped.items():
        sorted_items = sorted(items, key=_candidate_sort_key)
        primary = sorted_items[0]
        groups.append(
            {
                "ticker": ticker,
                "latest_outcome": primary.get("current_outcome_label") or primary.get("result_status") or "Unavailable",
                "primary_reason": primary.get("operator_summary") or "No material update.",
                "trade_identity_label": primary.get("trade_identity_label"),
                "strategy_label": primary.get("strategy_label") or primary.get("strategy_match") or "Unavailable",
                "decision_time": primary.get("decision_time"),
                "duplicate_count": len(sorted_items),
                "alternatives": tuple(
                    {
                        "strategy_label": item.get("strategy_label") or item.get("strategy_match") or "Unavailable",
                        "operator_summary": item.get("operator_summary") or "No material update.",
                        "trade_identity_label": item.get("trade_identity_label"),
                        "candidate_score": item.get("candidate_score"),
                    }
                    for item in sorted_items[1:]
                ),
                "detail_internal_ids": primary.get("detail_internal_ids") or {},
                "current_outcome_label": primary.get("current_outcome_label") or primary.get("result_status"),
                "action_required": _is_action_required(primary),
            }
        )

    groups.sort(key=_candidate_group_priority)
    return tuple(groups)


def _normalize_manual_review_rows(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized_rows = []
    for row in rows:
        degraded_copy = row.get("degraded_linkage_copy")
        if not degraded_copy and not row.get("linked_detail_url"):
            degraded_copy = "Backend audit linkage has not reached a signal snapshot yet."
        normalized_rows.append(
            {
                **row,
                "last_evaluated_label": row.get("last_evaluated_label") or str(row.get("last_evaluated_at") or "").strip() or None,
                "decision_state_label": row.get("decision_state_label")
                or _humanize(row.get("latest_decision_action"))
                or "Pending evaluation",
                "execution_state_label": row.get("execution_state_label")
                or _humanize(row.get("execution_path_state"))
                or "Unlinked",
                "degraded_linkage_copy": degraded_copy,
            }
        )
    return tuple(normalized_rows)


def _build_action_queue(
    decision_readout: tuple[dict[str, Any], ...],
    manual_review_queue: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    action_rows: list[tuple[int, dict[str, Any]]] = []
    for row in manual_review_queue:
        priority = 0 if row.get("linked_detail_url") or row.get("last_evaluated_label") else 2
        action_rows.append(
            (
                priority,
                {
                    "ticker": row["ticker"],
                    "label": row.get("status_label") or row.get("mode_label") or "Manual Review",
                    "summary": row.get("operator_summary") or row.get("reason") or "No material update.",
                },
            )
        )
    for row in decision_readout:
        if not row.get("action_required"):
            continue
        action_rows.append(
            (
                1,
                {
                    "ticker": row["ticker"],
                    "label": row.get("current_outcome_label") or row.get("latest_outcome") or "Candidate",
                    "summary": row.get("primary_reason") or "No material update.",
                },
            )
        )
    action_rows.sort(key=lambda item: (item[0], item[1]["ticker"]))
    return tuple(row for _, row in action_rows)


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, str, float]:
    return (
        0 if _is_action_required(row) else 1,
        _reverse_timestamp_key(row.get("decision_time")),
        -(float(row.get("candidate_score") or 0.0)),
    )


def _candidate_group_priority(row: dict[str, Any]) -> tuple[int, str, str]:
    return (
        0 if row.get("action_required") else 1,
        _reverse_timestamp_key(row.get("decision_time")),
        row["ticker"],
    )


def _reverse_timestamp_key(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(chr(255 - ord(ch)) for ch in text)


def _is_action_required(row: dict[str, Any]) -> bool:
    outcome = str(row.get("current_outcome_label") or row.get("result_status") or "").strip().lower()
    identity = str(row.get("trade_identity_label") or "").strip().lower()
    return "ready for review" in outcome or "action now" in identity


def _humanize(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.replace("_", " ").replace("-", " ").split())
