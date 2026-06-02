"""Point-in-time source filtering helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.trading.signals.sources import SourceRecord


@dataclass(frozen=True)
class PointInTimeAudit:
    """Result of filtering source rows by decision-time availability."""

    records: tuple[SourceRecord, ...]
    excluded_future_source_count: int
    max_input_available_for_decision_at: datetime | None
    source_record_refs: tuple[dict[str, str], ...]
    source_available_times: dict[str, str]
    point_in_time_passed: bool


def filter_point_in_time_records(
    records: list[SourceRecord] | tuple[SourceRecord, ...],
    decision_time: datetime,
) -> PointInTimeAudit:
    """Return only records available at decision time plus replay audit metadata."""
    available = tuple(
        sorted(
            (record for record in records if record.available_for_decision_at <= decision_time),
            key=lambda record: (record.available_for_decision_at, record.source_record_id),
        )
    )
    excluded_count = len(records) - len(available)
    max_available = (
        max((record.available_for_decision_at for record in available), default=None)
    )
    return PointInTimeAudit(
        records=available,
        excluded_future_source_count=excluded_count,
        max_input_available_for_decision_at=max_available,
        source_record_refs=tuple(record.source_ref for record in available),
        source_available_times={
            record.source_record_id: record.available_for_decision_at.isoformat()
            for record in available
        },
        point_in_time_passed=all(record.available_for_decision_at <= decision_time for record in available),
    )
