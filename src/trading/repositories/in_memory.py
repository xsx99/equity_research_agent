"""Small in-memory repositories for PR02 orchestration tests."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroReadthroughEventRecord, MacroSnapshotRecord
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
    PortfolioRiskIntentRecord,
    PortfolioRiskSnapshotRecord,
    PositionSizingDecisionRecord,
    RiskDecisionRecord,
    RiskFactorExposureRecord,
)
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SocialMacroItemRecord,
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
        self.social_macro_items: list[SocialMacroItemRecord] = []
        self.macro_snapshots: list[MacroSnapshotRecord] = []
        self.macro_readthrough_events: list[MacroReadthroughEventRecord] = []
        self.calendar_events: list[CalendarEventRecord] = []
        self.portfolio_event_risk_assessments: list[PortfolioEventRiskAssessmentRecord] = []
        self.strategy_definitions: list[StrategyDefinitionRecord] = []
        self.strategy_runs: list[StrategyRunRecord] = []
        self.candidate_scores: list[CandidateScoreRecord] = []
        self.watch_candidates: list[WatchCandidateRecord] = []
        self.trade_classifications: list[TradeClassificationRecord] = []
        self.historical_replay_runs: list[HistoricalReplayRunRecord] = []
        self.candidate_outcome_evaluations: list[CandidateOutcomeEvaluationRecord] = []
        self.position_sizing_decisions: list[PositionSizingDecisionRecord] = []
        self.portfolio_risk_snapshots: list[PortfolioRiskSnapshotRecord] = []
        self.portfolio_risk_intents: list[PortfolioRiskIntentRecord] = []
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

    def save_social_macro_item(self, item: SocialMacroItemRecord) -> None:
        self.social_macro_items.append(item)

    def save_macro_snapshot(self, snapshot: MacroSnapshotRecord) -> None:
        self.macro_snapshots = [
            item
            for item in self.macro_snapshots
            if not (
                item.trade_date == snapshot.trade_date
                and item.snapshot_time == snapshot.snapshot_time
                and item.source_set_key == snapshot.source_set_key
            )
        ]
        self.macro_snapshots.append(snapshot)

    def load_latest_macro_snapshot(
        self,
        *,
        trade_date: date,
        decision_time: datetime | None = None,
    ) -> MacroSnapshotRecord | None:
        candidates = [
            item
            for item in self.macro_snapshots
            if item.trade_date == trade_date
            and (decision_time is None or item.snapshot_time <= decision_time)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.snapshot_time)

    def save_calendar_events(
        self,
        events: list[CalendarEventRecord] | tuple[CalendarEventRecord, ...],
    ) -> None:
        for event in events:
            self.calendar_events = [item for item in self.calendar_events if item.event_key != event.event_key]
            self.calendar_events.append(event)

    def load_calendar_events(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
    ) -> tuple[CalendarEventRecord, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        events = [
            item
            for item in self.calendar_events
            if item.available_for_decision_at <= decision_time
            and (symbol is None or item.ticker in {None, symbol})
        ]
        events.sort(key=lambda item: (item.event_time, item.event_key))
        return tuple(events)

    def save_portfolio_event_risk_assessments(
        self,
        assessments: list[PortfolioEventRiskAssessmentRecord] | tuple[PortfolioEventRiskAssessmentRecord, ...],
    ) -> None:
        for assessment in assessments:
            key = _portfolio_event_risk_assessment_key(assessment)
            self.portfolio_event_risk_assessments = [
                item
                for item in self.portfolio_event_risk_assessments
                if _portfolio_event_risk_assessment_key(item) != key
            ]
            self.portfolio_event_risk_assessments.append(assessment)

    def load_portfolio_event_risk_assessments(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
    ) -> tuple[PortfolioEventRiskAssessmentRecord, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        assessments = [
            item
            for item in self.portfolio_event_risk_assessments
            if (item.available_for_decision_at is None or item.available_for_decision_at <= decision_time)
            and (symbol is None or item.ticker == symbol)
        ]
        assessments.sort(
            key=lambda item: (
                item.available_for_decision_at or datetime.min,
                item.portfolio_event_risk_assessment_id or "",
            )
        )
        return tuple(assessments)

    def load_decision_available_risk_macro_context(
        self,
        *,
        trade_date: date,
        decision_time: datetime,
        ticker: str | None = None,
    ) -> dict[str, object]:
        return {
            "macro_snapshot": self.load_latest_macro_snapshot(
                trade_date=trade_date,
                decision_time=decision_time,
            ),
            "calendar_events": self.load_calendar_events(
                decision_time=decision_time,
                ticker=ticker,
            ),
            "portfolio_event_risk_assessments": self.load_portfolio_event_risk_assessments(
                decision_time=decision_time,
                ticker=ticker,
            ),
        }

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

    def save_portfolio_risk_intent(self, intent: PortfolioRiskIntentRecord) -> None:
        self.portfolio_risk_intents = [
            item for item in self.portfolio_risk_intents if item.portfolio_risk_intent_id != intent.portfolio_risk_intent_id
        ]
        self.portfolio_risk_intents.append(intent)

    def load_portfolio_risk_intents(self, *, trade_date: date) -> tuple[PortfolioRiskIntentRecord, ...]:
        return tuple(
            intent
            for intent in sorted(self.portfolio_risk_intents, key=lambda item: item.decision_time)
            if intent.decision_time.date() == trade_date
        )

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


def _portfolio_event_risk_assessment_key(assessment: PortfolioEventRiskAssessmentRecord) -> str:
    if assessment.portfolio_event_risk_assessment_id:
        return assessment.portfolio_event_risk_assessment_id
    return "|".join(
        (
            assessment.calendar_event_id or "synthetic",
            assessment.portfolio_risk_snapshot_id or "no_snapshot",
            assessment.ticker,
            assessment.risk_source,
            assessment.available_for_decision_at.isoformat() if assessment.available_for_decision_at else "na",
        )
    )
