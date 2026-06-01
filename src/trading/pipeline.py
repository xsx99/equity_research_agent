"""PR02 universe and signal pipeline orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from src.trading.manual_requests import ManualTickerRequestService
from src.trading.signal_sources import InMemorySignalSourceRepository
from src.trading.signals import SignalSnapshotResult, build_signal_snapshot
from src.trading.universe import (
    UniverseFilterConfig,
    UniverseProvider,
    UniverseSnapshotResult,
    apply_universe_filters,
)


class UniverseScanPipeline:
    """Load provider assets and persist deterministic filter decisions."""

    def __init__(
        self,
        *,
        provider: UniverseProvider,
        config: UniverseFilterConfig,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> UniverseSnapshotResult:
        return apply_universe_filters(
            self.provider.fetch_universe_assets(),
            self.config,
            snapshot_time=self.now(),
        )


class SignalPipeline:
    """Build pre-open signal snapshots for scanner and active manual tickers."""

    def __init__(
        self,
        *,
        source_repository: InMemorySignalSourceRepository,
        manual_request_service: ManualTickerRequestService,
    ) -> None:
        self.source_repository = source_repository
        self.manual_request_service = manual_request_service

    def build_pre_open_snapshots(
        self,
        *,
        universe_result: UniverseSnapshotResult,
        decision_time: datetime,
    ) -> tuple[SignalSnapshotResult, ...]:
        included_symbols = list(universe_result.included_symbols)
        manual_requests = self.manual_request_service.load_active()
        manual_by_ticker = {request.ticker: request for request in manual_requests}
        tickers = included_symbols + [
            ticker for ticker in sorted(manual_by_ticker) if ticker not in included_symbols
        ]
        snapshots: list[SignalSnapshotResult] = []
        for ticker in tickers:
            manual_request = manual_by_ticker.get(ticker)
            source_records = self.source_repository.records_for_ticker(ticker)
            snapshot = build_signal_snapshot(
                ticker=ticker,
                decision_time=decision_time,
                source_records=source_records,
                snapshot_type="pre_open",
                selection_source="manual_request" if manual_request is not None else "scanner",
                manual_request_id=manual_request.request_id if manual_request is not None else None,
            )
            snapshots.append(snapshot)
            if manual_request is not None:
                result_status = (
                    "blocked_by_missing_data"
                    if snapshot.source_freshness_json.get("technical") == "missing"
                    else "ordinary_watch"
                )
                self.manual_request_service.record_evaluation(
                    manual_request.request_id,
                    result_status=result_status,
                    signal_snapshot_id=snapshot.signal_snapshot_id,
                )
        return tuple(snapshots)
