from __future__ import annotations

from datetime import datetime, timezone

from src.trading.intraday.news_alerts import NewsAlertRecord
from src.trading.intraday.rebalance import IntradayRebalanceDecisionRecord
from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository


class _FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def filter_by(self, **kwargs):
        filtered = [
            row
            for row in self._rows
            if all(getattr(row, key) == value for key, value in kwargs.items())
        ]
        return _FakeQuery(filtered)

    def all(self) -> list[object]:
        return list(self._rows)

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise AssertionError("expected at most one row")
        return self._rows[0]


class _FakeSession:
    def __init__(self) -> None:
        self.rows_by_type: dict[type, list[object]] = {}
        self.flush_calls = 0

    def add(self, row: object) -> None:
        self.rows_by_type.setdefault(type(row), []).append(row)

    def query(self, model: type) -> _FakeQuery:
        return _FakeQuery(self.rows_by_type.get(model, []))

    def flush(self) -> None:
        self.flush_calls += 1


def test_in_memory_repository_persists_intraday_scans_snapshots_and_alerts():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()

    scan = IntradaySignalScanRecord(
        intraday_signal_scan_id="scan-1",
        started_at=now,
        completed_at=now,
        decision_time=now,
        status="succeeded",
        scope_json={"tickers": ["NVDA"]},
        coverage_json={"tickers_requested": 1, "tickers_completed": 1},
        error_message=None,
        metadata_json={},
    )
    snapshot = IntradaySignalSnapshotRecord(
        intraday_signal_snapshot_id="intraday-1",
        intraday_signal_scan_id="scan-1",
        ticker="NVDA",
        decision_time=now,
        baseline_signal_snapshot_id="baseline-1",
        previous_intraday_snapshot_id=None,
        refreshed_signals_json={"technical": {"last_price": 125.0}},
        carried_forward_signals_json={"fundamental": {"market_cap_bucket": "mega"}},
        delta_vs_baseline_json={"technical": {"last_price": 5.0}},
        delta_vs_previous_json={},
        source_freshness_json={"technical": "fresh", "fundamental": "carried_forward_from_baseline"},
        metadata_json={},
        created_at=now,
    )
    alert = NewsAlertRecord(
        news_alert_id="alert-1",
        ticker="NVDA",
        source_ticker="NVDA",
        alert_type="earnings_beat_raise",
        sentiment="positive",
        severity="high",
        source="fixture",
        published_at=now,
        headline="NVDA rises after earnings beat and raised guidance",
        summary="Beat and raise guidance.",
        strategy_relevance=("earnings_drift_v1",),
        affected_positions=("position-1",),
        affected_candidates=("candidate-1",),
        affected_themes=("ai_semis",),
        readthrough_source_ticker=None,
        action_required=True,
        dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
        event_news_item_id="event-1",
        metadata_json={},
        created_at=now,
    )

    repository.save_intraday_signal_scan(scan)
    repository.save_intraday_signal_snapshot(snapshot)
    repository.save_news_alert(alert)
    repository.save_news_alert(alert)

    assert repository.intraday_signal_scans == [scan]
    assert repository.intraday_signal_snapshots == [snapshot]
    assert repository.news_alerts == [alert]

    repository.save_intraday_rebalance_decision(
        IntradayRebalanceDecisionRecord(
            intraday_rebalance_decision_id="rebalance-1",
            ticker="NVDA",
            action="hold",
            status="fallback",
            reason_code="classification_failed",
            confidence=0.0,
            target_weight=0.0,
            approved_quantity=0.0,
            thesis="",
            urgency="low",
            rationale=(),
            prompt_template=object(),
            prompt_run=object(),
            usage_events=[],
            decision_time=now,
            available_for_decision_at=now,
            risk_decision_id=None,
            metadata_json={},
        )
    )

    assert len(repository.intraday_rebalance_decisions) == 1


def test_sqlalchemy_repository_persists_intraday_scans_snapshots_and_alerts():
    now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repository = SqlAlchemyTradingRepository(session)

    repository.save_intraday_signal_scan(
        IntradaySignalScanRecord(
            intraday_signal_scan_id="scan-1",
            started_at=now,
            completed_at=now,
            decision_time=now,
            status="succeeded",
            scope_json={"tickers": ["NVDA"]},
            coverage_json={"tickers_requested": 1, "tickers_completed": 1},
            error_message=None,
            metadata_json={},
        )
    )
    repository.save_intraday_signal_snapshot(
        IntradaySignalSnapshotRecord(
            intraday_signal_snapshot_id="intraday-1",
            intraday_signal_scan_id="scan-1",
            ticker="NVDA",
            decision_time=now,
            baseline_signal_snapshot_id="baseline-1",
            previous_intraday_snapshot_id=None,
            refreshed_signals_json={"technical": {"last_price": 125.0}},
            carried_forward_signals_json={"fundamental": {"market_cap_bucket": "mega"}},
            delta_vs_baseline_json={"technical": {"last_price": 5.0}},
            delta_vs_previous_json={},
            source_freshness_json={"technical": "fresh", "fundamental": "carried_forward_from_baseline"},
            metadata_json={},
            created_at=now,
        )
    )
    repository.save_news_alert(
        NewsAlertRecord(
            news_alert_id="alert-1",
            ticker="NVDA",
            source_ticker="NVDA",
            alert_type="earnings_beat_raise",
            sentiment="positive",
            severity="high",
            source="fixture",
            published_at=now,
            headline="NVDA rises after earnings beat and raised guidance",
            summary="Beat and raise guidance.",
            strategy_relevance=("earnings_drift_v1",),
            affected_positions=("position-1",),
            affected_candidates=("candidate-1",),
            affected_themes=("ai_semis",),
            readthrough_source_ticker=None,
            action_required=True,
            dedupe_key="NVDA|earnings_beat_raise|2026-06-02T15:00:00+00:00",
            event_news_item_id="event-1",
            metadata_json={},
            created_at=now,
        )
    )
    repository.save_intraday_rebalance_decision(
        IntradayRebalanceDecisionRecord(
            intraday_rebalance_decision_id="rebalance-1",
            ticker="NVDA",
            action="hold",
            status="fallback",
            reason_code="classification_failed",
            confidence=0.0,
            target_weight=0.0,
            approved_quantity=0.0,
            thesis="",
            urgency="low",
            rationale=(),
            prompt_template=object(),
            prompt_run=object(),
            usage_events=[],
            decision_time=now,
            available_for_decision_at=now,
            risk_decision_id=None,
            metadata_json={},
        )
    )

    assert session.flush_calls >= 4
