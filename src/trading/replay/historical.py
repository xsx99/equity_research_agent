"""Historical replay orchestration for PR03 strategy matching outcomes."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord, OutcomeEvaluator
from src.trading.strategies.selector import (
    PrimaryStrategySelector,
    SelectedTradeRecord,
    WatchCandidateRecord,
)
from src.trading.strategies.matching import (
    CandidateScoreRecord,
    StrategyMatcher,
    StrategyRunRecord,
    create_strategy_run,
)
from src.trading.strategies.classifier import TradeClassificationRecord, TradeClassifier


@dataclass(frozen=True)
class HistoricalReplayRunRecord:
    """One deterministic replay batch."""

    historical_replay_run_id: str
    decision_time: datetime
    snapshot_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    decision_filter_json: dict[str, Any]
    outcome_horizon_policy_json: dict[str, Any]
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoricalReplayResult:
    """Replay artifacts persisted by the runner."""

    replay_run: HistoricalReplayRunRecord
    strategy_run: StrategyRunRecord
    candidates: tuple[CandidateScoreRecord, ...]
    selected_trades: tuple[SelectedTradeRecord, ...]
    watch_candidates: tuple[WatchCandidateRecord, ...]
    classifications: tuple[TradeClassificationRecord, ...]
    outcomes: tuple[CandidateOutcomeEvaluationRecord, ...]


class HistoricalReplayRunner:
    """Reconstruct candidates from stored PIT snapshots, then evaluate outcomes."""

    def __init__(
        self,
        *,
        repository: Any,
        outcome_evaluator: OutcomeEvaluator,
        matcher: StrategyMatcher | None = None,
        selector: PrimaryStrategySelector | None = None,
        classifier: TradeClassifier | None = None,
        now: Any | None = None,
    ) -> None:
        self.repository = repository
        self.outcome_evaluator = outcome_evaluator
        self.matcher = matcher or StrategyMatcher()
        self.selector = selector or PrimaryStrategySelector()
        self.classifier = classifier or TradeClassifier()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        decision_time: datetime,
        horizon_end_at: datetime,
        snapshot_type: str = "pre_open",
        benchmark_symbols: tuple[str, ...] = ("QQQ", "SPY"),
    ) -> HistoricalReplayResult:
        started_at = self.now()
        replay_run = HistoricalReplayRunRecord(
            historical_replay_run_id=str(uuid.uuid4()),
            decision_time=decision_time,
            snapshot_type=snapshot_type,
            status="running",
            started_at=started_at,
            completed_at=None,
            decision_filter_json={
                "decision_time": decision_time.isoformat(),
                "available_for_decision_at_lte": decision_time.isoformat(),
                "snapshot_type": snapshot_type,
            },
            outcome_horizon_policy_json={"horizon_end_at": horizon_end_at.isoformat()},
            metadata_json={},
        )
        snapshots = self.repository.load_signal_snapshots_for_decision(
            decision_time=decision_time,
            snapshot_type=snapshot_type,
        )
        strategy_run = create_strategy_run(
            decision_time=decision_time,
            snapshot_type=snapshot_type,
            metadata_json={"source": "historical_replay", "replay_run_id": replay_run.historical_replay_run_id},
        )
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
        classification_by_candidate = {
            classification.candidate_score_id: classification for classification in classifications
        }
        outcomes = tuple(
            self.outcome_evaluator.evaluate(
                candidate,
                classification_by_candidate.get(candidate.candidate_score_id),
                horizon_start_at=decision_time,
                horizon_end_at=horizon_end_at,
                benchmark_symbols=benchmark_symbols,
                historical_replay_run_id=replay_run.historical_replay_run_id,
            )
            for candidate in candidates
        )
        completed_run = HistoricalReplayRunRecord(
            **{**replay_run.__dict__, "status": "succeeded", "completed_at": self.now()}
        )
        self.repository.save_historical_replay_run(completed_run)
        self.repository.save_strategy_run(strategy_run)
        self.repository.save_candidate_scores(candidates)
        self.repository.save_watch_candidates(selection.watch_candidates)
        self.repository.save_trade_classifications(classifications)
        self.repository.save_candidate_outcome_evaluations(outcomes)
        return HistoricalReplayResult(
            replay_run=completed_run,
            strategy_run=strategy_run,
            candidates=candidates,
            selected_trades=selection.selected_trades,
            watch_candidates=selection.watch_candidates,
            classifications=classifications,
            outcomes=outcomes,
        )
