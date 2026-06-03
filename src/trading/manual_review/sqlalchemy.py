"""SQLAlchemy-backed manual ticker request helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from src.db.models.trading import ManualTickerRequest as ManualTickerRequestModel
from src.trading.data_sources.universe import normalize_ticker
from src.trading.manual_review.requests import ACTIVE_STATUS, ManualTickerRequest


class SQLAlchemyManualTickerRequestService:
    """DB-backed manual request loader/updater for live preopen runs."""

    def __init__(self, session: Any, *, now: Callable[[], datetime] | None = None) -> None:
        self.session = session
        self.now = now or (lambda: datetime.now(timezone.utc))

    def load_active(self) -> tuple[ManualTickerRequest, ...]:
        rows = self.session.query(ManualTickerRequestModel).filter_by(status=ACTIVE_STATUS).all()
        requests = [self._to_record(row) for row in rows]
        return tuple(sorted(requests, key=lambda request: (request.created_at, request.ticker)))

    def record_evaluation(
        self,
        request_id: str,
        *,
        result_status: str,
        signal_snapshot_id: str | None,
    ) -> ManualTickerRequest:
        row = self.session.query(ManualTickerRequestModel).filter_by(
            manual_ticker_request_id=_to_uuid(request_id)
        ).one_or_none()
        if row is None:
            raise KeyError(f"manual_request_not_found:{request_id}")
        row.last_evaluated_at = self.now()
        row.latest_result_status = result_status
        row.latest_signal_snapshot_id = _to_uuid(signal_snapshot_id) if signal_snapshot_id is not None else None
        self.session.flush()
        return self._to_record(row)

    def _to_record(self, row: ManualTickerRequestModel) -> ManualTickerRequest:
        return ManualTickerRequest(
            request_id=str(row.manual_ticker_request_id),
            ticker=normalize_ticker(row.ticker),
            reason=row.reason,
            mode=row.mode,
            status=row.status,
            created_at=row.created_at,
            dismissed_at=row.dismissed_at,
            cancelled_at=row.cancelled_at,
            last_evaluated_at=row.last_evaluated_at,
            latest_result_status=row.latest_result_status,
            latest_signal_snapshot_id=(
                str(row.latest_signal_snapshot_id) if row.latest_signal_snapshot_id is not None else None
            ),
        )


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))
