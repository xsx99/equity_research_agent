"""Compatibility shim for the signal snapshot pipeline."""
from __future__ import annotations

from src.trading.signals.pipeline import (
    SignalPipeline,
    SignalSnapshotWriter,
    SignalSourceRepositoryProtocol,
    SourceIngestionServiceProtocol,
    _insider_data_covered,
    _manual_requests_by_ticker,
)

__all__ = [
    "SignalPipeline",
    "SignalSnapshotWriter",
    "SignalSourceRepositoryProtocol",
    "SourceIngestionServiceProtocol",
    "_insider_data_covered",
    "_manual_requests_by_ticker",
]
