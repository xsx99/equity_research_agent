from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.trading.portfolio.pnl import (
    PortfolioPnlValidationError,
    StockFillEvent,
    replay_stock_fills,
)


START = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
END = START + timedelta(days=30)


def _fill(
    execution_id: str,
    ticker: str,
    action: str,
    quantity: float,
    fill_price: float,
    *,
    executed_at: datetime | None = None,
) -> StockFillEvent:
    return StockFillEvent(
        execution_id=execution_id,
        ticker=ticker,
        executed_at=executed_at or START + timedelta(days=1),
        action=action,
        quantity=quantity,
        fill_price=fill_price,
    )


def test_replay_stock_fills_realizes_profitable_round_trip() -> None:
    replay = replay_stock_fills(
        (
            _fill("buy-1", "aapl", "enter_long", 10, 100),
            _fill("sell-1", "AAPL", "exit", 10, 125, executed_at=START + timedelta(days=2)),
        ),
        started_at=START,
        through=END,
    )

    assert replay.realized_pnl == pytest.approx(250.0)
    assert replay.open_cost_basis == {}
    assert replay.fill_count == 2


def test_replay_stock_fills_realizes_losing_round_trip() -> None:
    replay = replay_stock_fills(
        (
            _fill("buy-1", "AAPL", "enter_long", 4, 100),
            _fill("sell-1", "AAPL", "reduce", 4, 90, executed_at=START + timedelta(days=2)),
        ),
        started_at=START,
        through=END,
    )

    assert replay.realized_pnl == pytest.approx(-40.0)
    assert replay.open_cost_basis == {}


def test_replay_stock_fills_uses_weighted_average_cost_for_partial_reduction() -> None:
    replay = replay_stock_fills(
        (
            _fill("buy-1", "AAPL", "enter_long", 10, 100),
            _fill("buy-2", "AAPL", "enter_long", 10, 120, executed_at=START + timedelta(days=2)),
            _fill("sell-1", "AAPL", "reduce", 5, 130, executed_at=START + timedelta(days=3)),
        ),
        started_at=START,
        through=END,
    )

    assert replay.realized_pnl == pytest.approx(100.0)
    assert replay.open_cost_basis["AAPL"].quantity == pytest.approx(15.0)
    assert replay.open_cost_basis["AAPL"].average_cost == pytest.approx(110.0)


def test_replay_stock_fills_orders_equal_timestamps_by_execution_id() -> None:
    at = START + timedelta(days=1)

    replay = replay_stock_fills(
        (
            _fill("02-sell", "AAPL", "exit", 1, 110, executed_at=at),
            _fill("01-buy", "AAPL", "enter_long", 1, 100, executed_at=at),
        ),
        started_at=START,
        through=END,
    )

    assert replay.realized_pnl == pytest.approx(10.0)
    assert replay.open_cost_basis == {}


def test_replay_stock_fills_excludes_events_outside_requested_window() -> None:
    replay = replay_stock_fills(
        (
            _fill("before", "AAPL", "enter_long", 1, 50, executed_at=START - timedelta(seconds=1)),
            _fill("inside", "MSFT", "enter_long", 2, 100),
            _fill("after", "MSFT", "exit", 2, 150, executed_at=END + timedelta(seconds=1)),
        ),
        started_at=START,
        through=END,
    )

    assert replay.realized_pnl == 0.0
    assert set(replay.open_cost_basis) == {"MSFT"}
    assert replay.open_cost_basis["MSFT"].quantity == pytest.approx(2.0)
    assert replay.open_cost_basis["MSFT"].average_cost == pytest.approx(100.0)
    assert replay.fill_count == 1


@pytest.mark.parametrize(
    ("event", "message"),
    (
        (_fill("bad-qty", "AAPL", "enter_long", 0, 100), "quantity"),
        (_fill("bad-price", "AAPL", "enter_long", 1, -1), "fill_price"),
        (_fill("bad-action", "AAPL", "hold", 1, 100), "action"),
    ),
)
def test_replay_stock_fills_rejects_invalid_events(event: StockFillEvent, message: str) -> None:
    with pytest.raises(PortfolioPnlValidationError, match=message):
        replay_stock_fills((event,), started_at=START, through=END)


def test_replay_stock_fills_rejects_duplicate_execution_ids() -> None:
    with pytest.raises(PortfolioPnlValidationError, match="duplicate_execution_id"):
        replay_stock_fills(
            (
                _fill("duplicate", "AAPL", "enter_long", 1, 100),
                _fill("duplicate", "MSFT", "enter_long", 1, 200),
            ),
            started_at=START,
            through=END,
        )


def test_replay_stock_fills_rejects_oversell() -> None:
    with pytest.raises(PortfolioPnlValidationError, match="oversell"):
        replay_stock_fills(
            (
                _fill("buy-1", "AAPL", "enter_long", 1, 100),
                _fill("sell-1", "AAPL", "exit", 2, 110, executed_at=START + timedelta(days=2)),
            ),
            started_at=START,
            through=END,
        )
