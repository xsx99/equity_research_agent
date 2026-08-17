from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.trading.portfolio.pnl import (
    AVERAGE_COST_TOLERANCE,
    CURRENCY_TOLERANCE,
    PortfolioPnlValidationError,
    PortfolioPnlPoint,
    QUANTITY_TOLERANCE,
    RECONCILIATION_RESIDUAL_TOLERANCE,
    StockFillEvent,
    enrich_snapshot_with_stock_pnl,
    replay_stock_fills,
    select_active_lifecycle_boundary,
)
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition


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


def test_select_active_lifecycle_boundary_uses_latest_clean_reset() -> None:
    first_reset = START
    second_reset = START + timedelta(days=10)
    points = (
        _point(first_reset, equity=1_000_000, stock_market_value=0),
        _point(first_reset + timedelta(days=2), equity=999_900, stock_market_value=100),
        _point(second_reset, equity=1_000_000, stock_market_value=0),
        _point(second_reset + timedelta(days=2), equity=999_800, stock_market_value=200),
    )

    boundary = select_active_lifecycle_boundary(
        points,
        (
            _fill("old-buy", "AAPL", "enter_long", 1, 100, executed_at=first_reset + timedelta(days=1)),
            _fill("new-buy", "MSFT", "enter_long", 1, 200, executed_at=second_reset + timedelta(days=1)),
        ),
        starting_equity=1_000_000,
    )

    assert boundary == second_reset


def test_select_active_lifecycle_boundary_skips_reset_at_fill_timestamp() -> None:
    ambiguous_reset = START + timedelta(days=10)

    boundary = select_active_lifecycle_boundary(
        (
            _point(START, equity=1_000_000, stock_market_value=0),
            _point(ambiguous_reset, equity=1_000_000, stock_market_value=0),
        ),
        (
            _fill("same-time", "AAPL", "enter_long", 1, 100, executed_at=ambiguous_reset),
        ),
        starting_equity=1_000_000,
    )

    assert boundary == START


def test_select_active_lifecycle_boundary_requires_clean_reset() -> None:
    with pytest.raises(PortfolioPnlValidationError, match="missing_clean_reset"):
        select_active_lifecycle_boundary(
            (_point(START, equity=999_999, stock_market_value=0),),
            (),
            starting_equity=1_000_000,
        )


def test_enrich_snapshot_with_stock_pnl_uses_replay_cost_and_keeps_residual_separate() -> None:
    snapshot_time = START + timedelta(days=20)
    snapshot = _snapshot(
        as_of=snapshot_time,
        account_equity=988_482.96,
        stock_market_value=64_813.47,
        metadata_json={"existing": "value"},
    )
    fills = (
        _fill("old-buy", "OLD", "enter_long", 1, 10, executed_at=START - timedelta(days=2)),
        _fill("closed-buy", "LOSS", "enter_long", 1, 12_000, executed_at=START + timedelta(days=1)),
        _fill("closed-sell", "LOSS", "exit", 1, 934.51, executed_at=START + timedelta(days=2)),
        _fill("open-buy", "OPEN", "enter_long", 1, 65_258.572198, executed_at=START + timedelta(days=3)),
    )
    positions = (_position("OPEN", quantity=1, average_cost=65_258.572198, market_value=64_813.47),)

    enriched = enrich_snapshot_with_stock_pnl(
        snapshot,
        positions=positions,
        points=(
            _point(START - timedelta(days=10), equity=1_000_000, stock_market_value=0),
            _point(START, equity=1_000_000, stock_market_value=0),
            _point(snapshot_time, equity=988_482.96, stock_market_value=64_813.47),
        ),
        fills=fills,
        starting_equity=1_000_000,
    )

    assert enriched is not snapshot
    assert enriched.realized_pnl == pytest.approx(-11_065.49)
    assert enriched.unrealized_pnl == pytest.approx(-445.102198)
    assert enriched.metadata_json["pnl_reconciliation_residual"] == pytest.approx(-6.447802)
    assert enriched.metadata_json["pnl_reconciled"] is False
    assert enriched.metadata_json["pnl_tracking_started_at"] == START.isoformat()
    assert enriched.metadata_json["pnl_fill_count"] == 3
    assert enriched.metadata_json["pnl_excluded_pre_boundary_fill_count"] == 1
    assert enriched.metadata_json["pnl_excluded_pre_boundary_snapshot_count"] == 1
    assert enriched.metadata_json["pnl_calculation_method"] == "weighted_average_stock_fills_v1"
    assert enriched.metadata_json["pnl_starting_equity"] == 1_000_000
    assert enriched.metadata_json["pnl_tolerances"] == {
        "quantity": QUANTITY_TOLERANCE,
        "currency": CURRENCY_TOLERANCE,
        "average_cost": AVERAGE_COST_TOLERANCE,
        "reconciliation_residual": RECONCILIATION_RESIDUAL_TOLERANCE,
    }
    assert enriched.metadata_json["pnl_cost_basis_diagnostics"] == []
    assert enriched.metadata_json["existing"] == "value"
    assert snapshot.realized_pnl == 0.0


