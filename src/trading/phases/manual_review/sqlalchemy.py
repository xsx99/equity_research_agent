"""SQLAlchemy-backed manual ticker request helpers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.db.models.trading import ManualTickerRequest as ManualTickerRequestModel
from src.trading.data_sources.universe import normalize_ticker
from src.trading.phases.manual_review.requests import ACTIVE_STATUS, ManualTickerRequest, REQUEST_MODES


@dataclass(frozen=True)
class ManualReviewAuditRow:
    manual_ticker_request_id: str
    ticker: str
    reason: str
    mode: str
    status: str
    created_at: datetime
    last_evaluated_at: datetime | None
    latest_result_status: str | None
    latest_signal_snapshot_id: str | None
    latest_trading_decision_id: str | None
    latest_decision_action: str | None
    latest_risk_outcome: str | None
    latest_order_status: str | None
    latest_execution_status: str | None
    latest_execution_time: datetime | None
    execution_path_state: str
    latest_block_reason: str | None
    linkage_state: str


class SQLAlchemyManualTickerRequestService:
    """DB-backed manual request loader/updater for live preopen runs."""

    def __init__(self, session: Any, *, now: Callable[[], datetime] | None = None) -> None:
        self.session = session
        self.now = now or (lambda: datetime.now(timezone.utc))

    def load_active(self) -> tuple[ManualTickerRequest, ...]:
        rows = self.session.query(ManualTickerRequestModel).filter_by(status=ACTIVE_STATUS).all()
        requests = [self._to_record(row) for row in rows]
        return tuple(sorted(requests, key=lambda request: (request.created_at, request.ticker)))

    def create(self, ticker: str, reason: str, mode: str = "review_only") -> ManualTickerRequest:
        normalized_ticker = normalize_ticker(ticker)
        normalized_reason = str(reason or "").strip()
        if not normalized_ticker:
            raise ValueError("manual_request_ticker_required")
        if not normalized_reason:
            raise ValueError("manual_request_reason_required")
        if mode not in REQUEST_MODES:
            raise ValueError(f"unsupported_manual_request_mode:{mode}")

        now = self.now()
        for row in self._active_rows_for_ticker(normalized_ticker):
            row.status = "cancelled"
            row.cancelled_at = now

        row = ManualTickerRequestModel(
            manual_ticker_request_id=uuid.uuid4(),
            ticker=normalized_ticker,
            reason=normalized_reason,
            mode=mode,
            status=ACTIVE_STATUS,
            created_at=now,
            metadata_json={},
        )
        self.session.add(row)
        self.session.flush()
        return self._to_record(row)

    def dismiss(self, request_id: str) -> ManualTickerRequest:
        row = self._require_row(request_id)
        row.status = "dismissed"
        row.dismissed_at = self.now()
        self.session.flush()
        return self._to_record(row)

    def cancel(self, request_id: str) -> ManualTickerRequest:
        row = self._require_row(request_id)
        row.status = "cancelled"
        row.cancelled_at = self.now()
        self.session.flush()
        return self._to_record(row)

    def record_evaluation(
        self,
        request_id: str,
        *,
        result_status: str,
        signal_snapshot_id: str | None,
    ) -> ManualTickerRequest:
        row = self._require_row(request_id)
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

    def _require_row(self, request_id: str) -> ManualTickerRequestModel:
        row = self.session.query(ManualTickerRequestModel).filter_by(
            manual_ticker_request_id=_to_uuid(request_id)
        ).one_or_none()
        if row is None:
            raise KeyError(f"manual_request_not_found:{request_id}")
        return row

    def _active_rows_for_ticker(self, ticker: str) -> list[ManualTickerRequestModel]:
        rows = self.session.query(ManualTickerRequestModel).filter_by(status=ACTIVE_STATUS).all()
        return [row for row in rows if normalize_ticker(row.ticker) == ticker]


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))
