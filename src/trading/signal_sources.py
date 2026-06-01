"""Point-in-time source rows and in-memory source adapters for PR02."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class SourceRecord:
    """Normalized point-in-time source row consumed by signal builders."""

    ticker: str
    source_family: str
    source: str
    source_table: str
    source_record_id: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())

    @property
    def source_ref(self) -> dict[str, str]:
        return {
            "source": self.source,
            "source_table": self.source_table,
            "source_record_id": self.source_record_id,
        }


class InMemorySignalSourceRepository:
    """Fixture-backed signal source repository."""

    def __init__(self, records: Iterable[SourceRecord] = ()) -> None:
        self._records: list[SourceRecord] = list(records)

    def add(self, *records: SourceRecord) -> None:
        self._records.extend(records)

    def records_for_ticker(self, ticker: str) -> tuple[SourceRecord, ...]:
        symbol = ticker.strip().upper()
        return tuple(record for record in self._records if record.ticker == symbol)

    def available_records(
        self,
        ticker: str,
        decision_time: datetime,
        *,
        source_family: str | None = None,
    ) -> tuple[SourceRecord, ...]:
        records = [
            record
            for record in self.records_for_ticker(ticker)
            if record.available_for_decision_at <= decision_time
            and (source_family is None or record.source_family == source_family)
        ]
        return tuple(sorted(records, key=lambda record: record.available_for_decision_at))

    def latest_available_by_family(
        self,
        ticker: str,
        source_family: str,
        decision_time: datetime,
    ) -> tuple[SourceRecord, ...]:
        records = self.available_records(ticker, decision_time, source_family=source_family)
        if not records:
            return ()
        latest = max(record.available_for_decision_at for record in records)
        return tuple(record for record in records if record.available_for_decision_at == latest)