def test_enrich_snapshot_with_stock_pnl_marks_residual_within_tolerance_reconciled() -> None:
    snapshot_time = START + timedelta(days=2)
    enriched = enrich_snapshot_with_stock_pnl(
        _snapshot(as_of=snapshot_time, account_equity=1_000_009.995, stock_market_value=110),
        positions=(_position("AAPL", quantity=1, average_cost=100, market_value=110),),
        points=(
            _point(START, equity=1_000_000, stock_market_value=0),
            _point(snapshot_time, equity=1_000_009.995, stock_market_value=110),
        ),
        fills=(_fill("buy", "AAPL", "enter_long", 1, 100),),
        starting_equity=1_000_000,
    )

    assert enriched.unrealized_pnl == pytest.approx(10.0)
    assert enriched.metadata_json["pnl_reconciliation_residual"] == pytest.approx(-0.005)
    assert enriched.metadata_json["pnl_reconciled"] is True


def test_enrich_snapshot_with_stock_pnl_rejects_quantity_mismatch() -> None:
    snapshot_time = START + timedelta(days=2)
    with pytest.raises(PortfolioPnlValidationError, match="quantity_mismatch"):
        enrich_snapshot_with_stock_pnl(
            _snapshot(as_of=snapshot_time, account_equity=1_000_010, stock_market_value=110),
            positions=(
                _position(
                    "AAPL",
                    quantity=1 + (QUANTITY_TOLERANCE * 2),
                    average_cost=100,
                    market_value=110,
                ),
            ),
            points=(
                _point(START, equity=1_000_000, stock_market_value=0),
                _point(snapshot_time, equity=1_000_010, stock_market_value=110),
            ),
            fills=(_fill("buy", "AAPL", "enter_long", 1, 100),),
            starting_equity=1_000_000,
        )


def test_enrich_snapshot_with_stock_pnl_records_small_cost_mismatch() -> None:
    snapshot_time = START + timedelta(days=2)
    broker_cost = 100 + AVERAGE_COST_TOLERANCE
    enriched = enrich_snapshot_with_stock_pnl(
        _snapshot(as_of=snapshot_time, account_equity=1_000_010, stock_market_value=110),
        positions=(_position("AAPL", quantity=1, average_cost=broker_cost, market_value=110),),
        points=(
            _point(START, equity=1_000_000, stock_market_value=0),
            _point(snapshot_time, equity=1_000_010, stock_market_value=110),
        ),
        fills=(_fill("buy", "AAPL", "enter_long", 1, 100),),
        starting_equity=1_000_000,
    )

    assert enriched.metadata_json["pnl_cost_basis_diagnostics"] == [
        {
            "ticker": "AAPL",
            "broker_average_cost": pytest.approx(broker_cost),
            "replayed_average_cost": pytest.approx(100.0),
            "difference": pytest.approx(AVERAGE_COST_TOLERANCE),
        }
    ]


def test_enrich_snapshot_with_stock_pnl_rejects_material_cost_mismatch() -> None:
    snapshot_time = START + timedelta(days=2)
    with pytest.raises(PortfolioPnlValidationError, match="average_cost_mismatch"):
        enrich_snapshot_with_stock_pnl(
            _snapshot(as_of=snapshot_time, account_equity=1_000_010, stock_market_value=110),
            positions=(
                _position(
                    "AAPL",
                    quantity=1,
                    average_cost=100 + AVERAGE_COST_TOLERANCE + 0.001,
                    market_value=110,
                ),
            ),
            points=(
                _point(START, equity=1_000_000, stock_market_value=0),
                _point(snapshot_time, equity=1_000_010, stock_market_value=110),
            ),
            fills=(_fill("buy", "AAPL", "enter_long", 1, 100),),
            starting_equity=1_000_000,
        )


def _point(
    snapshot_time: datetime,
    *,
    equity: float,
    stock_market_value: float,
    option_market_value: float = 0.0,
) -> PortfolioPnlPoint:
    return PortfolioPnlPoint(
        snapshot_time=snapshot_time,
        account_equity=equity,
        stock_market_value=stock_market_value,
        option_market_value=option_market_value,
    )


def _position(
    ticker: str,
    *,
    quantity: float,
    average_cost: float,
    market_value: float,
) -> StockPosition:
    return StockPosition(
        ticker=ticker,
        quantity=quantity,
        average_cost=average_cost,
        market_price=market_value / quantity,
        market_value=market_value,
        trade_identity="tactical_stock_trade",
        strategy_id="test_strategy",
        opened_at=START,
        updated_at=END,
    )


def _snapshot(
    *,
    as_of: datetime,
    account_equity: float,
    stock_market_value: float,
    metadata_json: dict[str, object] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=as_of,
        cash_balance=account_equity - stock_market_value,
        account_equity=account_equity,
        net_liquidation_value=account_equity,
        buying_power=account_equity * 2,
        excess_liquidity=account_equity,
        stock_market_value=stock_market_value,
        option_market_value=0.0,
        stock_margin_requirement=0.0,
        option_margin_requirement=0.0,
        total_margin_requirement=0.0,
        initial_margin_requirement=0.0,
        maintenance_margin_requirement=0.0,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_reported",
        day_pnl=0.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json=metadata_json or {},
    )
