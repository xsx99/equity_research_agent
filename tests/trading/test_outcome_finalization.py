from datetime import datetime, timezone

from src.trading.outcomes.finalization import resolve_finalization


def test_selected_trade_finalizes_at_complete_close_not_partial_reduction():
    horizon = datetime(2026, 7, 30, 20, tzinfo=timezone.utc)
    close = datetime(2026, 7, 10, 19, 45, tzinfo=timezone.utc)

    partial = resolve_finalization(
        trade_identity="tactical_stock_trade",
        has_complete_close=False,
        complete_close_at=close,
        horizon_end_at=horizon,
    )
    complete = resolve_finalization(
        trade_identity="tactical_stock_trade",
        has_complete_close=True,
        complete_close_at=close,
        horizon_end_at=horizon,
    )

    assert partial.horizon_end_at == horizon
    assert partial.reason == "horizon_expired"
    assert complete.horizon_end_at == close
    assert complete.reason == "trade_closed"


def test_watch_and_rejected_paths_remain_horizon_finalized_even_if_ticker_closed_elsewhere():
    horizon = datetime(2026, 7, 30, 20, tzinfo=timezone.utc)

    outcome = resolve_finalization(
        trade_identity="watch_only",
        has_complete_close=True,
        complete_close_at=datetime(2026, 7, 10, 19, 45, tzinfo=timezone.utc),
        horizon_end_at=horizon,
    )

    assert outcome.horizon_end_at == horizon
    assert outcome.reason == "horizon_expired"
