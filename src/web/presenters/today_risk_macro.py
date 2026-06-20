"""Backend risk/macro presenter for the today workstation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.web.presenters.today_copy import (
    event_type_label,
    macro_regime_label,
    operator_text,
    recommended_action_label,
    risk_appetite_label,
    risk_source_label,
)


def build_today_risk_macro_payload(
    *,
    latest_risk: object | None,
    latest_intent: object | None,
    risk_macro_context: dict[str, object] | None,
    exposures: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    context = risk_macro_context or {}
    macro_snapshot = context.get("macro_snapshot")
    calendar_events = tuple(context.get("calendar_events") or ())
    event_assessments = tuple(context.get("portfolio_event_risk_assessments") or ())

    binding_constraints = tuple(
        getattr(latest_intent, "binding_constraints", None)
        or getattr(latest_risk, "concentration_flags_json", None)
        or ()
    )
    availability = _availability(
        macro_snapshot=macro_snapshot,
        latest_intent=latest_intent,
        latest_risk=latest_risk,
    )
    top_risk_sources = _top_risk_sources(
        latest_intent=latest_intent,
        event_assessments=event_assessments,
        binding_constraints=binding_constraints,
        exposures=exposures,
    )
    return {
        "risk_config_version": getattr(latest_risk, "resolver_version", None),
        "command_center": {
            "regime": macro_regime_label(getattr(macro_snapshot, "regime", None) or "unavailable"),
            "risk_appetite_label": risk_appetite_label(getattr(latest_risk, "risk_appetite", None) or "unavailable"),
            "exposure_usage_pct": _exposure_usage_pct(latest_risk),
            "event_risk_level": _event_risk_level(event_assessments),
            "favored_exposures": tuple(_string_list(_macro_metadata(macro_snapshot).get("favored_exposures"))),
            "avoided_exposures": tuple(
                _string_list(_macro_metadata(macro_snapshot).get("avoided_exposures"))
                or _string_list(getattr(macro_snapshot, "blocked_strategy_tags", ()))
            ),
            "hedge_posture": _hedge_posture(latest_intent),
            "warning_banner": _warning_banner(macro_snapshot=macro_snapshot, availability=availability),
            "operator_note": _operator_note(
                macro_snapshot=macro_snapshot,
                event_assessments=event_assessments,
                top_risk_sources=top_risk_sources,
            ),
            "updated_at": _updated_at(macro_snapshot=macro_snapshot, latest_risk=latest_risk),
            "basis_note": _basis_note(macro_snapshot=macro_snapshot),
        },
        "summary": {
            "risk_status": _risk_status(latest_intent=latest_intent),
            "top_risk_sources": top_risk_sources,
            "availability_issues": tuple(
                {"label": _availability_label(item), "summary": _availability_summary(item)}
                for item in availability["issues"]
            ),
        },
        "macro": {
            "regime": macro_regime_label(getattr(macro_snapshot, "regime", None) or "unavailable"),
            "risk_budget_multiplier": getattr(macro_snapshot, "risk_budget_multiplier", None),
            "blocked_strategy_tags": tuple(getattr(macro_snapshot, "blocked_strategy_tags", ()) or ()),
            "invalidators": tuple(getattr(macro_snapshot, "invalidators", ()) or ()),
            "updated_at": getattr(macro_snapshot, "snapshot_time", None),
            "basis_note": _basis_note(macro_snapshot),
        },
        "events": tuple(_event_row(event) for event in calendar_events if _default_visible_event(event)),
        "risk_sources": tuple(_risk_source_row(assessment) for assessment in event_assessments if _default_visible_assessment(assessment)),
        "exposures": exposures,
        "binding_constraints": binding_constraints,
        "availability": availability,
        "updated_at": _updated_at(macro_snapshot=macro_snapshot, latest_risk=latest_risk),
        "basis_note": _basis_note(macro_snapshot),
    }


def _risk_status(*, latest_intent: object | None) -> str:
    aggregate = str(getattr(latest_intent, "aggregate_risk_state", "") or "").lower()
    if aggregate in {"", "risk_normalized"}:
        return "Within Limits"
    return _humanize_identifier(aggregate)


def _top_risk_sources(
    *,
    latest_intent: object | None,
    event_assessments: tuple[object, ...],
    binding_constraints: tuple[str, ...],
    exposures: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    metadata_json = dict(getattr(latest_intent, "metadata_json", {}) or {})
    source_keys = list(_string_list(metadata_json.get("top_risk_sources")))
    if not source_keys:
        source_keys = [str(getattr(item, "risk_source", "")) for item in event_assessments if getattr(item, "risk_source", None)]
    rows: list[dict[str, Any]] = []
    for index, source_key in enumerate(source_keys[:3]):
        summary = binding_constraints[index] if index < len(binding_constraints) else _risk_source_summary(source_key)
        rows.append({"label": _risk_source_label(source_key, exposures=exposures), "summary": operator_text(summary)})
    if not rows and exposures:
        first = exposures[0]
        rows.append(
            {
                "label": f"{first.get('factor_name') or 'Portfolio'} concentration",
                "summary": operator_text(binding_constraints[0]) if binding_constraints else "theme cap near limit",
            }
        )
    elif not rows and binding_constraints:
        rows.extend({"label": "Constraint pressure", "summary": operator_text(item)} for item in binding_constraints[:3])
    return tuple(rows)


def _availability(*, macro_snapshot: object | None, latest_intent: object | None, latest_risk: object | None) -> dict[str, Any]:
    issues = []
    metadata_json = dict(getattr(macro_snapshot, "metadata_json", {}) or {})
    for item in _string_list(metadata_json.get("availability_issues")):
        if item not in issues:
            issues.append(item)
    intent_metadata = dict(getattr(latest_intent, "metadata_json", {}) or {})
    for item in _string_list(intent_metadata.get("data_availability_issues")):
        if item not in issues:
            issues.append(item)
    if macro_snapshot is None and "macro_regime_unavailable" not in issues:
        issues.append("macro_regime_unavailable")
    freshness = dict(getattr(macro_snapshot, "source_freshness", {}) or {})
    return {
        "status": "degraded" if issues else "available",
        "issues": tuple(issues),
        "source_freshness": freshness,
        "updated_at": getattr(macro_snapshot, "snapshot_time", None),
        "basis_note": _basis_note(macro_snapshot),
    }


def _event_row(event: object) -> dict[str, Any]:
    return {
        "scheduled_at": getattr(event, "event_time", None),
        "event_type": getattr(event, "event_type", None),
        "event_type_label": event_type_label(getattr(event, "event_type", None)),
        "importance": getattr(event, "severity_hint", None),
        "portfolio_risk_level": getattr(event, "severity_hint", None),
        "affected_ticker": getattr(event, "ticker", None),
        "risk_mechanism": getattr(event, "title", None),
        "updated_at": getattr(event, "available_for_decision_at", None),
        "basis_note": getattr(event, "source", None),
    }


def _risk_source_row(assessment: object) -> dict[str, Any]:
    metadata_json = dict(getattr(assessment, "metadata_json", {}) or {})
    return {
        "ticker": getattr(assessment, "ticker", None),
        "risk_source": getattr(assessment, "risk_source", None),
        "risk_source_label": risk_source_label(getattr(assessment, "risk_source", None)),
        "severity": getattr(assessment, "severity", None),
        "recommended_action": getattr(assessment, "recommended_action", None),
        "recommended_action_label": recommended_action_label(getattr(assessment, "recommended_action", None)),
        "rationale": getattr(assessment, "rationale", None),
        "material_change": bool(metadata_json.get("material_change")),
        "updated_at": getattr(assessment, "available_for_decision_at", None),
        "basis_note": metadata_json.get("why_visible") or metadata_json.get("summary_bucket"),
    }


def _default_visible_event(event: object) -> bool:
    metadata_json = dict(getattr(event, "metadata_json", {}) or {})
    return metadata_json.get("default_visibility", "show") != "hide"


def _default_visible_assessment(assessment: object) -> bool:
    metadata_json = dict(getattr(assessment, "metadata_json", {}) or {})
    return metadata_json.get("default_visibility", "show") != "hide"


def _event_risk_level(event_assessments: tuple[object, ...]) -> str:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "watch": 1, "low": 0}
    highest = "low"
    for assessment in event_assessments:
        severity = str(getattr(assessment, "severity", "low") or "low").lower()
        if severity_rank.get(severity, -1) > severity_rank.get(highest, -1):
            highest = severity
    return _humanize_identifier(highest)


def _warning_banner(*, macro_snapshot: object | None, availability: dict[str, Any]) -> str | None:
    if availability["issues"]:
        return "Risk context degraded; review macro and provider availability before acting."
    if str(getattr(macro_snapshot, "regime", "") or "").lower() == "risk_off":
        return "Macro regime is risk off; sizing and new risk should remain conservative."
    return None


def _operator_note(
    *,
    macro_snapshot: object | None,
    event_assessments: tuple[object, ...],
    top_risk_sources: tuple[dict[str, Any], ...],
) -> str:
    if str(getattr(macro_snapshot, "regime", "") or "").lower() == "risk_off":
        return "Macro snapshot is risk off and should anchor operator posture."
    if event_assessments:
        return f"{len(event_assessments)} canonical event-risk row(s) are active for the current decision window."
    if top_risk_sources:
        return top_risk_sources[0]["summary"]
    return "No material macro or event-risk issue is currently active."


def _hedge_posture(latest_intent: object | None) -> dict[str, Any] | None:
    metadata_json = dict(getattr(latest_intent, "metadata_json", {}) or {})
    posture = metadata_json.get("hedge_posture")
    return dict(posture) if isinstance(posture, dict) else None


def _exposure_usage_pct(latest_risk: object | None) -> float | None:
    gross_exposure = getattr(latest_risk, "gross_exposure", None)
    if gross_exposure is None:
        return None
    exposure_ratio = _exposure_ratio(gross_exposure, getattr(latest_risk, "account_equity", None))
    if exposure_ratio is None:
        return None
    return round(exposure_ratio * 100.0, 2)


def _updated_at(*, macro_snapshot: object | None, latest_risk: object | None) -> datetime | None:
    return getattr(macro_snapshot, "snapshot_time", None) or getattr(latest_risk, "decision_time", None)


def _basis_note(macro_snapshot: object | None) -> str | None:
    return _macro_metadata(macro_snapshot).get("basis_note")


def _macro_metadata(macro_snapshot: object | None) -> dict[str, Any]:
    return dict(getattr(macro_snapshot, "metadata_json", {}) or {})


def _risk_source_label(source_key: str, *, exposures: tuple[dict[str, Any], ...]) -> str:
    normalized = str(source_key or "").strip().lower()
    if normalized == "macro":
        return "Macro regime"
    if normalized == "own_event":
        return "Own event window"
    if normalized in {"sector_event_cluster", "event_cluster"}:
        first = exposures[0] if exposures else {}
        factor_name = str(first.get("factor_name") or "Portfolio").strip()
        return f"{factor_name} concentration"
    return _humanize_identifier(normalized)


def _risk_source_summary(source_key: str) -> str:
    normalized = str(source_key or "").strip().lower()
    if normalized == "macro":
        return "Macro regime is constraining risk appetite."
    if normalized == "own_event":
        return "Upcoming own-event risk is driving tactical caution."
    if normalized in {"sector_event_cluster", "event_cluster"}:
        return "Clustered event risk is driving hedge posture."
    return _humanize_identifier(normalized)


def _availability_summary(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"macro_regime_unavailable", "global_context_failed"}:
        return "Global macro regime data is unavailable."
    if normalized == "global_context_stale":
        return "Global macro inputs are stale."
    return _humanize_identifier(normalized)


def _availability_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"macro_regime_unavailable", "global_context_failed"}:
        return "Macro regime unavailable"
    if normalized == "global_context_stale":
        return "Macro inputs stale"
    return _humanize_identifier(normalized)


def _humanize_identifier(value: object) -> str:
    normalized = str(value or "").strip().replace("_", " ")
    if not normalized:
        return ""
    return " ".join(part.capitalize() for part in normalized.split())


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _exposure_ratio(exposure: object, account_equity: object) -> float | None:
    exposure_value = _to_float(exposure)
    if exposure_value is None:
        return None
    if abs(exposure_value) <= 1.0:
        return exposure_value

    equity_value = _to_float(account_equity)
    if equity_value is None or equity_value == 0.0:
        return None
    return exposure_value / equity_value


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
