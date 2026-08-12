"""Bounded, auditable market-data loading for candidate outcome evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class OutcomePriceRequest:
    """Persisted decision-time comparator context for one candidate checkpoint."""

    candidate_symbol: str
    snapshot_type: str
    decision_time: datetime
    horizon_end_at: datetime
    sector_theme_symbols: tuple[str, ...] = ()
    peer_symbols: tuple[str, ...] = ()
    opportunity_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutcomePriceBar:
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None


@dataclass(frozen=True)
class OutcomePriceLoadResult:
    """Batch result that preserves provider incompleteness rather than guessing."""

    requested_symbols: tuple[str, ...]
    bars_by_symbol: dict[str, tuple[OutcomePriceBar, ...]]
    missing_symbols: tuple[str, ...]
    provider_errors: dict[str, str]
    start_boundary: datetime
    end_boundary: datetime
    metadata_json: dict[str, str]


class OutcomePriceLoader:
    """Batch-load split-adjusted daily OHLC bars from persisted comparator context."""

    def __init__(self, *, provider: Any, calendar: Any | None = None) -> None:
        self.provider = provider
        if calendar is None:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar("XNYS")
        self.calendar = calendar

    def load(self, request: OutcomePriceRequest) -> OutcomePriceLoadResult:
        _require_snapshot_type(request.snapshot_type)
        requested_symbols = _symbols_for(request)
        start_boundary = _session_open(self.calendar, request.decision_time.date())
        end_boundary = _session_close(self.calendar, request.horizon_end_at.date())
        lookback_days = max(30, (end_boundary.date() - start_boundary.date()).days + 7)
        try:
            payload = self.provider.fetch_daily_bars_for_symbols(
                requested_symbols,
                lookback_days=lookback_days,
            )
        except Exception as exc:
            return OutcomePriceLoadResult(
                requested_symbols=requested_symbols,
                bars_by_symbol={},
                missing_symbols=requested_symbols,
                provider_errors={"batch": f"{type(exc).__name__}: {exc}"},
                start_boundary=start_boundary,
                end_boundary=end_boundary,
                metadata_json=_metadata(self.provider),
            )
        bars_by_symbol = {
            symbol: _normalize_bars(payload.get(symbol, ()), start_boundary.date(), end_boundary.date())
            for symbol in requested_symbols
            if _normalize_bars(payload.get(symbol, ()), start_boundary.date(), end_boundary.date())
        }
        missing_symbols = tuple(symbol for symbol in requested_symbols if symbol not in bars_by_symbol)
        return OutcomePriceLoadResult(
            requested_symbols=requested_symbols,
            bars_by_symbol=bars_by_symbol,
            missing_symbols=missing_symbols,
            provider_errors={},
            start_boundary=start_boundary,
            end_boundary=end_boundary,
            metadata_json=_metadata(self.provider),
        )


def _symbols_for(request: OutcomePriceRequest) -> tuple[str, ...]:
    values = (
        request.candidate_symbol,
        "QQQ",
        "SPY",
        *request.sector_theme_symbols,
        *request.peer_symbols,
        *request.opportunity_symbols,
    )
    return tuple(sorted({str(symbol).strip().upper() for symbol in values if str(symbol).strip()}))


def _normalize_bars(raw_bars: Iterable[dict[str, Any]], start: date, end: date) -> tuple[OutcomePriceBar, ...]:
    bars = []
    for raw in raw_bars:
        session_date = _bar_date(raw.get("date"))
        if session_date is None or not start <= session_date <= end:
            continue
        bars.append(
            OutcomePriceBar(
                session_date=session_date,
                open=_as_float(raw.get("open")),
                high=_as_float(raw.get("high")),
                low=_as_float(raw.get("low")),
                close=_as_float(raw.get("close")),
            )
        )
    return tuple(sorted(bars, key=lambda bar: bar.session_date))


def _bar_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _session_open(calendar: Any, session_date: date) -> datetime:
    return _utc(calendar.session_open(session_date))


def _session_close(calendar: Any, session_date: date) -> datetime:
    return _utc(calendar.session_close(session_date))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_snapshot_type(snapshot_type: str) -> None:
    if snapshot_type not in {"pre_open", "manual", "intraday"}:
        raise ValueError(f"unsupported_snapshot_type:{snapshot_type}")


def _metadata(provider: Any) -> dict[str, str]:
    return {
        "provider": str(getattr(provider, "provider_name", type(provider).__name__)),
        "feed": str(getattr(provider, "feed", "unknown")),
        "adjustment": "provider_split_adjusted",
        "resolution": "1Day",
    }
