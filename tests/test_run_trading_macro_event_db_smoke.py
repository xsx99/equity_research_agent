from __future__ import annotations

from datetime import datetime, timezone

from scripts.run_trading_macro_event_db_smoke import run_smoke


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)

    def filter_by(self, **kwargs):
        return _FakeQuery(
            [
                row
                for row in self._rows
                if all(getattr(row, key) == value for key, value in kwargs.items())
            ]
        )

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        return _FakeQuery(self.rows_by_type.get(model, []))

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None


def test_run_trading_macro_event_db_smoke_round_trips_canonical_rows():
    now = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)

    result = run_smoke(
        as_of=now,
        session_factory=_FakeSession,
        init_schema=lambda: None,
    )

    assert result["status"] == "passed"
    assert result["checks"] == {
        "macro_snapshot_reloaded": True,
        "calendar_events_reloaded": True,
        "event_assessments_reloaded": True,
        "today_payload_uses_canonical_regime": True,
        "today_payload_sees_event_risk": True,
    }
    assert len(result["persisted"]["calendar_event_ids"]) == 2
    assert len(result["persisted"]["portfolio_event_risk_assessment_ids"]) == 2
    assert result["persisted"]["risk_factor_exposure_count"] == 2
    assert result["reloaded"]["risk_macro_regime"] == "risk_off"
    assert result["reloaded"]["risk_macro_event_risk_level"] == "High"
    assert result["reloaded"]["risk_macro_top_source"] == "Own event window"
