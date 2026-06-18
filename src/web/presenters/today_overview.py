"""Presenter helpers for the today overview command surface."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def build_today_overview(
    *,
    header: dict[str, Any],
    job_timeline: tuple[dict[str, Any], ...],
    risk_macro: dict[str, Any],
    live_alerts: tuple[dict[str, Any], ...],
    material_changes: tuple[dict[str, Any], ...],
    positions: tuple[dict[str, Any], ...],
    option_positions: tuple[dict[str, Any], ...],
    closed_positions: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    deduped_closed_positions = _dedupe_rows_by_ticker(closed_positions)
    open_positions = positions + option_positions
    command_center = _build_command_center(
        header=header,
        open_positions=open_positions,
        closed_positions=deduped_closed_positions,
    )
    metric_cards = (
        _metric_card(
            label="Net Liquidation Value",
            value=header.get("nav"),
            source_of_truth_label="Broker equity snapshot",
            updated_at=_risk_macro_updated_at(risk_macro),
        ),
        _metric_card(
            label="Day P&L",
            value=header.get("day_pnl"),
            source_of_truth_label="Broker session mark",
            basis_note="Review-window realized and unrealized session P&L.",
            updated_at=_risk_macro_updated_at(risk_macro),
            tone="positive" if _is_positive(header.get("day_pnl")) else "warning",
        ),
        _metric_card(
            label="Buying Power",
            value=header.get("buying_power"),
            source_of_truth_label="Broker margin snapshot",
            updated_at=_risk_macro_updated_at(risk_macro),
        ),
        _metric_card(
            label="Gross Exposure",
            value=_format_percent(header.get("gross_exposure")),
            source_of_truth_label="Risk snapshot exposure usage",
            updated_at=_risk_macro_updated_at(risk_macro),
        ),
        _metric_card(
            label="Estimated AI Cost",
            value=header.get("llm_cost_estimate"),
            source_of_truth_label="Estimated API and model usage",
            basis_note="Estimated provider and model usage, not settled billing.",
            updated_at=_risk_macro_updated_at(risk_macro),
        ),
    )
    summary_items = tuple(
        item
        for item in (
            f"{header.get('open_alert_count', 0)} open alerts" if header.get("open_alert_count") is not None else None,
            f"{header.get('material_signal_change_count', 0)} material signal changes"
            if header.get("material_signal_change_count") is not None
            else None,
            f"{len(open_positions)} open positions" if open_positions else None,
            f"{len(deduped_closed_positions)} closed tickers pending review" if deduped_closed_positions else None,
        )
        if item
    )
    primary_summary = summary_items[:2] or ("No immediate session issues recorded.",)
    hidden_count = max(len(summary_items) - len(primary_summary), 0)
    updated_at = _risk_macro_updated_at(risk_macro)
    return {
        "operator_strip": {
            "primary": (
                _operator_item("Market Phase", header.get("market_phase") or "Unavailable"),
                _operator_item("Runtime Mode", _humanize_label(header.get("runtime_mode")) or "Unavailable"),
                _operator_item("Alert Count", str(header.get("open_alert_count", 0)), tone=_alert_tone(header)),
            ),
            "context": (
                _operator_item("Macro Regime", header.get("macro_regime") or "unavailable", tone=_macro_tone(header)),
                _operator_item("Risk Appetite", _humanize_label(header.get("risk_appetite")) or "Unavailable"),
                _operator_item("Live Status", _humanize_label(header.get("live_status")) or "Unavailable", tone=_live_tone(header)),
                _operator_item("Job Status", _job_status(job_timeline)),
            ),
        },
        "metric_cards": metric_cards,
        "alert_bar": {
            "count": int(header.get("open_alert_count") or 0),
            "warning_banner": risk_macro.get("command_center", {}).get("warning_banner"),
        },
        "current_summary": {
            "headline": (
                "Macro and execution context require active operator review."
                if risk_macro.get("availability", {}).get("status") == "degraded"
                else "Session context is stable and the operator queue is bounded."
            ),
            "items": primary_summary,
            "hidden_item_count": hidden_count,
            "meta": {
                "updated_at_label": _format_timestamp_label(updated_at),
                "source_of_truth_label": "Combined route summary",
                "basis_note": risk_macro.get("command_center", {}).get("basis_note"),
                "degraded_reasons": tuple(risk_macro.get("availability", {}).get("issues") or ()),
            },
        },
        "command_center": command_center,
        "live_alerts": live_alerts,
        "material_changes": material_changes,
    }


def _build_command_center(
    *,
    header: dict[str, Any],
    open_positions: tuple[dict[str, Any], ...],
    closed_positions: tuple[dict[str, Any], ...],
) -> dict[str, tuple[dict[str, Any], ...]]:
    needs_review = tuple(
        {
            "ticker": str(row.get("ticker") or "").strip().upper(),
            "summary": row.get("summary") or "Closed recently and ready for review",
        }
        for row in closed_positions
        if str(row.get("ticker") or "").strip()
    )
    open_positions = tuple(
        {
            "ticker": str(row.get("ticker") or "").strip().upper(),
            "summary": _open_position_summary(row),
        }
        for row in open_positions
        if str(row.get("ticker") or "").strip()
    )
    system_issues: list[dict[str, Any]] = []
    if str(header.get("macro_regime") or "").strip().lower() == "unavailable":
        system_issues.append(
            {
                "label": "Macro regime unavailable",
                "summary": "Global macro regime data is unavailable.",
            }
        )
    if (
        str(header.get("live_status") or "").strip().lower() == "degraded"
        and str(header.get("macro_regime") or "").strip().lower() != "unavailable"
    ):
        system_issues.append(
            {
                "label": "Live context degraded",
                "summary": "One or more canonical feeds are degraded; verify operator posture before acting.",
            }
        )
    if not system_issues and not needs_review and not open_positions:
        system_issues.append(
            {
                "label": "No active issues",
                "summary": "No command-center issues are currently active.",
            }
        )
    return {
        "needs_review": needs_review,
        "open_positions": open_positions,
        "system_issues": tuple(system_issues),
    }


def _open_position_summary(row: dict[str, Any]) -> str:
    summary = str(row.get("summary") or "").strip()
    if summary:
        return summary
    if row.get("option_strategy_type") is not None or row.get("max_loss") is not None:
        max_loss = row.get("max_loss")
        if isinstance(max_loss, Decimal):
            return f"Open option position, max loss ${max_loss:,.2f}"
        if max_loss is not None:
            return f"Open option position, max loss {max_loss}"
        return "Open option position"
    return "Open position, risk within limits"


def _dedupe_rows_by_ticker(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        deduped.append(row)
    return tuple(deduped)


def _metric_card(
    *,
    label: str,
    value: Any,
    source_of_truth_label: str,
    updated_at: Any,
    basis_note: str | None = None,
    tone: str = "neutral",
) -> dict[str, Any]:
    return {
        "metric_id": label.lower().replace(" ", "_"),
        "label": label,
        "primary_value": _format_metric_value(label, value),
        "secondary_value": None,
        "tone": tone,
        "meta": {
            "updated_at_label": _format_timestamp_label(updated_at),
            "refresh_mode_label": None,
            "source_of_truth_label": source_of_truth_label,
            "basis_note": basis_note,
            "degraded_reasons": (),
        },
    }


def _operator_item(label: str, value: str, *, tone: str = "neutral") -> dict[str, str]:
    return {"label": label, "value": value, "tone": tone}


def _job_status(job_timeline: tuple[dict[str, Any], ...]) -> str:
    if not job_timeline:
        return "Unavailable"
    latest = job_timeline[0]
    label = str(latest.get("label") or "").strip()
    status = str(latest.get("status") or "").strip()
    return f"{label} / {status}".strip(" /")


def _format_metric_value(label: str, value: Any) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, Decimal):
        lowered = label.lower()
        if "cost" in lowered or "p&l" in lowered or "value" in lowered or "power" in lowered:
            return f"${value:,.2f}"
    return str(value)


def _format_percent(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_timestamp_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _risk_macro_updated_at(risk_macro: dict[str, Any]) -> Any:
    return (
        risk_macro.get("command_center", {}).get("updated_at")
        or risk_macro.get("updated_at")
        or risk_macro.get("availability", {}).get("updated_at")
    )


def _is_positive(value: Any) -> bool:
    try:
        return Decimal(value) >= 0
    except Exception:
        return False


def _macro_tone(header: dict[str, Any]) -> str:
    regime = str(header.get("macro_regime") or "").strip().lower()
    return "warning" if regime in {"risk_off", "unavailable"} else "neutral"


def _live_tone(header: dict[str, Any]) -> str:
    status = str(header.get("live_status") or "").strip().lower()
    return "warning" if status == "degraded" else "neutral"


def _alert_tone(header: dict[str, Any]) -> str:
    return "warning" if int(header.get("open_alert_count") or 0) > 0 else "neutral"


def _humanize_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.replace("_", " ").replace("-", " ").split())
