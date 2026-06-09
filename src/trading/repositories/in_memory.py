"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.trading.replay.historical import HistoricalReplayRunRecord
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.data_sources.provider_resilience import ProviderRequestRunRecord
from src.trading.brokers.paper_option import (
    PaperOptionExecutionRecord,
    PaperOptionOrderRecord,
    PaperOptionPosition,
)
from src.trading.intraday.news_alerts import NewsAlertRecord
from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
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
from src.trading.strategies.selector import WatchCandidateRecord
from src.trading.data_sources.universe import UniverseSnapshotResult

if TYPE_CHECKING:
    from src.trading.intraday.rebalance import IntradayRebalanceDecisionRecord
    from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
    from src.trading.post_close.strategy_evolution import (
        StrategyEvaluationResultRecord,
        StrategyProposalRecord,
    )
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
        self.watch_candidates: list[WatchCandidateRecord] = []
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
        self.option_strategy_decisions: list[OptionStrategyDecisionRecord] = []
        self.option_strategy_legs: list[OptionStrategyLegRecord] = []
        self.risk_hedge_decisions: list[RiskHedgeDecisionRecord] = []
        self.paper_option_orders: list[PaperOptionOrderRecord] = []
        self.paper_option_executions: list[PaperOptionExecutionRecord] = []
        self.paper_option_positions: list[PaperOptionPosition] = []
        self.option_risk_snapshots: list[OptionRiskSnapshotRecord] = []
        self.portfolio_snapshots: list[PortfolioSnapshot] = []
        self.intraday_signal_scans: list[IntradaySignalScanRecord] = []
        self.intraday_signal_snapshots: list[IntradaySignalSnapshotRecord] = []
        self.news_alerts: list[NewsAlertRecord] = []
        self.intraday_rebalance_decisions: list["IntradayRebalanceDecisionRecord"] = []
        self.daily_reflections: list["DailyReflectionRecord"] = []
        self.learning_factors: list["LearningFactorRecord"] = []
        self.strategy_proposals: list["StrategyProposalRecord"] = []
        self.strategy_evaluation_results: list["StrategyEvaluationResultRecord"] = []

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

    def load_previous_signal_snapshot(
        self,
        *,
        ticker: str,
        before_decision_time: datetime,
        snapshot_type: str = "pre_open",
    ) -> SignalSnapshotResult | None:
        symbol = ticker.strip().upper()
        previous = [
            snapshot
            for snapshot in self.signal_snapshots
            if snapshot.ticker == symbol
            and snapshot.snapshot_type == snapshot_type
            and snapshot.decision_time < before_decision_time
            and snapshot.available_for_decision_at <= before_decision_time
        ]
        if not previous:
            return None
        return max(previous, key=lambda snapshot: (snapshot.decision_time, snapshot.available_for_decision_at))

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

    def load_event_news_items(
        self,
        *,
        source_record_ids: tuple[str, ...],
    ) -> tuple[EventNewsItemRecord, ...]:
        wanted = set(source_record_ids)
        return tuple(item for item in self.event_news_items if item.event_news_item_id in wanted)

    def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
        self.strategy_definitions = [
            item for item in self.strategy_definitions if item.strategy_definition_id != definition.strategy_definition_id
        ]
        self.strategy_definitions.append(definition)

    def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        return list(self.strategy_definitions)

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

    def save_watch_candidates(
        self,
        watch_candidates: list[WatchCandidateRecord] | tuple[WatchCandidateRecord, ...],
    ) -> None:
        self.watch_candidates.extend(watch_candidates)

    def save_trade_classifications(
        self,
        classifications: list[TradeClassificationRecord] | tuple[TradeClassificationRecord, ...],
    ) -> None:
        for classification in classifications:
            self.trade_classifications = [
                item
                for item in self.trade_classifications
                if item.trade_classification_id != classification.trade_classification_id
            ]
            self.trade_classifications.append(classification)

    def load_trade_classification(self, trade_classification_id: str | None) -> TradeClassificationRecord | None:
        if trade_classification_id is None:
            return None
        for classification in self.trade_classifications:
            if classification.trade_classification_id == trade_classification_id:
                return classification
        return None

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
        self.trading_decisions = [
            item
            for item in self.trading_decisions
            if item.trading_decision_id != decision.trading_decision_id
        ]
        self.trading_decisions.append(decision)

    def save_option_strategy_decision(self, decision: OptionStrategyDecisionRecord) -> None:
        self.option_strategy_decisions.append(decision)

    def save_option_strategy_legs(
        self,
        legs: list[OptionStrategyLegRecord] | tuple[OptionStrategyLegRecord, ...],
    ) -> None:
        self.option_strategy_legs.extend(legs)

    def save_option_risk_snapshot(self, snapshot: OptionRiskSnapshotRecord) -> None:
        self.option_risk_snapshots.append(snapshot)

    def save_risk_hedge_decision(self, decision: RiskHedgeDecisionRecord) -> None:
        self.risk_hedge_decisions.append(decision)

    def save_paper_order(self, order: PaperOrderRecord) -> None:
        if order.paper_order_id not in {item.paper_order_id for item in self.paper_orders}:
            self.paper_orders.append(order)

    def save_paper_execution(self, execution: PaperExecutionRecord) -> None:
        if execution.paper_execution_id not in {item.paper_execution_id for item in self.paper_executions}:
            self.paper_executions.append(execution)

    def has_paper_execution(self, paper_execution_id: str) -> bool:
        return any(item.paper_execution_id == paper_execution_id for item in self.paper_executions)

    def save_paper_option_order(self, order: PaperOptionOrderRecord) -> None:
        if order.paper_option_order_id not in {item.paper_option_order_id for item in self.paper_option_orders}:
            self.paper_option_orders.append(order)

    def save_paper_option_execution(self, execution: PaperOptionExecutionRecord) -> None:
        if execution.paper_option_execution_id not in {
            item.paper_option_execution_id for item in self.paper_option_executions
        }:
            self.paper_option_executions.append(execution)

    def has_paper_option_execution(self, paper_option_execution_id: str) -> bool:
        return any(item.paper_option_execution_id == paper_option_execution_id for item in self.paper_option_executions)

    def save_paper_position(self, position: StockPosition) -> None:
        self.paper_positions = [item for item in self.paper_positions if item.ticker != position.ticker]
        self.paper_positions.append(position)
        self.paper_positions.sort(key=lambda item: item.ticker)

    def load_paper_positions(self) -> tuple[StockPosition, ...]:
        return tuple(sorted(self.paper_positions, key=lambda item: item.ticker))

    def replace_paper_positions(self, positions: tuple[StockPosition, ...] | list[StockPosition]) -> None:
        self.paper_positions = sorted(list(positions), key=lambda item: item.ticker)

    def save_paper_option_position(self, position: PaperOptionPosition) -> None:
        self.paper_option_positions = [
            item for item in self.paper_option_positions if item.paper_option_position_id != position.paper_option_position_id
        ]
        self.paper_option_positions.append(position)

    def load_paper_option_positions(self) -> tuple[PaperOptionPosition, ...]:
        return tuple(sorted(self.paper_option_positions, key=lambda item: (item.ticker, item.option_strategy_type)))

    def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self.portfolio_snapshots.append(snapshot)

    def save_intraday_signal_scan(self, scan: IntradaySignalScanRecord) -> None:
        self.intraday_signal_scans.append(scan)

    def save_intraday_signal_snapshot(self, snapshot: IntradaySignalSnapshotRecord) -> None:
        self.intraday_signal_snapshots.append(snapshot)

    def save_news_alert(self, alert: NewsAlertRecord) -> None:
        if alert.dedupe_key not in {item.dedupe_key for item in self.news_alerts}:
            self.news_alerts.append(alert)

    def save_intraday_rebalance_decision(self, decision: "IntradayRebalanceDecisionRecord") -> None:
        self.intraday_rebalance_decisions.append(decision)

    def save_daily_reflection(self, reflection: "DailyReflectionRecord") -> None:
        self.daily_reflections.append(reflection)

    def save_learning_factor(self, learning_factor: "LearningFactorRecord") -> None:
        self.learning_factors.append(learning_factor)

    def save_strategy_proposal(self, proposal: "StrategyProposalRecord") -> None:
        self.strategy_proposals.append(proposal)

    def save_strategy_evaluation_result(self, result: "StrategyEvaluationResultRecord") -> None:
        self.strategy_evaluation_results.append(result)
