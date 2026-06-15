from __future__ import annotations

from datetime import datetime, timezone

from src.trading.portfolio.state import (
    OptionPosition,
    PortfolioSnapshot,
    StockPosition,
    build_portfolio_context,
    build_portfolio_snapshot_from_account,
    build_positions_from_broker,
)
from src.trading.risk import PortfolioContext


def test_build_portfolio_snapshot_from_alpaca_account():
    snapshot = build_portfolio_snapshot_from_account(
        {
            "cash": "999997.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999995.46",
            "long_market_value": "2.27",
            "initial_margin": "1.14",
            "maintenance_margin": "0.68",
            "last_equity": "1000000.00",
        },
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
    )

    assert snapshot == PortfolioSnapshot(
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        cash_balance=999997.73,
        account_equity=1000000.12,
        net_liquidation_value=1000000.12,
        buying_power=1999995.46,
        excess_liquidity=999999.44,
        stock_market_value=2.27,
        option_market_value=0.0,
        stock_margin_requirement=1.14,
        option_margin_requirement=0.0,
        total_margin_requirement=1.14,
        initial_margin_requirement=1.14,
        maintenance_margin_requirement=0.68,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_reported",
        day_pnl=0.12,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json={},
    )


def test_build_positions_from_broker_uses_broker_qty_price_and_local_trade_metadata():
    positions = build_positions_from_broker(
        broker_positions=[
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ],
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        local_position_metadata={"AAPL": {"strategy_id": "relative_strength_rotation_v1", "trade_identity": "tactical_stock_trade"}},
    )

    assert positions == (
        StockPosition(
            ticker="AAPL",
            quantity=0.01,
            average_cost=227.15,
            market_price=227.27,
            market_value=2.27,
            trade_identity="tactical_stock_trade",
            strategy_id="relative_strength_rotation_v1",
            opened_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
            direction="long",
        ),
    )


def test_build_positions_from_broker_filters_option_contract_rows():
    positions = build_positions_from_broker(
        broker_positions=[
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
                "asset_class": "us_equity",
            },
            {
                "symbol": "AAPL260717C00200000",
                "qty": "1",
                "avg_entry_price": "2.20",
                "current_price": "2.35",
                "market_value": "235.0",
                "side": "long",
                "asset_class": "option",
            },
        ],
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        local_position_metadata={"AAPL": {"strategy_id": "relative_strength_rotation_v1", "trade_identity": "tactical_stock_trade"}},
    )

    assert [position.ticker for position in positions] == ["AAPL"]


def test_build_portfolio_context_uses_broker_snapshot_and_positions():
    snapshot = build_portfolio_snapshot_from_account(
        {
            "cash": "999997.73",
            "equity": "1000000.12",
            "portfolio_value": "1000000.12",
            "buying_power": "1999995.46",
            "long_market_value": "2.27",
            "initial_margin": "1.14",
            "maintenance_margin": "0.68",
            "last_equity": "1000000.00",
        },
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
    )
    positions = build_positions_from_broker(
        broker_positions=[
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ],
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        local_position_metadata={"AAPL": {"strategy_id": "relative_strength_rotation_v1", "trade_identity": "tactical_stock_trade"}},
    )

    context = build_portfolio_context(
        snapshot=snapshot,
        positions=positions,
        approved_core_tickers=("MSFT",),
    )

    assert isinstance(context, PortfolioContext)
    assert context.account_equity == 1000000.12
    assert context.cash_balance == 999997.73
    assert context.buying_power == 1999995.46
    assert context.total_margin_requirement == 1.14
    assert context.positions[0].ticker == "AAPL"
    assert context.positions[0].direction == "long"


def test_build_portfolio_context_carries_option_overlay_buying_power_and_assignment_exposure():
    snapshot = PortfolioSnapshot(
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        cash_balance=999997.73,
        account_equity=1000000.12,
        net_liquidation_value=1000000.12,
        buying_power=1999495.46,
        excess_liquidity=999499.44,
        stock_market_value=2.27,
        option_market_value=500.0,
        stock_margin_requirement=1.14,
        option_margin_requirement=500.0,
        total_margin_requirement=501.14,
        initial_margin_requirement=501.14,
        maintenance_margin_requirement=500.68,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_plus_local_option_overlay",
        day_pnl=0.12,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata_json={
            "stock_margin_requirement_source": "broker_reported",
            "option_overlay_source": "local_simulation",
        },
    )
    positions = build_positions_from_broker(
        broker_positions=[
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "227.15",
                "current_price": "227.27",
                "market_value": "2.27",
                "side": "long",
            }
        ],
        as_of=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
        local_position_metadata={"AAPL": {"strategy_id": "relative_strength_rotation_v1", "trade_identity": "tactical_stock_trade"}},
    )

    context = build_portfolio_context(
        snapshot=snapshot,
        positions=positions,
        option_positions=(
            OptionPosition(
                ticker="NVDA",
                quantity=1,
                market_value=500.0,
                trade_identity="tactical_option_trade",
                strategy_id="earnings_drift_v1",
                option_strategy_type="put_credit_spread",
                opened_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
                updated_at=datetime(2026, 6, 2, 16, 31, tzinfo=timezone.utc),
                expiry=datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc).date(),
                max_loss=500.0,
                margin_requirement=500.0,
                buying_power_effect=500.0,
                assignment_notional=11_000.0,
            ),
        ),
        approved_core_tickers=("MSFT",),
    )

    assert context.option_margin_requirement == 500.0
    assert context.total_margin_requirement == 501.14
    assert context.positions[1].ticker == "NVDA"
    assert context.positions[1].market_value == 500.0
    assert context.positions[1].assignment_notional == 11_000.0
