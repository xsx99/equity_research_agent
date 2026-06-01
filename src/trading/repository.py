"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from datetime import datetime

from src.trading.historical_replay import HistoricalReplayRunRecord
from src.trading.outcome_evaluator import CandidateOutcomeEvaluationRecord
from src.trading.provider_resilience import ProviderRequestRunRecord
from src.trading.signal_sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.strategy_matching import CandidateScoreRecord, StrategyDefinitionRecord, StrategyRunRecord
from src.trading.trade_classifier import TradeClassificationRecord
from src.trading.universe import UniverseSnapshotResult


class InMemoryTradingRepository:
    """Collect trading operational artifacts without a DB session."""

    def __init__(self) -> None:
        self.universe_snapshots: list[UniverseSnapshotResult] = []
        self.signal_snapshots: list[SignalSnapshotResult] = []
        self.source_ingestion_runs: list[SourceIngestionRunRecord] = []
        self.provider_request_runs: list[ProviderRequestRunRecord] = []
        self.fundamental_snapshots: list[FundamentalSnapshotRecord] = []
        self.event_news_items: list[EventNewsItemRecord] = []
        self.strategy_definitions: list[StrategyDefinitionRecord] = []
        self.strategy_runs: list[StrategyRunRecord] = []
        self.candidate_scores: list[CandidateScoreRecord] = []
        self.trade_classifications: list[TradeClassificationRecord] = []
        self.historical_replay_runs: list[HistoricalReplayRunRecord] = []
        self.candidate_outcome_evaluations: list[CandidateOutcomeEvaluationRecord] = []

    def save_universe_snapshot(self, snapshot: UniverseSnapshotResult) -> None:
        self.universe_snapshots.append(snapshot)

    def save_signal_snapshot(self, snapshot: SignalSnapshotResult) -> None:
        self.signal_snapshots.append(snapshot)

    def load_signal_snapshots_for_decision(
        self,
        *,
        decision_time: datetime,
        snapshot_type: str = "pre_open",
    ) -> tuple[SignalSnapshotResult, ...]:
        """Return snapshots that were decision-available at the requested time."""
        selected_by_ticker: dict[str, SignalSnapshotResult] = {}
        for snapshot in self.signal_snapshots:
            if snapshot.snapshot_type != snapshot_type:
                continue
            if snapshot.decision_time != decision_time:
                continue
            if snapshot.available_for_decision_at > decision_time:
                continue
            current = selected_by_ticker.get(snapshot.ticker)
            if current is None or snapshot.available_for_decision_at > current.available_for_decision_at:
                selected_by_ticker[snapshot.ticker] = snapshot
        return tuple(snapshot for _ticker, snapshot in sorted(selected_by_ticker.items()))

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

    def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
        self.strategy_definitions.append(definition)

    def load_active_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        """Return active strategy and expression definitions for matching/selection."""
        return [
            definition
            for definition in self.strategy_definitions
            if definition.is_active and definition.lifecycle_status in {"active", "experimental", "shadow"}
        ]

    def save_strategy_run(self, run: StrategyRunRecord) -> None:
        self.strategy_runs.append(run)

    def save_candidate_scores(self, candidates: list[CandidateScoreRecord] | tuple[CandidateScoreRecord, ...]) -> None:
        self.candidate_scores.extend(candidates)

    def save_trade_classifications(
        self,
        classifications: list[TradeClassificationRecord] | tuple[TradeClassificationRecord, ...],
    ) -> None:
        self.trade_classifications.extend(classifications)

    def save_historical_replay_run(self, run: HistoricalReplayRunRecord) -> None:
        self.historical_replay_runs.append(run)

    def save_candidate_outcome_evaluations(
        self,
        outcomes: list[CandidateOutcomeEvaluationRecord] | tuple[CandidateOutcomeEvaluationRecord, ...],
    ) -> None:
        self.candidate_outcome_evaluations.extend(outcomes)
