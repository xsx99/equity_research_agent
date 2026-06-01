from datetime import datetime, timezone

from src.trading.signal_sources import InMemorySignalSourceRepository, SourceRecord


def test_signal_source_repository_returns_latest_decision_available_rows_by_family():
    decision_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    old_time = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    new_time = datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc)
    future_time = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    repo = InMemorySignalSourceRepository()
    repo.add(
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "old", old_time, old_time, old_time, old_time, {"score": 1}),
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "new", new_time, new_time, new_time, new_time, {"score": 2}),
        SourceRecord("AAPL", "fundamental", "fixture", "fundamental_snapshots", "future", future_time, future_time, future_time, future_time, {"score": 99}),
    )

    rows = repo.latest_available_by_family("AAPL", "fundamental", decision_time)

    assert [row.source_record_id for row in rows] == ["new"]
