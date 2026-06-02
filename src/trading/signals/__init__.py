"""Trading signal source contracts, builders, and snapshot helpers."""
from src.trading.signals.event_news import EventNewsSignals, build_event_news_signals
from src.trading.signals.fundamental import FundamentalSignals, build_fundamental_signals
from src.trading.signals.point_in_time import PointInTimeAudit, filter_point_in_time_records
from src.trading.signals.snapshots import SignalSnapshotResult, build_signal_snapshot, compute_relative_strength
from src.trading.signals.source_ingestion import SourceIngestionResult, SourceIngestionService
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    InMemorySignalSourceRepository,
    SourceIngestionRunRecord,
    SourceRecord,
)
from src.trading.signals.technical import TechnicalSignals, build_technical_signals

__all__ = [
    "EventNewsItemRecord",
    "EventNewsSignals",
    "FundamentalSignals",
    "FundamentalSnapshotRecord",
    "InMemorySignalSourceRepository",
    "PointInTimeAudit",
    "SignalSnapshotResult",
    "SourceIngestionResult",
    "SourceIngestionRunRecord",
    "SourceIngestionService",
    "SourceRecord",
    "TechnicalSignals",
    "build_event_news_signals",
    "build_fundamental_signals",
    "build_signal_snapshot",
    "build_technical_signals",
    "compute_relative_strength",
    "filter_point_in_time_records",
]

