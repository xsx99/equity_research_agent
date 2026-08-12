"""Stable run identities for persisted candidate-outcome maturation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


_MATURED_CANDIDATE_MODE = "persisted_candidate_maturation"
_NAMESPACE = uuid.UUID("2dbf27f6-3d2e-41fc-b5f5-80a74f53687c")


def persisted_candidate_maturation_run_id(
    *,
    source_decision_time: datetime,
    snapshot_type: str,
    evaluation_as_of_session: datetime,
) -> str:
    """Return UUIDv5 for one exact production maturity run lineage tuple."""
    if snapshot_type not in {"pre_open", "manual", "intraday"}:
        raise ValueError(f"unsupported_snapshot_type:{snapshot_type}")
    name = "|".join(
        (
            _utc_iso(source_decision_time),
            snapshot_type,
            _utc_iso(evaluation_as_of_session),
            _MATURED_CANDIDATE_MODE,
        )
    )
    return str(uuid.uuid5(_NAMESPACE, name))


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
