from datetime import date, datetime, timezone

import pytest

from src.trading.macro import MacroReadthroughEventRecord, MacroSnapshotRecord


def test_macro_snapshot_record_preserves_point_in_time_macro_contract():
    snapshot_time = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    record = MacroSnapshotRecord(
        macro_snapshot_id="macro-1",
        snapshot_time=snapshot_time,
        trade_date=date(2026, 6, 16),
        regime="risk_off",
        risk_budget_multiplier=0.6,
        volatility_state="elevated",
        rates_state="restrictive",
        liquidity_state="tight",
        blocked_strategy_tags=("gap_and_go_v1",),
        invalidators=("fomc_same_day",),
        source_freshness={"macro_indicator_provider": {"status": "fresh"}},
        metadata_json={"basis_note": "macro and rates restrictive"},
    )

    assert record.trade_date == date(2026, 6, 16)
    assert record.snapshot_time == snapshot_time
    assert record.source_set_key == "macro_indicator_provider"


def test_macro_snapshot_record_rejects_trade_date_mismatch():
    with pytest.raises(ValueError, match="trade_date"):
        MacroSnapshotRecord(
            macro_snapshot_id="macro-1",
            snapshot_time=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
            trade_date=date(2026, 6, 15),
            regime="balanced",
            risk_budget_multiplier=1.0,
            volatility_state=None,
            rates_state=None,
            liquidity_state=None,
            blocked_strategy_tags=(),
            invalidators=(),
            source_freshness={},
            metadata_json={},
        )


def test_macro_readthrough_event_record_normalizes_tickers_and_availability():
    event_time = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
    record = MacroReadthroughEventRecord(
        macro_readthrough_event_id="readthrough-1",
        event_key="readthrough:nvda:avgo:2026-06-16",
        source_ticker="nvda",
        affected_ticker="avgo",
        scope="peer",
        mechanism="earnings_readthrough",
        direction="negative",
        title="NVDA read-through pressures peers",
        source="fixture",
        event_time=event_time,
        published_at=event_time,
        available_for_decision_at=event_time,
        valid_until=event_time,
        metadata_json={"relationship_context": "peer"},
    )

    assert record.source_ticker == "NVDA"
    assert record.affected_ticker == "AVGO"


def test_macro_readthrough_event_record_rejects_invalid_availability():
    with pytest.raises(ValueError, match="available_for_decision_at"):
        MacroReadthroughEventRecord(
            macro_readthrough_event_id="readthrough-1",
            event_key="readthrough:nvda:avgo:2026-06-16",
            source_ticker="NVDA",
            affected_ticker="AVGO",
            scope="peer",
            mechanism="earnings_readthrough",
            direction="negative",
            title="NVDA read-through pressures peers",
            source="fixture",
            event_time=datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 6, 16, 10, 5, tzinfo=timezone.utc),
            available_for_decision_at=datetime(2026, 6, 16, 10, 4, tzinfo=timezone.utc),
            valid_until=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
            metadata_json={},
        )
