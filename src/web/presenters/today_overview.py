"""Presenter helpers for the today overview command surface."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.web.presenters.today_copy import (
    generic_status_label,
    job_status_label,
    live_status_label,
    macro_regime_label,
    risk_appetite_label,
    runtime_mode_label,
)


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
    latest_preopen_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deduped_closed_positions = _dedupe_rows_by_ticker(closed_positions)
    open_positions = positions + option_positions
    resolved_live_status = _resolved_live_status(header=header, risk_macro=risk_macro)
    command_center = _build_command_center(
        header=header,
        risk_macro=risk_macro,
        live_status=resolved_live_status,
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
            value=_format_exposure(header.get("gross_exposure")),
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
                _operator_item("Runtime Mode", runtime_mode_label(header.get("runtime_mode")) or "Unavailable"),
                _operator_item("Alert Count", str(header.get("open_alert_count", 0)), tone=_alert_tone(header)),
            ),
            "context": (
                _operator_item("Macro Regime", macro_regime_label(header.get("macro_regime")) or "Unavailable", tone=_macro_tone(header)),
                _operator_item("Risk Appetite", risk_appetite_label(header.get("risk_appetite")) or "Unavailable"),
                _operator_item("Live Status", live_status_label(resolved_live_status) or "Unavailable", tone=_live_tone(resolved_live_status)),
                _operator_item("Job Status", _job_status(job_timeline)),
            ),
        },
        "metric_cards": metric_cards,
        "alert_bar": {
            "count": int(header.get("open_alert_count") or 0),
            "warning_banner": risk_macro.get("command_center", {}).get("warning_banner"),
        },
        "latest_preopen_run": _build_latest_preopen_run_view(latest_preopen_run),
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
        "attention_feed": _build_attention_feed(
            needs_review=command_center["needs_review"],
            live_alerts=live_alerts,
            material_changes=material_changes,
        ),
    }


_ATTENTION_PRIORITY = {"alert": 0, "review": 1, "signal": 2}


def _build_attention_feed(
    *,
    needs_review: tuple[dict[str, Any], ...],
    live_alerts: tuple[dict[str, Any], ...],
    material_changes: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Collapse alerts / reviews / signal changes into one entry per ticker.

    A ticker that appears as both (e.g.) a live alert and a material change
    renders as a single card with both badges instead of duplicate rows.
    """
    facets_by_ticker: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []

    def _add(ticker: Any, kind: str, badge: str, text: Any) -> None:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return
        if symbol not in facets_by_ticker:
            facets_by_ticker[symbol] = []
            order.append(symbol)
        facets_by_ticker[symbol].append(
            {"kind": kind, "badge": badge, "text": str(text or "").strip()}
        )

    for row in live_alerts or ():
        _add(row.get("ticker"), "alert", str(row.get("severity") or "Alert"), row.get("headline") or row.get("summary"))
    for row in needs_review or ():
        _add(row.get("ticker"), "review", "Review", row.get("summary"))
    for row in material_changes or ():
        _add(row.get("ticker"), "signal", "Signal", row.get("summary"))

    feed: list[dict[str, Any]] = []
    for symbol in order:
        facets = sorted(
            facets_by_ticker[symbol],
            key=lambda facet: _ATTENTION_PRIORITY.get(facet["kind"], 9),
        )
        feed.append(
            {
                "ticker": symbol,
                "primary_kind": facets[0]["kind"],
                "facets": tuple(facets),
            }
        )
    feed.sort(key=lambda entry: _ATTENTION_PRIORITY.get(entry["primary_kind"], 9))
    return tuple(feed)


