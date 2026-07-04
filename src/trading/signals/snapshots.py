"""Deterministic point-in-time signal snapshot builders."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from src.trading.signals.event_news import build_event_news_signals
from src.trading.signals.fundamental import build_fundamental_signals
from src.trading.signals.insider import build_insider_signals
from src.trading.signals.point_in_time import filter_point_in_time_records
from src.trading.signals.social_macro import build_social_macro_signals
from src.trading.signals.sources import SourceRecord
from src.trading.signals.technical import build_technical_signals, compute_relative_strength


@dataclass(frozen=True)
class SignalSnapshotResult:
    """In-memory pre-open signal snapshot artifact."""

    signal_snapshot_id: str
    ticker: str
    snapshot_type: str
    decision_time: datetime
    available_for_decision_at: datetime
    max_input_available_for_decision_at: datetime | None
    signal_json: dict[str, dict[str, Any]]
    source_freshness_json: dict[str, str]
    missing_signals_json: list[str]
    stale_signals_json: list[str]
    source_record_refs_json: list[dict[str, str]]
    source_available_times_json: dict[str, str]
    excluded_future_source_count: int
    point_in_time_passed: bool
    selection_source: str = "scanner"
    manual_request_id: str | None = None


def build_signal_snapshot(
    *,
    ticker: str,
    decision_time: datetime,
    source_records: Iterable[SourceRecord],
    snapshot_type: str,
    selection_source: str = "scanner",
    manual_request_id: str | None = None,
    insider_data_covered: bool = False,
) -> SignalSnapshotResult:
    """Build a replayable PR02 signal snapshot from PIT-filtered source rows."""
    audit = filter_point_in_time_records(tuple(source_records), decision_time)
    records_by_family = _group_records(audit.records)
    technical = build_technical_signals(records_by_family.get("technical", ()))
    fundamental = build_fundamental_signals(records_by_family.get("fundamental", ()))
    events_news = build_event_news_signals(
        records_by_family.get("events_news", ()),
        decision_time=decision_time,
    )
    insider = build_insider_signals(
        records_by_family.get("insider", ()),
        decision_time=decision_time,
        data_covered=insider_data_covered,
    )
    social_macro = build_social_macro_signals(
        records_by_family.get("social_macro", ()),
        decision_time=decision_time,
    )
    missing = [
        *_missing_with_prefix("technical", technical.missing),
        *_missing_with_prefix("fundamental", fundamental.missing),
        *_missing_with_prefix("events_news", events_news.missing),
        *_missing_with_prefix("insider", insider.missing),
        *_missing_with_prefix("social_macro", social_macro.missing),
        "option_chain_availability",
        "full_transcript_interpretation",
        "macro_sector_readthrough",
    ]
    source_freshness = {
        family: ("fresh" if family in records_by_family else "missing")
        for family in ("technical", "fundamental", "events_news", "insider", "social_macro")
    }
    if insider_data_covered:
        source_freshness["insider"] = "fresh"
    available_for_decision_at = audit.max_input_available_for_decision_at or decision_time
    return SignalSnapshotResult(
        signal_snapshot_id=str(uuid.uuid4()),
        ticker=ticker.strip().upper(),
        snapshot_type=snapshot_type,
        decision_time=decision_time,
        available_for_decision_at=available_for_decision_at,
        max_input_available_for_decision_at=audit.max_input_available_for_decision_at,
        signal_json={
            "technical": technical.values,
            "fundamental": fundamental.values,
            "events_news": events_news.values,
            "insider": insider.values,
            "social_macro": social_macro.values,
        },
        source_freshness_json=source_freshness,
        missing_signals_json=missing,
        stale_signals_json=[],
        source_record_refs_json=list(audit.source_record_refs),
        source_available_times_json=audit.source_available_times,
        excluded_future_source_count=audit.excluded_future_source_count,
        point_in_time_passed=audit.point_in_time_passed,
        selection_source=selection_source,
        manual_request_id=manual_request_id,
    )


def _group_records(records: tuple[SourceRecord, ...]) -> dict[str, tuple[SourceRecord, ...]]:
    grouped: dict[str, list[SourceRecord]] = {}
    for record in records:
        grouped.setdefault(record.source_family, []).append(record)
    return {family: tuple(items) for family, items in grouped.items()}


def _missing_with_prefix(prefix: str, fields: Iterable[str]) -> list[str]:
    return [f"{prefix}.{field}" for field in fields]
