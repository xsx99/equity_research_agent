"""Detail-building helpers for the today workspace presenter."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.web.presenters.signal_evidence import signal_groups
from src.web.presenters.today_copy import (
    expression_bucket_label,
    operator_text,
    order_status_label,
    risk_reason_label,
    risk_status_label,
    strategy_label,
)
from src.web.presenters.today_workspace_format import (
    _EMPTY_MARKER,
    _NO_MATERIAL_TICKER_NEWS,
)
from src.web.presenters.today_workspace_format import (
    _decision_invalidators,
    _decision_rationale_items,
    _decision_summary,
    _format_recency_label,
    _format_timestamp_label,
    _humanize_label,
    _is_material_news_snippet,
    _latest_signal_time_label,
    _parse_timestamp,
    _sort_key_desc,
    _truncate_news_text,
    _with_terminal_period,
    _empty_snippet,
)
from src.web.presenters.today_workspace_timeline import (
    _build_decision_list,
    _build_history_highlights,
    _build_lifecycle,
    _build_risk_history,
    _build_timeline,
    _hedge_overlay_reason,
    _latest_decision,
    _sort_timestamped_items,
)

_TECHNICAL_CHART_SPECS = (
    ("price / key level trend", {"price", "price_trend", "key_levels"}),
    ("relative strength trend", {"relative_strength", "relative_strength_trend", "rs"}),
)
_SIGNAL_GROUP_ORDER = (
    "Risk blockers",
    "Decision drivers",
    "Trend",
    "Insider",
    "Policy / Social",
    "Evidence",
    "Data quality",
)

def _build_detail(
    *,
    selected_ticker: str | None,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    positions_by_ticker: dict[str | None, Any],
    option_positions_by_ticker: dict[str | None, Any],
    closed_positions_by_ticker: dict[str | None, Any],
    risk_by_ticker: dict[str | None, Any],
    signal_history_by_ticker: dict[str | None, Any],
    news_by_ticker: dict[str | None, Any],
    fundamentals_by_ticker: dict[str | None, Any],
) -> dict[str, Any] | None:
    if not selected_ticker:
        return None

    raw_decisions = rows_by_ticker.get(selected_ticker, [])
    decision_history = _sort_timestamped_items(raw_decisions, "created_at")
    latest_decision = _latest_decision(raw_decisions)
    signal_history = signal_history_by_ticker.get(selected_ticker) or {}
    technical_charts = _build_technical_charts(signal_history.get("technical"))
    news_snippets = _build_snippets(news_by_ticker.get(selected_ticker))
    fundamental_snippets = _build_snippets(fundamentals_by_ticker.get(selected_ticker))
    option_positions_by_ticker = option_positions_by_ticker or {}
    position = positions_by_ticker.get(selected_ticker) or option_positions_by_ticker.get(selected_ticker) or {"summary": _EMPTY_MARKER}
    closed_position = closed_positions_by_ticker.get(selected_ticker) or {}
    risk = risk_by_ticker.get(selected_ticker) or {}
    risk_history = _build_risk_history(risk.get("history"))
    key_drivers = _decision_rationale_items(latest_decision, "key_drivers")
    counterarguments = _decision_rationale_items(latest_decision, "counterarguments")
    invalidators = _decision_invalidators(latest_decision)
    metadata_json = dict(latest_decision.get("metadata_json") or {})
    signal_summary = {
        **_build_signal_summary(signal_history),
        "technical_charts": technical_charts,
        "news_snippets": news_snippets,
        "event_news_summary": _build_event_news_summary(news_snippets),
        "fundamental_snippets": fundamental_snippets,
    }
    latest_risk_summary = {
        "status": risk.get("status") or _EMPTY_MARKER,
        "status_label": risk_status_label(risk.get("status")) or _EMPTY_MARKER,
        "reason": risk_reason_label(risk.get("reason")) or operator_text(risk.get("reason")) or _EMPTY_MARKER,
        "lookahead_risk_source": risk.get("lookahead_risk_source"),
        "hedge_overlay_reason": _hedge_overlay_reason(risk.get("generated_hedge_action")),
        "applied_rules": tuple(risk.get("applied_rules") or ()),
        "rule_checks": tuple(risk.get("rule_checks") or ()),
    }
    trade_summary = _risk_override_trade_summary(latest_decision, risk) or _decision_summary(latest_decision)

    latest_conclusion = {
        "trade_decision": {
            "ticker": selected_ticker,
            "value": latest_decision.get("decision"),
            "label": _humanize_label(latest_decision.get("decision")) or _EMPTY_MARKER,
            "strategy_id": latest_decision.get("selected_strategy_id") or _EMPTY_MARKER,
            "strategy_label": strategy_label(latest_decision.get("selected_strategy_id")) or _EMPTY_MARKER,
            "expression_bucket_id": latest_decision.get("expression_bucket_id") or _EMPTY_MARKER,
            "expression_bucket_label": expression_bucket_label(latest_decision.get("expression_bucket_id")) or _EMPTY_MARKER,
            "confidence": latest_decision.get("confidence"),
            "approved_weight": latest_decision.get("approved_weight"),
        },
        "signal_summary": signal_summary,
        "risk_summary": latest_risk_summary,
        "trade_plan": {
            "thesis": trade_summary,
            "time_horizon": _humanize_label(latest_decision.get("time_horizon")),
            "target_weight": latest_decision.get("target_weight"),
            "approved_weight": latest_decision.get("approved_weight"),
            "max_loss_pct": latest_decision.get("max_loss_pct"),
            "entry_plan": operator_text(metadata_json.get("entry_plan")) or None,
            "exit_plan": operator_text(metadata_json.get("exit_plan")) or None,
            "invalidators": tuple(invalidators),
        },
        "bull_bear": {
            "confidence": latest_decision.get("confidence"),
            "bull_points": tuple(key_drivers),
            "bear_points": tuple(counterarguments),
        },
        "signal_groups": signal_groups(latest_decision.get("core_signal_evidence")),
        "position_execution": {
            "position": position,
            "position_label": position.get("position_label"),
            "order_status": position.get("order_status") or latest_decision.get("order_status") or _EMPTY_MARKER,
            "order_status_label": order_status_label(position.get("order_status") or latest_decision.get("order_status"))
            or _EMPTY_MARKER,
            "summary": position.get("summary") or _EMPTY_MARKER,
            "fill_price": position.get("avg_fill_price") or position.get("entry_price") or position.get("avg_cost"),
            "filled_qty": position.get("filled_qty") or position.get("quantity"),
        },
    }
    if trade_summary != _EMPTY_MARKER:
        latest_conclusion["trade_decision"]["summary"] = trade_summary
    if key_drivers:
        latest_conclusion["trade_decision"]["key_drivers"] = key_drivers
    if counterarguments:
        latest_conclusion["trade_decision"]["counterarguments"] = counterarguments
    if invalidators:
        latest_conclusion["trade_decision"]["invalidators"] = invalidators
    if not latest_conclusion["trade_plan"]["entry_plan"]:
        latest_conclusion["trade_plan"]["entry_plan"] = operator_text(metadata_json.get("entry_plan")) or None
    if not latest_conclusion["trade_plan"]["exit_plan"]:
        latest_conclusion["trade_plan"]["exit_plan"] = operator_text(metadata_json.get("exit_plan")) or None

    timeline = _build_timeline(
        signal_history=signal_history,
        decisions=decision_history,
        risk_history=risk_history,
        latest_signal_summary=signal_summary,
        latest_risk_summary=latest_risk_summary,
    )
    tabs = {
        "timeline": timeline,
        "history_highlights": _build_history_highlights(timeline),
        "trend": {
            "technical": technical_charts,
            "news": news_snippets,
            "fundamental": fundamental_snippets,
        },
        "decisions": _build_decision_list(decision_history),
        "risk": {
            "current_stance": latest_conclusion["risk_summary"],
            "position_state": position,
            "history": risk_history,
        },
    }

    return {
        "ticker": selected_ticker,
        "lifecycle": _build_lifecycle(
            latest_decision=latest_decision,
            decisions=decision_history,
            position=position,
            closed_position=closed_position,
        ),
        "latest_conclusion": latest_conclusion,
        "tabs": tabs,
    }


def _risk_override_trade_summary(latest_decision: dict[str, Any], risk: dict[str, Any]) -> str | None:
    decision = str(latest_decision.get("decision") or "").strip().lower()
    if decision not in {"reduce", "exit"}:
        return None

    target_weight = _float_or_none(latest_decision.get("target_weight"))
    approved_weight = _float_or_none(latest_decision.get("approved_weight"))
    if target_weight not in (None, 0.0) or approved_weight not in (None, 0.0):
        return None

    reason = str(risk.get("reason") or "").strip()
    lookahead_risk_source = str(risk.get("lookahead_risk_source") or "").strip()
    if "force_reduce" not in reason and "lookahead" not in reason and not lookahead_risk_source:
        return None

    trade_identity = latest_decision.get("trade_identity") or "position"
    risk_source = lookahead_risk_source or "lookahead"
    return (
        f"{_humanize_label(decision)} {operator_text(trade_identity).lower()} exposure to zero "
        f"because lookahead {operator_text(risk_source).lower()} risk required closing the position."
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _build_signal_summary(signal_history: Any) -> dict[str, Any]:
    summary_items = signal_history.get("summary") if isinstance(signal_history, dict) else signal_history
    timeline_items = signal_history.get("timeline") if isinstance(signal_history, dict) else None
    bullets = _dedupe_summary_bullets(summary_items)
    if bullets == [_EMPTY_MARKER]:
        return {
            "summary_bullets": bullets,
            "hidden_bullet_count": 0,
            "latest_signal_time_label": _latest_signal_time_label(timeline_items),
            "primary_sections": ({"label": "Status", "bullets": (_EMPTY_MARKER,)},),
            "grouped_sections": (),
        }

    grouped = _group_summary_bullets(bullets)
    if len(bullets) <= 5:
        primary = bullets
        hidden_count = 0
    else:
        ordered = []
        for label in _SIGNAL_GROUP_ORDER:
            ordered.extend(grouped.get(label, ()))
        primary = ordered[:5]
        hidden_count = max(len(ordered) - len(primary), 0)
    sections = tuple(
        {"label": label, "bullets": tuple(grouped[label])}
        for label in _SIGNAL_GROUP_ORDER
        if grouped.get(label)
    )
    return {
        "summary_bullets": primary,
        "hidden_bullet_count": hidden_count,
        "latest_signal_time_label": _latest_signal_time_label(timeline_items),
        "primary_sections": _primary_signal_sections(primary),
        "grouped_sections": sections,
    }

def _primary_signal_sections(primary_bullets: list[str]) -> tuple[dict[str, Any], ...]:
    grouped_primary = _group_summary_bullets(primary_bullets)
    return tuple(
        {"label": label, "bullets": tuple(grouped_primary[label])}
        for label in _SIGNAL_GROUP_ORDER
        if grouped_primary.get(label)
    )

def _dedupe_summary_bullets(summary_items: Any) -> list[str]:
    if isinstance(summary_items, list):
        bullets = []
        seen: set[str] = set()
        for item in summary_items:
            bullet = str(item).strip()
            if not bullet or bullet in seen:
                continue
            seen.add(bullet)
            bullets.append(operator_text(bullet))
        if bullets:
            return bullets
    return [_EMPTY_MARKER]

def _group_summary_bullets(bullets: list[str]) -> dict[str, list[str]]:
    grouped = {label: [] for label in _SIGNAL_GROUP_ORDER}
    for bullet in bullets:
        grouped[_summary_group_label(bullet)].append(bullet)
    return grouped

def _summary_group_label(bullet: str) -> str:
    normalized = bullet.strip().lower()
    if any(token in normalized for token in ("blocked", "risk ", "invalidator", "event cluster")):
        return "Risk blockers"
    if any(token in normalized for token in ("insider", "form 4", "cluster buy", "net buy")):
        return "Insider"
    if any(token in normalized for token in ("policy", "social", "tariff", "trump", "official update")):
        return "Policy / Social"
    if any(token in normalized for token in ("relative strength", "breakout", "trend", "volume", "price ")):
        return "Trend"
    if any(token in normalized for token in ("stale", "missing", "data quality", "freshness")):
        return "Data quality"
    if any(token in normalized for token in ("catalyst", "guidance", "earnings", "headline", "fresh ")):
        return "Evidence"
    return "Decision drivers"

def _build_technical_charts(technical_items: Any) -> list[dict[str, Any]]:
    items = technical_items if isinstance(technical_items, list) else []
    charts: list[dict[str, Any]] = []
    for chart_type, labels in _TECHNICAL_CHART_SPECS:
        source = next(
            (
                item
                for item in items
                if str(item.get("label") or "").strip().lower() in labels
            ),
            None,
        )
        if source is None:
            charts.append(
                {
                    "chart_type": chart_type,
                    "label": _EMPTY_MARKER,
                    "points": [],
                    "summary": _EMPTY_MARKER,
                    "empty": True,
                }
            )
            continue

        charts.append(
            {
                "chart_type": chart_type,
                "label": source.get("label") or _EMPTY_MARKER,
                "points": list(source.get("points") or []),
                "summary": source.get("summary") or _EMPTY_MARKER,
                "empty": False,
            }
        )
    return charts

def _build_snippets(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        return [_empty_snippet()]

    snippets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippets.append(
            {
                "title": operator_text(item.get("title")) or _EMPTY_MARKER,
                "summary": operator_text(item.get("summary")) or _EMPTY_MARKER,
                "time": item.get("published_at") or item.get("as_of"),
                "event_type": item.get("event_type"),
                "importance": item.get("importance"),
                "source": item.get("source"),
                "sentiment": item.get("sentiment"),
                "source_ticker": item.get("source_ticker"),
                "readthrough_source_ticker": item.get("readthrough_source_ticker"),
                "readthrough_label": item.get("readthrough_label"),
                "explicit_ticker_mention": item.get("explicit_ticker_mention"),
                "empty": False,
            }
        )
    snippets.sort(key=lambda item: _sort_key_desc(item.get("time")))
    return snippets or [_empty_snippet()]

def _build_event_news_summary(news_snippets: list[dict[str, Any]]) -> str | None:
    primary_snippet = next(
        (
            item
            for item in news_snippets
            if _is_material_news_snippet(item)
        ),
        None,
    )
    if primary_snippet is None:
        has_non_empty_news = any(not item.get("empty") for item in news_snippets)
        return _NO_MATERIAL_TICKER_NEWS if has_non_empty_news else None

    title = str(primary_snippet.get("title") or "").strip()
    summary = _truncate_news_text(str(primary_snippet.get("summary") or "").strip())
    if title and summary and summary != title:
        return f"{title}: {_with_terminal_period(summary)}"
    if summary:
        return _with_terminal_period(summary)
    if title:
        return _with_terminal_period(title)
    return None

def _item_last_updated_at(
    row: dict[str, Any],
    *,
    position: Any,
    closed_position: Any,
    risk: Any,
    signal_history: Any,
    news_items: Any,
    fundamental_items: Any,
) -> datetime | None:
    candidates: list[datetime] = []
    _append_candidate_times(candidates, row)
    _append_candidate_times(candidates, position)
    _append_candidate_times(candidates, closed_position)
    _append_candidate_times(candidates, risk)

    if isinstance(signal_history, dict):
        _append_candidate_times(candidates, signal_history)
        for item in signal_history.get("timeline") or ():
            _append_candidate_times(candidates, item)

    for item in news_items or ():
        _append_candidate_times(candidates, item)
    for item in fundamental_items or ():
        _append_candidate_times(candidates, item)

    return max(candidates) if candidates else None

def _append_candidate_times(candidates: list[datetime], payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    for key in (
        "created_at",
        "decision_time",
        "time",
        "published_at",
        "as_of",
        "updated_at",
        "opened_at",
        "closed_at",
        "snapshot_time",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            candidates.append(parsed)
