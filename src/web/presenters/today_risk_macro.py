"""Backend risk/macro presenter for the today workstation."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from src.web.presenters.today_copy import (
    event_type_label,
    macro_regime_label,
    operator_text,
    recommended_action_label,
    risk_appetite_label,
    risk_source_label,
)

_MACRO_INDICATOR_ORDER = ("vix", "oil_price", "gold_price", "us_treasury_10y")
_MACRO_INDICATOR_DEFAULTS = {
    "vix": {"label": "CBOE Volatility Index", "unit": "index"},
    "oil_price": {"label": "WTI Crude Oil Spot Price", "unit": "USD/bbl"},
    "gold_price": {"label": "Gold Proxy (GLD ETF)", "unit": "USD/share"},
    "us_treasury_10y": {"label": "US Treasury 10Y", "unit": "pct"},
}
_SHOW_PREVIOUS_CLOSE_RETURN = {"vix", "oil_price", "gold_price"}


def build_today_risk_macro_payload(
    *,
    latest_risk: object | None,
    latest_intent: object | None,
    risk_macro_context: dict[str, object] | None,
    exposures: tuple[dict[str, Any], ...],
    as_of: datetime | None = None,
) -> dict[str, Any]:
    context = risk_macro_context or {}
    macro_snapshot = context.get("macro_snapshot")
    calendar_events = _dedupe_calendar_events(tuple(context.get("calendar_events") or ()), as_of=as_of)
    event_assessments = _dedupe_risk_assessments(tuple(context.get("portfolio_event_risk_assessments") or ()))
    macro_news = _display_news_rows(
        tuple(context.get("macro_news") or ()),
        row_builder=_macro_news_row,
        limit=6,
        as_of=as_of,
    )
    event_news = _display_news_rows(
        tuple(context.get("event_news") or ()),
        row_builder=_event_news_row,
        limit=8,
        as_of=as_of,
    )

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
        "macro_indicators": _macro_indicator_rows(macro_snapshot),
        "events": tuple(
            _event_row(event)
            for event in sorted(calendar_events, key=_event_sort_key)
            if _default_visible_event(event)
            and _is_upcoming_event(event, as_of)
            and _is_in_visible_event_window(event, as_of)
        ),
        "risk_sources": tuple(_risk_source_row(assessment) for assessment in event_assessments if _default_visible_assessment(assessment)),
        "macro_news": macro_news,
        "event_news": event_news,
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


def _dedupe_calendar_events(events: tuple[object, ...], *, as_of: datetime | None = None) -> tuple[object, ...]:
    deduped: dict[tuple[Any, ...], object] = {}
    for event in events:
        key = _calendar_event_key(event)
        current = deduped.get(key)
        if current is None or _prefer_calendar_event(event, current, as_of=as_of):
            deduped[key] = event
    return tuple(deduped.values())


def _calendar_event_key(event: object) -> tuple[Any, ...]:
    event_type = str(getattr(event, "event_type", "") or "").strip().lower()
    ticker = str(getattr(event, "ticker", "") or "").strip().upper()
    if "earn" in event_type and ticker:
        return ("earnings", ticker)
    event_key = str(getattr(event, "event_key", "") or "").strip()
    if event_key:
        return ("event_key", event_key)
    return (event_type, ticker, getattr(event, "event_time", None))


def _prefer_calendar_event(candidate: object, current: object, *, as_of: datetime | None) -> bool:
    if _calendar_event_key(candidate)[0] == "earnings":
        candidate_upcoming = _is_upcoming_event(candidate, as_of)
        current_upcoming = _is_upcoming_event(current, as_of)
        if candidate_upcoming != current_upcoming:
            return candidate_upcoming
        candidate_available = _sort_timestamp(getattr(candidate, "available_for_decision_at", None))
        current_available = _sort_timestamp(getattr(current, "available_for_decision_at", None))
        if candidate_available != current_available:
            return candidate_available >= current_available
        return _sort_timestamp(getattr(candidate, "event_time", None)) < _sort_timestamp(
            getattr(current, "event_time", None)
        )
    return _sort_timestamp(getattr(candidate, "available_for_decision_at", None)) >= _sort_timestamp(
        getattr(current, "available_for_decision_at", None)
    )


def _dedupe_risk_assessments(assessments: tuple[object, ...]) -> tuple[object, ...]:
    deduped: dict[tuple[Any, ...], object] = {}
    for assessment in assessments:
        key = (
            str(getattr(assessment, "ticker", "") or "").strip().upper(),
            str(getattr(assessment, "risk_source", "") or "").strip().lower(),
            str(getattr(assessment, "event_type", "") or "").strip().lower(),
            str(getattr(assessment, "recommended_action", "") or "").strip().lower(),
        )
        current = deduped.get(key)
        if current is None or _sort_timestamp(getattr(assessment, "available_for_decision_at", None)) >= _sort_timestamp(
            getattr(current, "available_for_decision_at", None)
        ):
            deduped[key] = assessment
    return tuple(deduped.values())


def _sort_timestamp(value: Any) -> tuple[int, str]:
    if hasattr(value, "timestamp"):
        try:
            return (1, f"{value.timestamp():020.6f}")
        except (OSError, OverflowError, ValueError):
            pass
    return (0, str(value or ""))


def _event_sort_key(event: object) -> tuple[tuple[int, str], str]:
    return (
        _sort_timestamp(getattr(event, "event_time", None)),
        str(getattr(event, "event_key", "") or ""),
    )


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
        if _normalized_source_key(source_key) == "own_event":
            rows.append(_portfolio_event_risk_source_row(event_assessments=event_assessments, exposures=exposures))
            continue
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


def _portfolio_event_risk_source_row(
    *,
    event_assessments: tuple[object, ...],
    exposures: tuple[dict[str, Any], ...],
) -> dict[str, str]:
    factor_name = _portfolio_risk_factor_name(exposures) or "Portfolio"
    high_impact = any(
        _normalized_source_key(getattr(item, "risk_source", None)) == "own_event"
        and str(getattr(item, "severity", "") or "").strip().lower() in {"critical", "high"}
        for item in event_assessments
    )
    summary = (
        "High-impact portfolio events are driving tactical caution."
        if high_impact
        else "Portfolio event windows are driving tactical caution."
    )
    return {"label": f"{factor_name} event risk", "summary": summary}


def _portfolio_risk_factor_name(exposures: tuple[dict[str, Any], ...]) -> str | None:
    for exposure in exposures:
        factor_type = str(exposure.get("factor_type") or "").strip().lower()
        factor_name = str(exposure.get("factor_name") or "").strip()
        if factor_type in {"sector", "industry", "theme", "factor"} and factor_name:
            return factor_name
    return None


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


def _macro_indicator_rows(macro_snapshot: object | None) -> tuple[dict[str, Any], ...]:
    indicators = _macro_metadata(macro_snapshot).get("indicators")
    if not isinstance(indicators, dict):
        return ()
    rows: list[dict[str, Any]] = []
    for key in _MACRO_INDICATOR_ORDER:
        raw_payload = indicators.get(key)
        if not isinstance(raw_payload, dict):
            continue
        defaults = _MACRO_INDICATOR_DEFAULTS[key]
        value = _to_float(raw_payload.get("value"))
        unit = str(raw_payload.get("unit") or defaults["unit"])
        return_value = _to_float(raw_payload.get("return_vs_previous_close"))
        return_label = None
        return_tone = None
        if key in _SHOW_PREVIOUS_CLOSE_RETURN and return_value is not None:
            return_label = f"{return_value * 100:+.2f}% vs prev close"
            if return_value > 0:
                return_tone = "pos"
            elif return_value < 0:
                return_tone = "neg"
            else:
                return_tone = "flat"
        rows.append(
            {
                "key": key,
                "label": str(raw_payload.get("label") or defaults["label"]),
                "display_value": f"{_format_compact_number(value)} {unit}" if value is not None else "—",
                "observed_on": raw_payload.get("observed_on"),
                "return_label": return_label,
                "return_tone": return_tone,
            }
        )
    return tuple(rows)


def _event_row(event: object) -> dict[str, Any]:
    event_time = getattr(event, "event_time", None)
    return {
        "calendar_event_id": getattr(event, "calendar_event_id", None),
        "scheduled_at": event_time,
        "scheduled_at_label": _format_event_date(event_time),
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
        "calendar_event_id": getattr(assessment, "calendar_event_id", None),
        "ticker": getattr(assessment, "ticker", None),
        "risk_source": getattr(assessment, "risk_source", None),
        "risk_source_label": risk_source_label(getattr(assessment, "risk_source", None)),
        "severity": getattr(assessment, "severity", None),
        "event_type": getattr(assessment, "event_type", None),
        "days_until_event": getattr(assessment, "days_until_event", None),
        "recommended_action": getattr(assessment, "recommended_action", None),
        "recommended_action_label": recommended_action_label(getattr(assessment, "recommended_action", None)),
        "rationale": getattr(assessment, "rationale", None),
        "material_change": bool(metadata_json.get("material_change")),
        "updated_at": getattr(assessment, "available_for_decision_at", None),
        "basis_note": metadata_json.get("why_visible") or metadata_json.get("summary_bucket"),
    }


def _display_news_rows(
    items: tuple[object, ...],
    *,
    row_builder: Callable[[object], dict[str, Any]],
    limit: int,
    as_of: datetime | None,
) -> tuple[dict[str, Any], ...]:
    deduped: dict[str, object] = {}
    for item in items:
        if not _is_recent_news(item, as_of):
            continue
        key = _news_dedupe_key(item)
        current = deduped.get(key)
        if current is None or _sort_timestamp(getattr(item, "available_for_decision_at", None)) >= _sort_timestamp(
            getattr(current, "available_for_decision_at", None)
        ):
            deduped[key] = item
    rows = sorted(deduped.values(), key=_news_sort_key, reverse=True)
    return tuple(row_builder(item) for item in rows[:limit])


def _news_dedupe_key(item: object) -> str:
    headline = _normalized_story_text(
        _first_text(getattr(item, "title", None), getattr(item, "headline", None), getattr(item, "summary", None))
    )
    summary = _normalized_story_text(getattr(item, "summary", None))
    provider = _normalized_story_text(getattr(item, "provider", None))
    display_date = _display_date(getattr(item, "available_for_decision_at", None))
    if headline or summary:
        return f"story:{display_date or 'unknown'}:{provider}:{headline}:{summary}"
    return str(
        getattr(item, "dedupe_key", None)
        or getattr(item, "social_macro_item_id", None)
        or getattr(item, "event_news_item_id", None)
        or id(item)
    )


def _news_sort_key(item: object) -> tuple[tuple[int, str], str]:
    return (
        _sort_timestamp(getattr(item, "available_for_decision_at", None)),
        _news_dedupe_key(item),
    )


def _macro_news_row(item: object) -> dict[str, Any]:
    title = _first_text(getattr(item, "title", None), getattr(item, "summary", None))
    return {
        "news_id": getattr(item, "social_macro_item_id", None),
        "ticker": getattr(item, "ticker", None),
        "category": _humanize_identifier(getattr(item, "category", None)),
        "title": title,
        "headline": title,
        "summary": getattr(item, "summary", None),
        "source": getattr(item, "provider", None),
        "sentiment": getattr(item, "sentiment_direction", None) or getattr(item, "direction", None),
        "importance": getattr(item, "importance_label", None),
        "time": getattr(item, "available_for_decision_at", None),
    }


def _event_news_row(item: object) -> dict[str, Any]:
    headline = _first_text(getattr(item, "headline", None), getattr(item, "summary", None))
    return {
        "news_id": getattr(item, "event_news_item_id", None),
        "ticker": getattr(item, "ticker", None),
        "category": event_type_label(getattr(item, "event_type", None)),
        "title": headline,
        "headline": headline,
        "summary": getattr(item, "summary", None),
        "source": getattr(item, "provider", None),
        "sentiment": getattr(item, "sentiment", None) or getattr(item, "direction", None),
        "importance": getattr(item, "importance", None),
        "time": getattr(item, "available_for_decision_at", None),
    }


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _normalized_story_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _default_visible_event(event: object) -> bool:
    metadata_json = dict(getattr(event, "metadata_json", {}) or {})
    return metadata_json.get("default_visibility", "show") != "hide"


def _is_upcoming_event(event: object, as_of: datetime | None) -> bool:
    """Hide events whose scheduled time is already in the past.

    The risk surface is forward-looking: a CPI print or earnings date that has
    already happened should not be presented as a pending catalyst. We compare
    against ``as_of`` (the decision-snapshot time) when available, otherwise the
    event date alone cannot be classified and we keep it visible.
    """
    if as_of is None:
        return True
    event_time = getattr(event, "event_time", None)
    if not isinstance(event_time, (datetime, date)):
        return True
    cutoff: date | datetime = as_of
    if isinstance(event_time, datetime):
        reference = as_of
        if event_time.tzinfo is None and as_of.tzinfo is not None:
            reference = as_of.replace(tzinfo=None)
        elif event_time.tzinfo is not None and as_of.tzinfo is None:
            reference = as_of.replace(tzinfo=timezone.utc)
        return event_time >= reference
    if isinstance(cutoff, datetime):
        cutoff = cutoff.date()
    return event_time >= cutoff


def _is_in_visible_event_window(event: object, as_of: datetime | None) -> bool:
    if as_of is None:
        return True
    event_type = str(getattr(event, "event_type", "") or "").strip().lower()
    if "earn" not in event_type:
        return True
    event_date = _display_date(getattr(event, "event_time", None))
    reference_date = _display_date(as_of)
    if event_date is None or reference_date is None:
        return True
    return event_date <= reference_date + timedelta(days=7)


def _is_recent_news(item: object, as_of: datetime | None) -> bool:
    if as_of is None:
        return True
    news_date = _display_date(
        getattr(item, "available_for_decision_at", None)
        or getattr(item, "published_at", None)
        or getattr(item, "event_time", None)
    )
    reference_date = _display_date(as_of)
    if news_date is None or reference_date is None:
        return False
    return reference_date - timedelta(days=3) <= news_date <= reference_date


def _display_date(value: object) -> date | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone().date()
    if isinstance(value, date):
        return value
    return None


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


def _format_event_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%b %d, %Y")
    if isinstance(value, date):
        return value.strftime("%b %d, %Y")
    return None


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
    normalized = _normalized_source_key(source_key)
    if normalized == "macro":
        return "Macro regime"
    if normalized == "own_event":
        return _portfolio_event_risk_source_row(event_assessments=(), exposures=exposures)["label"]
    if normalized in {"sector_event_cluster", "event_cluster"}:
        first = exposures[0] if exposures else {}
        factor_name = str(first.get("factor_name") or "Portfolio").strip()
        return f"{factor_name} concentration"
    return _humanize_identifier(normalized)


def _risk_source_summary(source_key: str) -> str:
    normalized = _normalized_source_key(source_key)
    if normalized == "macro":
        return "Macro regime is constraining risk appetite."
    if normalized == "own_event":
        return "Portfolio event windows are driving tactical caution."
    if normalized in {"sector_event_cluster", "event_cluster"}:
        return "Clustered event risk is driving hedge posture."
    return _humanize_identifier(normalized)


def _normalized_source_key(value: object) -> str:
    return str(value or "").strip().lower()


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


def _format_compact_number(value: float | None) -> str:
    if value is None:
        return "—"
    text = f"{value:,.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


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
