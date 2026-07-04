"""Compatibility shim for intraday signal records and builders."""
from __future__ import annotations

import sys

from src.trading.phases.intraday import signals as _canonical

IntradaySignalScanRecord = _canonical.IntradaySignalScanRecord
IntradaySignalSnapshotRecord = _canonical.IntradaySignalSnapshotRecord
_carried_forward_signals = _canonical._carried_forward_signals
_clone_nested_mapping = _canonical._clone_nested_mapping
_diff_signal_families = _canonical._diff_signal_families
_merge_signal_families = _canonical._merge_signal_families
_merged_signals = _canonical._merged_signals
build_intraday_signal_snapshot = _canonical.build_intraday_signal_snapshot

__all__ = [
    "IntradaySignalScanRecord",
    "IntradaySignalSnapshotRecord",
    "_carried_forward_signals",
    "_clone_nested_mapping",
    "_diff_signal_families",
    "_merge_signal_families",
    "_merged_signals",
    "build_intraday_signal_snapshot",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
