"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from src.trading.provider_resilience import ProviderRequestRunRecord
from src.trading.signal_sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.universe import UniverseSnapshotResult


class InMemoryTradingRepository:
    """Collect PR02 operational artifacts without a DB session."""

    def __init__(self) -> None:
        self.universe_snapshots: list[UniverseSnapshotResult] = []
        self.signal_snapshots: list[SignalSnapshotResult] = []
        self.source_ingestion_runs: list[SourceIngestionRunRecord] = []
        self.provider_request_runs: list[ProviderRequestRunRecord] = []
        self.fundamental_snapshots: list[FundamentalSnapshotRecord] = []
        self.event_news_items: list[EventNewsItemRecord] = []

    def save_universe_snapshot(self, snapshot: UniverseSnapshotResult) -> None:
        self.universe_snapshots.append(snapshot)

    def save_signal_snapshot(self, snapshot: SignalSnapshotResult) -> None:
        self.signal_snapshots.append(snapshot)

    def record_source_ingestion_run(self, run: SourceIngestionRunRecord) -> None:
        self.source_ingestion_runs.append(run)

    def record_provider_request(self, run: ProviderRequestRunRecord) -> None:
        self.provider_request_runs.append(run)

    def record(self, run: ProviderRequestRunRecord) -> None:
        """ProviderRequestRecorder-compatible alias."""
        self.record_provider_request(run)

    def save_fundamental_snapshot(self, snapshot: FundamentalSnapshotRecord) -> None:
        self.fundamental_snapshots.append(snapshot)

    def save_event_news_item(self, item: EventNewsItemRecord) -> None:
        self.event_news_items.append(item)
