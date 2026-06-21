"""Presenter helpers for candidate and manual-review queue surfaces."""
from __future__ import annotations

from typing import Any

from src.web.presenters.today_copy import operator_text


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
                "selection_reason": _clean_copy(primary.get("selection_reason")),
                "signal_bullets": _signal_bullets(primary.get("core_signal_evidence")),
                "risk_tags": _labeled_bullets("Risk tags", primary.get("risk_tags")),
                "invalidators": _labeled_bullets("Invalidators", primary.get("invalidators")),
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


def _signal_bullets(evidence: dict[str, Any] | Any) -> tuple[str, ...]:
    flattened = _flatten_evidence(evidence)
    if not flattened:
        return ("No signal snapshot recorded for this candidate.",)

    bullets: list[str] = []
    technical = _signal_group_parts(
        flattened,
        (
            "technical.return_20d",
            "technical.relative_volume",
            "technical.rs_vs_spy_1d",
            "technical.rs_vs_qqq_1d",
            "technical.rsi_3",
            "technical.drawdown_from_recent_high",
        ),
    )
    fundamental = _signal_group_parts(
        flattened,
        (
            "fundamental.quality_score",
            "fundamental.revenue_growth_score",
            "fundamental.margin_trend_score",
            "fundamental.valuation_percentile",
        ),
    )
    news = _signal_group_parts(
        flattened,
        (
            "events_news.sentiment_direction",
            "events_news.high_signal_news_count_24h",
            "events_news.catalyst_quality_score",
            "events_news.own_earnings_event_type",
            "events_news.guidance_news_flag",
            "events_news.analyst_upgrade_count",
            "news.sentiment_direction",
            "news.high_signal_news_count_24h",
            "news.catalyst_quality_score",
            "insider.insider_net_buy_value_30d",
            "insider.insider_cluster_buy_count_90d",
            "insider.officer_buy_flag",
            "insider.director_buy_flag",
        ),
    )

    if technical:
        bullets.append(f"Technical: {', '.join(technical)}.")
    if fundamental:
        bullets.append(f"Fundamental: {', '.join(fundamental)}.")
    if news:
        bullets.append(f"News: {', '.join(news)}.")
    return tuple(bullets) if bullets else ("No signal snapshot recorded for this candidate.",)


def _signal_group_parts(flattened: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    for key in keys:
        part = _signal_part(key, flattened.get(key))
        if part:
            parts.append(part)
    return parts


def _signal_part(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        if not value:
            return None
        mapping = {
            "events_news.guidance_news_flag": "guidance news",
            "insider.officer_buy_flag": "officer buying",
            "insider.director_buy_flag": "director buying",
        }
        return mapping.get(key)

    number = _as_float(value)
    if key == "technical.return_20d" and number is not None:
        return f"20d return {number * 100:.2f}%"
    if key == "technical.relative_volume" and number is not None:
        return f"relative volume {number:.2f}"
    if key == "technical.rs_vs_spy_1d" and number is not None:
        return f"RS vs SPY {number * 100:.2f}%"
    if key == "technical.rs_vs_qqq_1d" and number is not None:
        return f"RS vs QQQ {number * 100:.2f}%"
    if key == "technical.rsi_3" and number is not None:
        return f"3d RSI {number:.2f}"
    if key == "technical.drawdown_from_recent_high" and number is not None:
        return f"drawdown from recent high {number * 100:.2f}%"
    if key == "fundamental.quality_score" and number is not None:
        return f"quality {number:.2f}"
    if key == "fundamental.revenue_growth_score" and number is not None:
        return f"revenue growth {number:.2f}"
    if key == "fundamental.margin_trend_score" and number is not None:
        return f"margin trend {number:.2f}"
    if key == "fundamental.valuation_percentile" and number is not None:
        return f"valuation percentile {number:.2f}"
    if key in {"events_news.sentiment_direction", "news.sentiment_direction"}:
        text = _clean_fragment(value)
        return f"sentiment {text}" if text else None
    if key in {"events_news.high_signal_news_count_24h", "news.high_signal_news_count_24h"} and number is not None:
        count = int(number) if float(number).is_integer() else number
        return f"{count} high-signal items / 24h"
    if key in {"events_news.catalyst_quality_score", "news.catalyst_quality_score"} and number is not None:
        return f"catalyst quality {number:.2f}"
    if key == "events_news.own_earnings_event_type":
        text = _clean_fragment(value)
        return f"earnings event {text}" if text else None
    if key == "events_news.analyst_upgrade_count" and number is not None:
        count = int(number) if float(number).is_integer() else number
        noun = "upgrade" if count == 1 else "upgrades"
        return f"{count} analyst {noun}"
    if key == "insider.insider_net_buy_value_30d" and number is not None:
        return f"insider net buy ${number:,.0f} / 30d"
    if key == "insider.insider_cluster_buy_count_90d" and number is not None:
        count = int(number) if float(number).is_integer() else number
        noun = "cluster buy" if count == 1 else "cluster buys"
        return f"{count} insider {noun} / 90d"

    text = _clean_fragment(value)
    return text or None


def _flatten_evidence(evidence: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    flattened: dict[str, Any] = {}
    for raw_key, raw_value in evidence.items():
        key = str(raw_key).strip()
        if not key:
            continue
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(raw_value, dict):
            flattened.update(_flatten_evidence(raw_value, full_key))
            continue
        flattened[full_key] = raw_value
    return flattened


def _labeled_bullets(label: str, values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    cleaned = [_clean_fragment(value) for value in values]
    items = [value for value in cleaned if value]
    if not items:
        return ()
    return (f"{label}: {', '.join(items)}.",)


def _clean_copy(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return operator_text(text)


def _clean_fragment(value: Any) -> str | None:
    text = _clean_copy(value)
    if not text:
        return None
    return text.rstrip(".")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
