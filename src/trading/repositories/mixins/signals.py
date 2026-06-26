from __future__ import annotations

from src.trading.repositories._base import *  # noqa: F401,F403


class SignalsRepositoryMixin:
    def save_signal_snapshot(self, snapshot: SignalSnapshotResult) -> None:
        row = self.session.query(SignalSnapshot).filter_by(
            signal_snapshot_id=_to_uuid(snapshot.signal_snapshot_id)
        ).one_or_none()
        if row is None:
            row = SignalSnapshot(signal_snapshot_id=_to_uuid(snapshot.signal_snapshot_id))
            self.session.add(row)
        row.ticker = snapshot.ticker
        row.snapshot_type = snapshot.snapshot_type
        row.decision_time = snapshot.decision_time
        row.available_for_decision_at = snapshot.available_for_decision_at
        row.max_input_available_for_decision_at = snapshot.max_input_available_for_decision_at
        row.signal_json = dict(snapshot.signal_json)
        row.source_freshness_json = dict(snapshot.source_freshness_json)
        row.missing_signals_json = list(snapshot.missing_signals_json)
        row.stale_signals_json = list(snapshot.stale_signals_json)
        row.source_record_refs_json = list(snapshot.source_record_refs_json)
        row.source_available_times_json = dict(snapshot.source_available_times_json)
        row.excluded_future_source_count = int(snapshot.excluded_future_source_count)
        row.point_in_time_passed = bool(snapshot.point_in_time_passed)
        row.selection_source = snapshot.selection_source
        row.manual_request_id = _to_uuid_or_none(snapshot.manual_request_id)
        row.universe_snapshot_id = None
        row.metadata_json = {}
        self.session.flush()
    def load_signal_snapshots_for_decision(
        self,
        *,
        decision_time: Any,
        snapshot_type: str = "pre_open",
    ) -> tuple[SignalSnapshotResult, ...]:
        selected_by_ticker: dict[str, SignalSnapshotResult] = {}
        for row in self.session.query(SignalSnapshot).all():
            if row.snapshot_type != snapshot_type:
                continue
            if row.decision_time != decision_time:
                continue
            if row.available_for_decision_at > decision_time:
                continue
            snapshot = SignalSnapshotResult(
                signal_snapshot_id=str(row.signal_snapshot_id),
                ticker=row.ticker,
                snapshot_type=row.snapshot_type,
                decision_time=row.decision_time,
                available_for_decision_at=row.available_for_decision_at,
                max_input_available_for_decision_at=row.max_input_available_for_decision_at,
                signal_json=dict(row.signal_json or {}),
                source_freshness_json=dict(row.source_freshness_json or {}),
                missing_signals_json=list(row.missing_signals_json or []),
                stale_signals_json=list(row.stale_signals_json or []),
                source_record_refs_json=list(row.source_record_refs_json or []),
                source_available_times_json=dict(row.source_available_times_json or {}),
                excluded_future_source_count=int(row.excluded_future_source_count or 0),
                point_in_time_passed=bool(row.point_in_time_passed),
                selection_source=row.selection_source,
                manual_request_id=str(row.manual_request_id) if row.manual_request_id is not None else None,
            )
            current = selected_by_ticker.get(snapshot.ticker)
            if current is None or snapshot.available_for_decision_at > current.available_for_decision_at:
                selected_by_ticker[snapshot.ticker] = snapshot
        return tuple(snapshot for _ticker, snapshot in sorted(selected_by_ticker.items()))
    def load_previous_signal_snapshot(
        self,
        *,
        ticker: str,
        before_decision_time: Any,
        snapshot_type: str = "pre_open",
    ) -> SignalSnapshotResult | None:
        symbol = ticker.strip().upper()
        previous: list[SignalSnapshotResult] = []
        for row in self.session.query(SignalSnapshot).all():
            if row.ticker != symbol or row.snapshot_type != snapshot_type:
                continue
            if row.decision_time >= before_decision_time or row.available_for_decision_at > before_decision_time:
                continue
            previous.append(
                SignalSnapshotResult(
                    signal_snapshot_id=str(row.signal_snapshot_id),
                    ticker=row.ticker,
                    snapshot_type=row.snapshot_type,
                    decision_time=row.decision_time,
                    available_for_decision_at=row.available_for_decision_at,
                    max_input_available_for_decision_at=row.max_input_available_for_decision_at,
                    signal_json=dict(row.signal_json or {}),
                    source_freshness_json=dict(row.source_freshness_json or {}),
                    missing_signals_json=list(row.missing_signals_json or []),
                    stale_signals_json=list(row.stale_signals_json or []),
                    source_record_refs_json=list(row.source_record_refs_json or []),
                    source_available_times_json=dict(row.source_available_times_json or {}),
                    excluded_future_source_count=int(row.excluded_future_source_count or 0),
                    point_in_time_passed=bool(row.point_in_time_passed),
                    selection_source=row.selection_source,
                    manual_request_id=str(row.manual_request_id) if row.manual_request_id is not None else None,
                )
            )
        if not previous:
            return None
        return max(previous, key=lambda snapshot: (snapshot.decision_time, snapshot.available_for_decision_at))
    def load_event_news_items(
        self,
        *,
        source_record_ids: tuple[str, ...],
    ) -> tuple[EventNewsItemRecord, ...]:
        if not source_record_ids:
            return ()
        wanted = {_to_uuid(source_record_id) for source_record_id in source_record_ids}
        rows = [
            row
            for row in self.session.query(EventNewsItem).all()
            if row.event_news_item_id in wanted
        ]
        return tuple(self._to_event_news_item_record(row) for row in rows)
    def load_latest_signal_snapshots_for_tickers(
        self,
        *,
        tickers: tuple[str, ...],
        snapshot_type: str,
        trade_date: date,
    ) -> dict[str, SignalSnapshotResult]:
        selected_by_ticker: dict[str, SignalSnapshotResult] = {}
        ticker_set = {ticker.strip().upper() for ticker in tickers}
        for row in self.session.query(SignalSnapshot).all():
            if row.snapshot_type != snapshot_type or row.ticker not in ticker_set:
                continue
            if row.decision_time.date() != trade_date:
                continue
            snapshot = SignalSnapshotResult(
                signal_snapshot_id=str(row.signal_snapshot_id),
                ticker=row.ticker,
                snapshot_type=row.snapshot_type,
                decision_time=row.decision_time,
                available_for_decision_at=row.available_for_decision_at,
                max_input_available_for_decision_at=row.max_input_available_for_decision_at,
                signal_json=dict(row.signal_json or {}),
                source_freshness_json=dict(row.source_freshness_json or {}),
                missing_signals_json=list(row.missing_signals_json or []),
                stale_signals_json=list(row.stale_signals_json or []),
                source_record_refs_json=list(row.source_record_refs_json or []),
                source_available_times_json=dict(row.source_available_times_json or {}),
                excluded_future_source_count=int(row.excluded_future_source_count or 0),
                point_in_time_passed=bool(row.point_in_time_passed),
                selection_source=row.selection_source,
                manual_request_id=str(row.manual_request_id) if row.manual_request_id is not None else None,
            )
            current = selected_by_ticker.get(snapshot.ticker)
            if current is None or snapshot.available_for_decision_at > current.available_for_decision_at:
                selected_by_ticker[snapshot.ticker] = snapshot
        return selected_by_ticker
