"""Strategy scoring workflow."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.strategies.selector import (
    PrimaryStrategySelector,
    SelectedTradeRecord,
    WatchCandidateRecord,
)
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.signals import SignalSnapshotResult
from src.trading.strategies.matching import CandidateScoreRecord, StrategyMatcher, StrategyRunRecord, create_strategy_run
from src.trading.strategies.classifier import TradeClassificationRecord, TradeClassifier


@dataclass(frozen=True)
class StrategyPipelineResult:
    """Candidate-scoring and classification output before TradingPipeline exists."""

    strategy_run: StrategyRunRecord
    candidates: tuple[CandidateScoreRecord, ...]
    selected_trades: tuple[SelectedTradeRecord, ...]
    watch_candidates: tuple[WatchCandidateRecord, ...]
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
        selection = self.selector.select(candidates, definitions)
        classifications = tuple(self.classifier.classify_many(selection.selected_trades))
        self.repository.save_strategy_run(strategy_run)
        self.repository.save_candidate_scores(candidates)
        self.repository.save_watch_candidates(selection.watch_candidates)
        self.repository.save_trade_classifications(classifications)
        self._record_manual_request_results(candidates, classifications, selection.watch_candidates)
        return StrategyPipelineResult(
            strategy_run=strategy_run,
            candidates=candidates,
            selected_trades=selection.selected_trades,
            watch_candidates=selection.watch_candidates,
            classifications=classifications,
        )

    def _record_manual_request_results(
        self,
        candidates: tuple[CandidateScoreRecord, ...],
        classifications: tuple[TradeClassificationRecord, ...],
        watch_candidates: tuple[WatchCandidateRecord, ...],
    ) -> None:
        if self.manual_request_service is None:
            return
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in candidates}
        for classification in classifications:
            candidate = candidate_by_id.get(classification.candidate_score_id)
            if candidate is None or candidate.manual_request_id is None:
                continue
            self.manual_request_service.record_evaluation(
                candidate.manual_request_id,
                result_status=classification.result_status,
                signal_snapshot_id=candidate.signal_snapshot_id,
            )
        for watch in watch_candidates:
            candidate = watch.candidate
            if candidate.manual_request_id is None:
                continue
            self.manual_request_service.record_evaluation(
                candidate.manual_request_id,
                result_status=watch.result_status,
                signal_snapshot_id=candidate.signal_snapshot_id,
            )
