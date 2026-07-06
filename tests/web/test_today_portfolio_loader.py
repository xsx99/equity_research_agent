from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.web.routers.loaders.portfolio import _load_positions


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *args, **kwargs):
        return _FakeQuery(self._rows)


def test_load_positions_exposes_enriched_stock_position_fields():
    opened_at = datetime(2026, 6, 10, 15, 30, tzinfo=timezone.utc)
    row = SimpleNamespace(
        ticker="AAPL",
        trade_identity="tactical_stock_trade",
        strategy_id="relative_strength_rotation_v1",
        quantity=10,
        average_cost=100,
        market_price=125,
        market_value=1250,
        unrealized_pnl=250,
        opened_at=opened_at,
        updated_at=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
    )

    positions = _load_positions(
        _FakeSession([row]),
        as_of=datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc),
    )

    assert len(positions) == 1
    position = positions[0]
    assert position["entry_price"] == 100
    assert position["avg_cost"] == 100
    assert position["avg_fill_price"] == 100
    assert position["current_price"] == 125
    assert position["held_days"] == 5
    assert position["total_pnl_pct"] == pytest.approx(0.25)
    assert position["sleeve"] == "Tactical Stock Trade"
    assert position["filled_qty"] == 10


def test_load_positions_computes_unrealized_pnl_when_row_has_no_column():
    row = SimpleNamespace(
        ticker="NOK",
        trade_identity="tactical_stock_trade",
        strategy_id="catalyst_breakout_v1",
        quantity=100,
        average_cost=12.50,
        market_price=12.75,
        market_value=1275,
        opened_at=datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
    )

    positions = _load_positions(
        _FakeSession([row]),
        as_of=datetime(2026, 7, 6, 16, 0, tzinfo=timezone.utc),
    )

    position = positions[0]
    assert position["unrealized_pnl"] == pytest.approx(25.0)
    assert position["total_pnl_pct"] == pytest.approx(0.02)
