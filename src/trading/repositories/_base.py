"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from src.db.models.trading import (
    CalendarEvent,
    CandidateScore,
    CandidateOutcomeEvaluation,
    DailyReflection,
    EventNewsItem,
    IntradayRebalanceDecision,
    IntradaySignalScan,
    IntradaySignalSnapshot,
    LearningFactor,
    MacroSnapshot,
    NewsAlert,
    ManualTickerRequest,
    OptionRiskSnapshot,
    OptionStrategyDecision,
    OptionStrategyLeg,
    PaperExecution,
    PaperOptionExecution,
    PaperOptionOrder,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PaperPosition,
    PortfolioEventRiskAssessment,
    PortfolioRiskIntent,
    PortfolioRiskSnapshot,
    PortfolioSnapshot as PortfolioSnapshotModel,
    PositionSizingDecision,
    RiskDecision,
    RiskFactorExposure,
    RiskHedgeDecision,
    SignalSnapshot,
    StrategyDefinition,
    StrategyRun,
    StrategyEvaluationResult,
    StrategyProposal,
    TradeClassification,
    TradingDecision,
    TradingRuntimeRun,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
    WatchCandidate,
)
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.data_sources.universe import UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.brokers.paper_option import (
    PaperOptionExecutionRecord,
    PaperOptionOrderRecord,
    PaperOptionPosition,
)
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.intraday.news_alerts import NewsAlertRecord
from src.trading.manual_review.sqlalchemy import ManualReviewAuditRow
from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.lookahead import HedgeActionRecord, PortfolioRiskIntentRecord, PositionRiskActionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyRunRecord
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.strategies.selector import WatchCandidateRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord
from src.trading.repositories._base_common import (
    _datetime_value,
    _decimal_or_none,
    _decimal_to_float,
    _format_option_contract_symbol,
    _legacy_option_client_order_id,
    _latest_row_sort_key,
    _string_or_none,
    _to_uuid,
    _to_uuid_or_none,
)
from src.trading.repositories._base_manual_review import (
    _intraday_context_metadata,
    _manual_request_payload,
    _manual_review_actionable_decision,
    _manual_review_execution_path_state,
    _manual_review_linkage_state,
)
from src.trading.repositories._base_payloads import (
    _candidate_outcome_payload,
    _candidate_score_payload,
    _hedge_action_payload,
    _hedge_effectiveness_payload,
    _intraday_rebalance_payload,
    _news_alert_payload,
    _option_risk_snapshot_payload,
    _paper_execution_payload,
    _paper_option_decision_payload,
    _paper_option_position_payload,
    _paper_order_payload,
    _portfolio_outcome_payload,
    _portfolio_risk_snapshot_payload,
    _portfolio_snapshot_payload,
    _position_risk_action_payload,
    _rejected_candidate_payload,
    _risk_factor_exposure_payload,
    _risk_hedge_overlay_payload,
    _trading_decision_payload,
)
from src.trading.repositories._base_records import (
    _calendar_event_record,
    _candidate_outcome_record,
    _daily_reflection_record,
    _hedge_action_record,
    _latest_portfolio_risk_snapshot_id,
    _learning_factor_record,
    _macro_snapshot_record,
    _portfolio_event_risk_assessment_record,
    _portfolio_event_risk_assessment_storage_key,
    _portfolio_risk_intent_record,
    _position_risk_action_record,
)


class _RepositoryBase:
    def __init__(self, session: Any) -> None:
        self.session = session

    def _require_universe_filter_config_row(self, config: UniverseFilterConfigRecord) -> UniverseFilterConfig:
        row = self.session.query(UniverseFilterConfig).filter_by(
            profile_name=config.profile_name,
            version=int(config.version),
        ).one_or_none()
        if row is None:
            raise RuntimeError(
                f"universe_filter_config_not_found:{config.profile_name}:v{config.version}"
            )
        return row

    def _to_event_news_item_record(self, row: Any) -> EventNewsItemRecord:
        return EventNewsItemRecord(
            event_news_item_id=str(row.event_news_item_id),
            ticker=row.ticker,
            source_ticker=row.source_ticker,
            event_type=row.event_type,
            direction=row.direction,
            sentiment=row.sentiment,
            importance=row.importance,
            headline=row.headline,
            summary=row.summary,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            dedupe_key=row.dedupe_key,
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            metadata_json=dict(row.metadata_json or {}),
        )


__all__ = [
    "_RepositoryBase",
    "_calendar_event_record",
    "_candidate_outcome_payload",
    "_candidate_outcome_record",
    "_candidate_score_payload",
    "_daily_reflection_record",
    "_datetime_value",
    "_decimal_or_none",
    "_decimal_to_float",
    "_format_option_contract_symbol",
    "_hedge_action_payload",
    "_hedge_action_record",
    "_hedge_effectiveness_payload",
    "_intraday_context_metadata",
    "_intraday_rebalance_payload",
    "_latest_portfolio_risk_snapshot_id",
    "_latest_row_sort_key",
    "_learning_factor_record",
    "_legacy_option_client_order_id",
    "_macro_snapshot_record",
    "_manual_request_payload",
    "_manual_review_actionable_decision",
    "_manual_review_execution_path_state",
    "_manual_review_linkage_state",
    "_news_alert_payload",
    "_option_risk_snapshot_payload",
    "_paper_execution_payload",
    "_paper_option_decision_payload",
    "_paper_option_position_payload",
    "_paper_order_payload",
    "_portfolio_event_risk_assessment_record",
    "_portfolio_event_risk_assessment_storage_key",
    "_portfolio_outcome_payload",
    "_portfolio_risk_intent_record",
    "_portfolio_risk_snapshot_payload",
    "_portfolio_snapshot_payload",
    "_position_risk_action_payload",
    "_position_risk_action_record",
    "_rejected_candidate_payload",
    "_risk_factor_exposure_payload",
    "_risk_hedge_overlay_payload",
    "_string_or_none",
    "_to_uuid",
    "_to_uuid_or_none",
    "_trading_decision_payload",
]
