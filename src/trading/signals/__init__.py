"""Trading signal source contracts, builders, and snapshot helpers."""
from src.trading.signals.event_news import EventNewsSignals, build_event_news_signals
from src.trading.signals.fundamental import FundamentalSignals, build_fundamental_signals
from src.trading.signals.insider import InsiderSignals, build_insider_signals
from src.trading.signals.point_in_time import PointInTimeAudit, filter_point_in_time_records
from src.trading.signals.social_macro import SocialMacroSignals, build_social_macro_signals
from src.trading.signals.snapshots import SignalSnapshotResult, build_signal_snapshot, compute_relative_strength
from src.trading.signals.source_ingestion import SourceIngestionResult, SourceIngestionService
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    InMemorySignalSourceRepository,
    SocialMacroItemRecord,
    SourceIngestionRunRecord,
    SourceRecord,
    insider_trade_available_for_decision_at,
    next_market_open_after_filing_date,
    source_record_from_insider_trade,
    source_record_from_social_macro_item,
)
from src.trading.signals.technical import TechnicalSignals, build_technical_signals

__all__ = [
    "EventNewsItemRecord",
    "EventNewsSignals",
    "FundamentalSignals",
    "FundamentalSnapshotRecord",
    "InMemorySignalSourceRepository",
    "InsiderSignals",
    "PointInTimeAudit",
    "SocialMacroSignals",
    "SocialMacroItemRecord",
    "SignalSnapshotResult",
    "SourceIngestionResult",
    "SourceIngestionRunRecord",
    "SourceIngestionService",
    "SourceRecord",
    "TechnicalSignals",
    "build_event_news_signals",
    "build_fundamental_signals",
    "build_insider_signals",
    "build_signal_snapshot",
    "build_social_macro_signals",
    "build_technical_signals",
    "compute_relative_strength",
    "filter_point_in_time_records",
    "insider_trade_available_for_decision_at",
    "next_market_open_after_filing_date",
    "source_record_from_insider_trade",
    "source_record_from_social_macro_item",
]
