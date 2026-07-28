"""Bounded, decision-time filtered market-data loading for ranking."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

from src.trading.data_sources.provider_resilience import (
    InMemoryProviderRequestRecorder,
    ProviderRequestRecorder,
    ProviderRequestRunRecord,
)
from src.trading.ranking.calendar import RankingSession, RankingSessionCalendar
from src.trading.ranking.records import AdjustedDailyBar


@dataclass(frozen=True)
class RankingInputBatch:
    """Auditable market-data inputs loaded before pure ranking calculations."""

    requested_tickers: tuple[str, ...]
    bars_by_ticker: dict[str, tuple[AdjustedDailyBar, ...]]
    benchmark_bars: tuple[AdjustedDailyBar, ...]
    cutoff_session: RankingSession
    chunk_errors: dict[str, str]


class RankingInputLoader:
    """Load full-universe daily bars only through batched provider calls."""

    def __init__(
        self,
        *,
        provider: Any,
        calendar: RankingSessionCalendar,
        recorder: ProviderRequestRecorder | None = None,
        chunk_size: int = 200,
        benchmark_ticker: str = "SPY",
        lookback_sessions: int = 65,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self.provider = provider
        self.calendar = calendar
        self.recorder = recorder or InMemoryProviderRequestRecorder()
        self.chunk_size = chunk_size
        self.benchmark_ticker = benchmark_ticker.strip().upper()
        self.lookback_sessions = lookback_sessions

    def load(self, tickers: Iterable[str], *, decision_time: datetime) -> RankingInputBatch:
        cutoff_session = self.calendar.latest_completed_session(decision_time)
        requested = tuple(sorted({_ticker(ticker) for ticker in tickers if _ticker(ticker)}))
        provider_symbols = tuple(dict.fromkeys((*requested, self.benchmark_ticker)))
        bars_by_symbol: dict[str, tuple[AdjustedDailyBar, ...]] = {}
        errors: dict[str, str] = {}
        for chunk in _chunks(provider_symbols, self.chunk_size):
            started_at = _utc_now()
            scope = ",".join(chunk)
            try:
                payload = self.provider.fetch_daily_bars_for_symbols(
                    chunk,
                    lookback_days=self.lookback_sessions,
                )
                for ticker in chunk:
                    bars_by_symbol[ticker] = _normalize_bars(
                        ticker=ticker,
                        raw_bars=(payload or {}).get(ticker, ()),
                        cutoff_session=cutoff_session,
                        max_sessions=self.lookback_sessions,
                    )
                self._record(scope, started_at, "succeeded", None)
            except Exception as exc:  # partial-provider failures remain replayable metadata
                errors[scope] = f"{type(exc).__name__}: {exc}"
                self._record(scope, started_at, "failed", errors[scope])
        return RankingInputBatch(
            requested_tickers=requested,
            bars_by_ticker={
                ticker: bars_by_symbol[ticker]
                for ticker in requested
                if bars_by_symbol.get(ticker)
            },
            benchmark_bars=bars_by_symbol.get(self.benchmark_ticker, ()),
            cutoff_session=cutoff_session,
            chunk_errors=errors,
        )

    def _record(self, scope: str, started_at: datetime, status: str, error_code: str | None) -> None:
        completed_at = _utc_now()
        self.recorder.record(
            ProviderRequestRunRecord(
                provider=str(getattr(self.provider, "provider_name", type(self.provider).__name__)),
                endpoint="daily_bars_batch",
                source_family="market_data",
                scope=scope,
                cache_status="miss",
                request_count=1,
                budget_remaining=0,
                retry_count=0,
                backoff_ms=0,
                latency_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
                status=status,
                error_code=error_code,
                circuit_state="closed",
                degraded_mode=status != "succeeded",
                started_at=started_at,
                completed_at=completed_at,
            )
        )


def _normalize_bars(
    *,
    ticker: str,
    raw_bars: Iterable[dict[str, Any]],
    cutoff_session: RankingSession,
    max_sessions: int,
) -> tuple[AdjustedDailyBar, ...]:
    normalized: list[AdjustedDailyBar] = []
    for raw in raw_bars:
        session_date = _bar_date(raw.get("date"))
        if session_date is None or session_date > cutoff_session.session_date:
            continue
        normalized.append(
            AdjustedDailyBar(
                session_date=session_date,
                close=_float_or_none(raw.get("close")),
                volume=_float_or_none(raw.get("volume")),
                available_for_decision_at=cutoff_session.scheduled_close,
                is_adjusted=True,
                split_adjusted=True,
                adjustment_source="provider_split_adjusted",
                source_refs=(f"market:{ticker}:{session_date.isoformat()}",),
            )
        )
    return tuple(sorted(normalized, key=lambda bar: bar.session_date)[-max_sessions:])


def _bar_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ticker(value: str) -> str:
    return str(value).strip().upper()


def _chunks(values: tuple[str, ...], size: int) -> Iterable[tuple[str, ...]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
