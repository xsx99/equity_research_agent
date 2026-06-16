"""Intraday signal refresh records and delta builders for PR8."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.trading.signals import SignalSnapshotResult


@dataclass(frozen=True)
class IntradaySignalScanRecord:
    """Metadata for one hourly intraday refresh run."""

    intraday_signal_scan_id: str
    started_at: datetime
    completed_at: datetime | None
    decision_time: datetime
    status: str
    scope_json: dict[str, Any]
    coverage_json: dict[str, Any]
    error_message: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntradaySignalSnapshotRecord:
    """Per-ticker intraday snapshot with explicit refresh/carry-forward splits."""

    intraday_signal_snapshot_id: str
    intraday_signal_scan_id: str
    ticker: str
    decision_time: datetime
    baseline_signal_snapshot_id: str
    previous_intraday_snapshot_id: str | None
    refreshed_signals_json: dict[str, dict[str, Any]]
    carried_forward_signals_json: dict[str, dict[str, Any]]
    delta_vs_baseline_json: dict[str, dict[str, Any]]
    delta_vs_previous_json: dict[str, dict[str, Any]]
    source_freshness_json: dict[str, str]
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_intraday_signal_snapshot(
    *,
    intraday_signal_scan_id: str,
    ticker: str,
    decision_time: datetime,
    baseline_snapshot: SignalSnapshotResult,
    previous_intraday_snapshot: IntradaySignalSnapshotRecord | None,
    refreshed_signals_json: dict[str, dict[str, Any]],
    source_freshness_json: dict[str, str],
) -> IntradaySignalSnapshotRecord:
    """Build a PR8 intraday snapshot with explicit deltas and carried-forward fields."""
    baseline_signals = baseline_snapshot.signal_json
    previous_signals = _merged_signals(previous_intraday_snapshot) if previous_intraday_snapshot is not None else baseline_signals
    carried_forward = _carried_forward_signals(
        baseline_signals=baseline_signals,
        refreshed_signals_json=refreshed_signals_json,
    )
    merged_current = _merge_signal_families(carried_forward, refreshed_signals_json)
    return IntradaySignalSnapshotRecord(
        intraday_signal_snapshot_id=str(uuid.uuid4()),
        intraday_signal_scan_id=intraday_signal_scan_id,
        ticker=ticker.strip().upper(),
        decision_time=decision_time,
        baseline_signal_snapshot_id=baseline_snapshot.signal_snapshot_id,
        previous_intraday_snapshot_id=(
            previous_intraday_snapshot.intraday_signal_snapshot_id
            if previous_intraday_snapshot is not None
            else None
        ),
        refreshed_signals_json=_clone_nested_mapping(refreshed_signals_json),
        carried_forward_signals_json=carried_forward,
        delta_vs_baseline_json=_diff_signal_families(merged_current, baseline_signals),
        delta_vs_previous_json=_diff_signal_families(merged_current, previous_signals),
        source_freshness_json=dict(source_freshness_json),
        metadata_json={},
        created_at=decision_time,
    )


def _merged_signals(snapshot: IntradaySignalSnapshotRecord) -> dict[str, dict[str, Any]]:
    return _merge_signal_families(snapshot.carried_forward_signals_json, snapshot.refreshed_signals_json)


def _carried_forward_signals(
    *,
    baseline_signals: dict[str, dict[str, Any]],
    refreshed_signals_json: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    carried_forward: dict[str, dict[str, Any]] = {}
    for family, values in baseline_signals.items():
        if family in refreshed_signals_json:
            continue
        carried_forward[family] = dict(values)
    return carried_forward


def _merge_signal_families(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = _clone_nested_mapping(left)
    for family, values in right.items():
        merged.setdefault(family, {})
        merged[family].update(values)
    return merged


def _diff_signal_families(
    current: dict[str, dict[str, Any]],
    prior: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    deltas: dict[str, dict[str, Any]] = {}
    families = set(current) | set(prior)
    for family in families:
        family_delta: dict[str, Any] = {}
        current_values = current.get(family, {})
        prior_values = prior.get(family, {})
        for key in set(current_values) | set(prior_values):
            current_value = current_values.get(key)
            prior_value = prior_values.get(key)
            if current_value == prior_value:
                continue
            if (
                isinstance(current_value, (int, float))
                and isinstance(prior_value, (int, float))
                and not isinstance(current_value, bool)
                and not isinstance(prior_value, bool)
            ):
                family_delta[key] = current_value - prior_value
            else:
                family_delta[key] = current_value
        if family_delta:
            deltas[family] = family_delta
    return deltas


def _clone_nested_mapping(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {family: dict(values) for family, values in payload.items()}
