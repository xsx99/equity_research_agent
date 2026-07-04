"""Manual ticker request state and service helpers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from src.trading.data_sources.universe import normalize_ticker

REQUEST_MODES = ("review_only", "paper_trade_eligible")
ACTIVE_STATUS = "active"


@dataclass(frozen=True)
class ManualTickerRequest:
    """User-pinned ticker that should be evaluated until dismissed."""

    request_id: str
    ticker: str
    reason: str
    mode: str
    status: str
    created_at: datetime
    dismissed_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_evaluated_at: datetime | None = None
    latest_result_status: str | None = None
    latest_signal_snapshot_id: str | None = None


class ManualTickerRequestService:
    """In-memory manual request service used by PR02 pipelines and tests."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._requests: dict[str, ManualTickerRequest] = {}

    def create(self, ticker: str, reason: str, mode: str = "review_only") -> ManualTickerRequest:
        normalized_ticker = normalize_ticker(ticker)
        normalized_reason = str(reason or "").strip()
        if not normalized_ticker:
            raise ValueError("manual_request_ticker_required")
        if not normalized_reason:
            raise ValueError("manual_request_reason_required")
        if mode not in REQUEST_MODES:
            raise ValueError(f"unsupported_manual_request_mode:{mode}")
        existing = self._active_request_for_ticker(normalized_ticker)
        if existing is not None:
            self._requests[existing.request_id] = replace(
                existing,
                status="cancelled",
                cancelled_at=self.now(),
            )
        request = ManualTickerRequest(
            request_id=str(uuid.uuid4()),
            ticker=normalized_ticker,
            reason=normalized_reason,
            mode=mode,
            status=ACTIVE_STATUS,
            created_at=self.now(),
        )
        self._requests[request.request_id] = request
        return request

    def load_active(self) -> tuple[ManualTickerRequest, ...]:
        return tuple(
            sorted(
                (request for request in self._requests.values() if request.status == ACTIVE_STATUS),
                key=lambda request: (request.created_at, request.ticker),
            )
        )

    def dismiss(self, request_id: str) -> ManualTickerRequest:
        request = self._require(request_id)
        updated = replace(request, status="dismissed", dismissed_at=self.now())
        self._requests[request_id] = updated
        return updated

    def cancel(self, request_id: str) -> ManualTickerRequest:
        request = self._require(request_id)
        updated = replace(request, status="cancelled", cancelled_at=self.now())
        self._requests[request_id] = updated
        return updated

    def record_evaluation(
        self,
        request_id: str,
        *,
        result_status: str,
        signal_snapshot_id: str | None,
    ) -> ManualTickerRequest:
        request = self._require(request_id)
        updated = replace(
            request,
            last_evaluated_at=self.now(),
            latest_result_status=result_status,
            latest_signal_snapshot_id=signal_snapshot_id,
        )
        self._requests[request_id] = updated
        return updated

    def _require(self, request_id: str) -> ManualTickerRequest:
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise KeyError(f"manual_request_not_found:{request_id}") from exc

    def _active_request_for_ticker(self, ticker: str) -> ManualTickerRequest | None:
        active = [
            request
            for request in self._requests.values()
            if request.status == ACTIVE_STATUS and request.ticker == ticker
        ]
        if not active:
            return None
        return sorted(active, key=lambda request: (request.created_at, request.request_id))[-1]
