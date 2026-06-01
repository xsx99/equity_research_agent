"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from src.trading.provider_resilience import ProviderRequestRunRecord
from src.trading.signals import SignalSnapshotResult
from src.trading.universe import UniverseSnapshotResult


class InMemoryTradingRepository:
    """Collect PR02 operational artifacts without a DB session."""

    def __init__(self) -> None:
        self.universe_snapshots: list[UniverseSnapshotResult] = []
        self.signal_snapshots: list[SignalSnapshotResult] = []
        self.provider_request_runs: list[ProviderRequestRunRecord] = []

    def save_universe_snapshot(self, snapshot: UniverseSnapshotResult) -> None:
        self.universe_snapshots.append(snapshot)

    def save_signal_snapshot(self, snapshot: SignalSnapshotResult) -> None:
        self.signal_snapshots.append(snapshot)

    def record_provider_request(self, run: ProviderRequestRunRecord) -> None:
        self.provider_request_runs.append(run)
