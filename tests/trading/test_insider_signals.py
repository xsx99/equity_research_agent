from datetime import datetime, timedelta, timezone

from src.trading.signals.insider import build_insider_signals
from src.trading.signals.sources import SourceRecord


def _insider_record(
    *,
    source_record_id: str,
    available_for_decision_at: datetime,
    published_at: datetime,
    transaction_type: str,
    total_value: float,
    is_officer: bool = False,
    is_director: bool = False,
) -> SourceRecord:
    return SourceRecord(
        ticker="NVDA",
        source_family="insider",
        source="fixture",
        source_table="insider_trades",
        source_record_id=source_record_id,
        event_time=published_at,
        published_at=published_at,
        ingested_at=published_at,
        available_for_decision_at=available_for_decision_at,
        payload={
            "transaction_type": transaction_type,
            "total_value": total_value,
            "is_officer": is_officer,
            "is_director": is_director,
        },
    )


def test_build_insider_signals_aggregates_cluster_buys_and_sales():
    decision_time = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
    five_days_ago = decision_time - timedelta(days=5)
    twelve_days_ago = decision_time - timedelta(days=12)
    forty_days_ago = decision_time - timedelta(days=40)

    signals = build_insider_signals(
        (
            _insider_record(
                source_record_id="buy-officer",
                available_for_decision_at=five_days_ago,
                published_at=five_days_ago,
                transaction_type="P",
                total_value=250_000.0,
                is_officer=True,
            ),
            _insider_record(
                source_record_id="buy-director",
                available_for_decision_at=twelve_days_ago,
                published_at=twelve_days_ago,
                transaction_type="P",
                total_value=125_000.0,
                is_director=True,
            ),
            _insider_record(
                source_record_id="sale-director",
                available_for_decision_at=forty_days_ago,
                published_at=forty_days_ago,
                transaction_type="S",
                total_value=50_000.0,
                is_director=True,
            ),
        ),
        decision_time=decision_time,
    )

    assert signals.values["purchase_count_30d"] == 2
    assert signals.values["sale_count_30d"] == 0
    assert signals.values["insider_net_buy_value_30d"] == 375_000.0
    assert signals.values["insider_net_buy_value_90d"] == 325_000.0
    assert signals.values["insider_cluster_buy_count_90d"] == 2
    assert signals.values["officer_buy_flag"] is True
    assert signals.values["director_buy_flag"] is True
    assert signals.values["sale_concentration_score"] == 0.1333
    assert signals.values["recent_form4_filing_at"] == five_days_ago.isoformat()


def test_build_insider_signals_treats_covered_empty_records_as_no_activity():
    decision_time = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)

    signals = build_insider_signals(
        (),
        decision_time=decision_time,
        data_covered=True,
    )

    assert signals.values == {
        "purchase_count_30d": 0,
        "sale_count_30d": 0,
        "insider_net_buy_value_30d": 0.0,
        "insider_net_buy_value_90d": 0.0,
        "insider_cluster_buy_count_90d": 0,
        "officer_buy_flag": False,
        "director_buy_flag": False,
        "sale_concentration_score": 0.0,
        "recent_form4_filing_at": None,
    }
    assert signals.missing == ()


def test_build_insider_signals_keeps_uncovered_empty_records_missing():
    decision_time = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)

    signals = build_insider_signals(
        (),
        decision_time=decision_time,
        data_covered=False,
    )

    assert signals.values == {}
    assert signals.missing == (
        "purchase_count_30d",
        "sale_count_30d",
        "insider_net_buy_value_30d",
        "insider_net_buy_value_90d",
        "insider_cluster_buy_count_90d",
        "officer_buy_flag",
        "director_buy_flag",
        "sale_concentration_score",
        "recent_form4_filing_at",
    )
