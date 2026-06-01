"""PR02 universe and signal pipeline orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable, Protocol

from src.trading.manual_requests import ManualTickerRequestService
from src.trading.primary_strategy_selector import PrimaryStrategySelector, SelectedStrategyRecord
from src.trading.repository import InMemoryTradingRepository
from src.trading.signal_sources import InMemorySignalSourceRepository
from src.trading.signals import SignalSnapshotResult, build_signal_snapshot
from src.trading.strategy_matching import CandidateScoreRecord, StrategyMatcher, StrategyRunRecord, create_strategy_run
from src.trading.trade_classifier import TradeClassificationRecord, TradeClassifier
from src.trading.universe import (
    UniverseFilterConfig,
    UniverseProvider,
    UniverseSnapshotResult,
    apply_universe_filters,
)


class SourceIngestionServiceProtocol(Protocol):
    """Minimal ingestion service API consumed by the SignalPipeline."""

    def refresh_tickers(
        self,
        tickers: tuple[str, ...],
        *,
        as_of: datetime,
        run_type: str,
    ) -> object:
        """Refresh source rows for the requested tickers."""


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
        source_ingestion_service: SourceIngestionServiceProtocol | None = None,
    ) -> None:
        self.source_repository = source_repository
        self.manual_request_service = manual_request_service
        self.source_ingestion_service = source_ingestion_service

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
        if self.source_ingestion_service is not None:
            self.source_ingestion_service.refresh_tickers(
                tuple(tickers),
                as_of=decision_time,
                run_type="pre_open",
            )
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


@dataclass(frozen=True)
class StrategyPipelineResult:
    """Candidate-scoring and classification output before TradingPipeline exists."""

    strategy_run: StrategyRunRecord
    candidates: tuple[CandidateScoreRecord, ...]
    selected: tuple[SelectedStrategyRecord, ...]
    classifications: tuple[TradeClassificationRecord, ...]


class StrategyPipeline:
    """Match signal snapshots to strategies and classify selected candidates."""

    def __init__(
        self,
        *,
        repository: InMemoryTradingRepository,
        manual_request_service: ManualTickerRequestService | None = None,
        matcher: StrategyMatcher | None = None,
        selector: PrimaryStrategySelector | None = None,
        classifier: TradeClassifier | None = None,
    ) -> None:
        self.repository = repository
        self.manual_request_service = manual_request_service
        self.matcher = matcher or StrategyMatcher()
        self.selector = selector or PrimaryStrategySelector()
        self.classifier = classifier or TradeClassifier()

    def run(
        self,
        *,
        snapshots: tuple[SignalSnapshotResult, ...],
        decision_time: datetime,
        snapshot_type: str = "pre_open",
    ) -> StrategyPipelineResult:
        """Persist PR03 strategy candidates and trade classifications."""
        strategy_run = create_strategy_run(decision_time=decision_time, snapshot_type=snapshot_type)
        definitions = self.repository.load_active_strategy_definitions()
        candidates = tuple(
            self.matcher.match(
                snapshots,
                definitions,
                strategy_run_id=strategy_run.strategy_run_id,
            )
        )
        selected = tuple(self.selector.select(candidates, definitions))
        classifications = tuple(self.classifier.classify_many(selected))
        self.repository.save_strategy_run(strategy_run)
        self.repository.save_candidate_scores(candidates)
        self.repository.save_trade_classifications(classifications)
        self._record_manual_request_results(classifications)
        return StrategyPipelineResult(
            strategy_run=strategy_run,
            candidates=candidates,
            selected=selected,
            classifications=classifications,
        )

    def _record_manual_request_results(self, classifications: tuple[TradeClassificationRecord, ...]) -> None:
        if self.manual_request_service is None:
            return
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in self.repository.candidate_scores}
        for classification in classifications:
            candidate = candidate_by_id.get(classification.candidate_score_id)
            if candidate is None or candidate.manual_request_id is None:
                continue
            self.manual_request_service.record_evaluation(
                candidate.manual_request_id,
                result_status=classification.result_status,
                signal_snapshot_id=candidate.signal_snapshot_id,
            )
