from __future__ import annotations

import uuid

from src.db.models.trading import UniverseFilterConfig
from src.trading.runtime.support import seed_default_universe_filter_config


class _FakeFilterCondition:
    def __init__(self, attr_name: str, expected: object) -> None:
        self.attr_name = attr_name
        self.expected = expected

    def matches(self, row: object) -> bool:
        return getattr(row, self.attr_name) is self.expected


class _FakeActiveField:
    def is_(self, expected: object) -> _FakeFilterCondition:
        return _FakeFilterCondition("is_active", expected)


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter(self, condition: _FakeFilterCondition) -> "_FakeQuery":
        return _FakeQuery([row for row in self._rows if condition.matches(row)])

    def first(self) -> object | None:
        if not self._rows:
            return None
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}
        self.flush_calls = 0

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        rows = list(self.rows_by_type.get(model, []))
        return _FakeQuery(rows)

    def flush(self) -> None:
        self.flush_calls += 1


def test_seed_default_universe_filter_config_inserts_one_active_row_when_missing(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(UniverseFilterConfig, "is_active", _FakeActiveField())

    seed_default_universe_filter_config(session)

    rows = session.rows_by_type[UniverseFilterConfig]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, UniverseFilterConfig)
    assert row.profile_name == "default"
    assert row.version == 1
    assert row.is_active is True
    assert row.min_price == 5
    assert row.min_avg_dollar_volume == 10_000_000
    assert row.manual_include_json == []
    assert row.manual_exclude_json == []
    assert session.flush_calls == 1


def test_seed_default_universe_filter_config_is_idempotent(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(UniverseFilterConfig, "is_active", _FakeActiveField())
    existing = UniverseFilterConfig(
        universe_filter_config_id=uuid.uuid4(),
        profile_name="custom",
        version=7,
        is_active=True,
        min_price=12,
        min_avg_dollar_volume=50_000_000,
        included_sectors_json=[],
        excluded_sectors_json=[],
        included_industries_json=[],
        excluded_industries_json=[],
        exchanges_json=[],
        asset_types_json=[],
        manual_include_json=["NVDA"],
        manual_exclude_json=[],
    )
    session.add(existing)

    seed_default_universe_filter_config(session)

    rows = session.rows_by_type[UniverseFilterConfig]
    assert rows == [existing]
    assert session.flush_calls == 0
