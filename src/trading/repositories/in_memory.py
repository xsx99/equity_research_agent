"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.trading.replay.historical import HistoricalReplayRunRecord
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.data_sources.provider_resilience import ProviderRequestRunRecord
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.risk import (
    PortfolioRiskSnapshotRecord,
    PositionSizingDecisionRecord,
    RiskDecisionRecord,
    RiskFactorExposureRecord,
)
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord, StrategyRunRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.data_sources.universe import UniverseSnapshotResult

if TYPE_CHECKING:
    from src.trading.workflows.trading_decision import TradingDecisionRecord


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
        self.position_sizing_decisions: list[PositionSizingDecisionRecord] = []
        self.portfolio_risk_snapshots: list[PortfolioRiskSnapshotRecord] = []
        self.risk_factor_exposures: list[RiskFactorExposureRecord] = []
        self.risk_decisions: list[RiskDecisionRecord] = []
        self.llm_prompt_templates: list[object] = []
        self.llm_prompt_runs: list[object] = []
        self.llm_usage_events: list[object] = []
        self.trading_decisions: list["TradingDecisionRecord"] = []
        self.paper_orders: list[PaperOrderRecord] = []
        self.paper_executions: list[PaperExecutionRecord] = []
        self.paper_positions: list[StockPosition] = []
        self.portfolio_snapshots: list[PortfolioSnapshot] = []

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

    def save_position_sizing_decision(self, decision: PositionSizingDecisionRecord) -> None:
        self.position_sizing_decisions.append(decision)

    def save_portfolio_risk_snapshot(self, snapshot: PortfolioRiskSnapshotRecord) -> None:
        self.portfolio_risk_snapshots.append(snapshot)

    def save_risk_factor_exposures(
        self,
        exposures: list[RiskFactorExposureRecord] | tuple[RiskFactorExposureRecord, ...],
    ) -> None:
        self.risk_factor_exposures.extend(exposures)

    def save_risk_decision(self, decision: RiskDecisionRecord) -> None:
        self.risk_decisions.append(decision)

    def save_prompt_template(self, template: object) -> None:
        versioned = (getattr(template, "prompt_id", None), getattr(template, "prompt_version", None))
        existing = {
            (getattr(item, "prompt_id", None), getattr(item, "prompt_version", None))
            for item in self.llm_prompt_templates
        }
        if versioned not in existing:
            self.llm_prompt_templates.append(template)

    def save_prompt_run(self, prompt_run: object) -> None:
        self.llm_prompt_runs.append(prompt_run)

    def save_usage_events(self, usage_events: list[object] | tuple[object, ...]) -> None:
        self.llm_usage_events.extend(usage_events)

    def save_trading_decision(self, decision: "TradingDecisionRecord") -> None:
        self.trading_decisions.append(decision)

    def save_paper_order(self, order: PaperOrderRecord) -> None:
        if order.paper_order_id not in {item.paper_order_id for item in self.paper_orders}:
            self.paper_orders.append(order)

    def save_paper_execution(self, execution: PaperExecutionRecord) -> None:
        if execution.paper_execution_id not in {item.paper_execution_id for item in self.paper_executions}:
            self.paper_executions.append(execution)

    def has_paper_execution(self, paper_execution_id: str) -> bool:
        return any(item.paper_execution_id == paper_execution_id for item in self.paper_executions)

    def save_paper_position(self, position: StockPosition) -> None:
        self.paper_positions = [item for item in self.paper_positions if item.ticker != position.ticker]
        self.paper_positions.append(position)
        self.paper_positions.sort(key=lambda item: item.ticker)

    def load_paper_positions(self) -> tuple[StockPosition, ...]:
        return tuple(sorted(self.paper_positions, key=lambda item: item.ticker))

    def replace_paper_positions(self, positions: tuple[StockPosition, ...] | list[StockPosition]) -> None:
        self.paper_positions = sorted(list(positions), key=lambda item: item.ticker)

    def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self.portfolio_snapshots.append(snapshot)