def _build_command_center(
    *,
    header: dict[str, Any],
    risk_macro: dict[str, Any],
    live_status: str,
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
    for row in tuple(risk_macro.get("summary", {}).get("availability_issues") or ()):
        label = str(row.get("label") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if label and summary:
            system_issues.append({"label": label, "summary": summary})
    if str(header.get("macro_regime") or "").strip().lower() == "unavailable":
        macro_issue = {
            "label": "Macro regime unavailable",
            "summary": "Global macro regime data is unavailable.",
        }
        if macro_issue not in system_issues:
            system_issues.append(macro_issue)
    if (
        str(live_status or "").strip().lower() == "degraded"
        and str(header.get("macro_regime") or "").strip().lower() != "unavailable"
        and not system_issues
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


def _build_latest_preopen_run_view(latest_preopen_run: dict[str, Any] | None) -> dict[str, Any]:
    if not latest_preopen_run:
        return {
            "status_label": "Unavailable",
            "as_of_label": None,
            "completed_at_label": None,
            "execution_mode_label": None,
            "headline": None,
            "summary_tiles": (),
            "empty_copy": "No persisted preopen run is available for the current trade date yet.",
        }

    summary = dict(latest_preopen_run.get("summary_json") or {})
    execution = dict(latest_preopen_run.get("execution_json") or {})
    return {
        "status_label": generic_status_label(latest_preopen_run.get("status")) or "Unavailable",
        "as_of_label": _format_timestamp_label(latest_preopen_run.get("as_of")),
        "completed_at_label": _format_timestamp_label(latest_preopen_run.get("completed_at")),
        "execution_mode_label": runtime_mode_label(execution.get("mode")) if execution.get("mode") else None,
        "headline": _preopen_headline(summary=summary, execution=execution),
        "summary_tiles": (
            {"label": "Signals", "value": str(int(summary.get("signal_snapshot_count", 0) or 0))},
            {"label": "Candidates", "value": str(int(summary.get("candidate_count", 0) or 0))},
            {"label": "Classifications", "value": str(int(summary.get("classification_count", 0) or 0))},
            {"label": "Risk Decisions", "value": str(int(summary.get("risk_decision_count", 0) or 0))},
            {"label": "Trading Decisions", "value": str(int(summary.get("trading_decision_count", 0) or 0))},
            {"label": "Orders Submitted", "value": str(int(execution.get("orders_submitted", 0) or 0))},
        ),
        "empty_copy": None,
    }


def _preopen_headline(*, summary: dict[str, Any], execution: dict[str, Any]) -> str:
    signals = int(summary.get("signal_snapshot_count", 0) or 0)
    candidates = int(summary.get("candidate_count", 0) or 0)
    risk_decisions = int(summary.get("risk_decision_count", 0) or 0)
    trading_decisions = int(summary.get("trading_decision_count", 0) or 0)
    mode = str(execution.get("mode") or "").strip().lower()

    if signals <= 0:
        return "Preopen started, but no signal snapshots were built."
    if candidates <= 0:
        return "Signals built, but no candidates were selected."
    if risk_decisions <= 0:
        return "Candidates scored, but none reached risk approval."
    if trading_decisions <= 0:
        return "Risk approved candidates, but no trading decisions were generated."
    if mode == "dry_run":
        return "Trading decisions were generated in dry-run mode."
    return "Trading decisions were generated and execution was enabled."


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
    status = job_status_label(latest.get("status")) or ""
    return f"{label} / {status}".strip(" /")


def _format_metric_value(label: str, value: Any) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        lowered = label.lower()
        if "cost" in lowered or "p&l" in lowered or "value" in lowered or "power" in lowered:
            return f"${value:,.2f}"
        if "exposure" in lowered:
            return f"{value:,.2f}"
    return str(value)


def _format_exposure(value: Any) -> str | Decimal | None:
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric) <= Decimal("1"):
        return f"{float(numeric) * 100:.1f}%"
    return numeric


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


def _live_tone(live_status: Any) -> str:
    status = str(live_status or "").strip().lower()
    return "warning" if status == "degraded" else "neutral"


def _resolved_live_status(*, header: dict[str, Any], risk_macro: dict[str, Any]) -> str:
    if str(risk_macro.get("availability", {}).get("status") or "").strip().lower() == "degraded":
        return "degraded"
    return str(header.get("live_status") or "").strip().lower() or "unavailable"


def _alert_tone(header: dict[str, Any]) -> str:
    return "warning" if int(header.get("open_alert_count") or 0) > 0 else "neutral"
