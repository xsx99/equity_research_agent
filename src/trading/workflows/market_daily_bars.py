"""Post-close batch ingestion of decision-visible daily market bars."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol

from src.db.models.trading import UniverseSnapshot, UniverseSymbol
from src.research.repositories.research_repository import get_active_tickers
from src.trading.data_sources.universe import normalize_ticker
from src.trading.ranking.calendar import RankingSessionCalendar
from src.trading.signals.sources import MarketDailyBarRecord, SourceIngestionRunRecord


class MarketDailyBarsRepository(Protocol):
    def save_market_daily_bars(self, bars: Iterable[MarketDailyBarRecord]) -> None:
        """Upsert successfully fetched bars without deleting prior rows."""

    def record_source_ingestion_run(self, run: SourceIngestionRunRecord) -> None:
        """Persist ingestion coverage and provider status."""


@dataclass(frozen=True)
class MarketDailyBarsBatchResult:
    ingestion_run: SourceIngestionRunRecord
    tickers_requested: int
    tickers_succeeded: int
    tickers_missing: tuple[str, ...]
    bars_saved: int


class MarketDailyBarsBatch:
    """Fetch active-symbol daily bars from Yahoo in an incremental batch."""

    _SUPPORT_SYMBOLS = ("SPY", "QQQ", "GLD")

    def __init__(
        self,
        *,
        active_ticker_loader: Callable[[], Iterable[str]],
        yahoo_fetcher: Callable[..., Mapping[str, Iterable[Mapping[str, Any]]]],
        repository: MarketDailyBarsRepository,
        lookback_days: int = 400,
        recent_window_days: int = 10,
        session_calendar: RankingSessionCalendar | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.active_ticker_loader = active_ticker_loader
        self.yahoo_fetcher = yahoo_fetcher
        self.repository = repository
        self.lookback_days = lookback_days
        self.recent_window_days = recent_window_days
        self.session_calendar = session_calendar or RankingSessionCalendar()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        as_of: datetime | None = None,
        backfill: bool = False,
    ) -> MarketDailyBarsBatchResult:
        decision_time = as_of or self.now()
        symbols = _normalize_symbols((*self.active_ticker_loader(), *self._SUPPORT_SYMBOLS))
        expected_trade_date = self.session_calendar.latest_completed_session(
            decision_time
        ).session_date
        window_days = self.lookback_days if backfill else self.recent_window_days
        start = expected_trade_date - timedelta(days=max(window_days - 1, 0))
        end = expected_trade_date + timedelta(days=1)
        started_at = self.now()
        yahoo_error: Exception | None = None

        try:
            yahoo_result = self.yahoo_fetcher(symbols, start, end)
        except Exception as exc:
            yahoo_result = {}
            yahoo_error = exc
        yahoo_bars = _normalize_provider_result(
            yahoo_result,
            provider="yahoo",
            ingested_at=decision_time,
        )
        covered_symbols: set[str] = set()
        for symbol, bars in yahoo_bars.items():
            latest_trade_date = max(
                (bar.trade_date for bar in bars),
                default=None,
            )
            if latest_trade_date is not None and latest_trade_date >= expected_trade_date:
                covered_symbols.add(symbol)
        final_missing = tuple(symbol for symbol in symbols if symbol not in covered_symbols)
        rows = [bar for symbol in symbols for bar in yahoo_bars.get(symbol, ())]
        if rows:
            self.repository.save_market_daily_bars(rows)

        errors = [error for error in (yahoo_error,) if error is not None]
        status = "succeeded" if not final_missing and not errors else "degraded"
        ingestion_run = SourceIngestionRunRecord(
            source_ingestion_run_id=str(uuid.uuid4()),
            source_family="market_daily_bars",
            run_type="post_close",
            scope_json={"tickers": list(symbols)},
            provider="yahoo",
            as_of=decision_time,
            started_at=started_at,
            completed_at=self.now(),
            status=status,
            coverage_json={
                "tickers_requested": len(symbols),
                "tickers_succeeded": len(covered_symbols),
                "tickers_missing": list(final_missing),
            },
            error_code=errors[0].__class__.__name__ if errors else None,
            error_message=str(errors[0]) if errors else None,
            metadata_json={
                "yahoo_tickers_succeeded": len(yahoo_bars),
                "lookback_days": self.lookback_days,
                "fetch_window_days": window_days,
                "backfill": backfill,
            },
        )
        self.repository.record_source_ingestion_run(ingestion_run)
        return MarketDailyBarsBatchResult(
            ingestion_run=ingestion_run,
            tickers_requested=len(symbols),
            tickers_succeeded=len(covered_symbols),
            tickers_missing=final_missing,
            bars_saved=len(rows),
        )


def load_active_daily_bar_tickers(session: Any) -> tuple[str, ...]:
    """Return included universe symbols plus active watchlist symbols."""
    symbols: list[str] = []
    snapshots = [
        row
        for row in session.query(UniverseSnapshot).all()
        if row.status == "succeeded"
    ]
    if snapshots:
        snapshot = max(
            snapshots,
            key=lambda row: (
                row.snapshot_date,
                row.completed_at or row.started_at,
            ),
        )
        symbols.extend(
            row.symbol
            for row in session.query(UniverseSymbol).filter(
                UniverseSymbol.universe_snapshot_id == snapshot.universe_snapshot_id,
                UniverseSymbol.status == "included",
            ).all()
        )
    symbols.extend(get_active_tickers(session))
    return _normalize_symbols(symbols)


def _normalize_provider_result(
    result: Any,
    *,
    provider: str,
    ingested_at: datetime,
) -> dict[str, tuple[MarketDailyBarRecord, ...]]:
    if not isinstance(result, Mapping):
        return {}
    normalized: dict[str, tuple[MarketDailyBarRecord, ...]] = {}
    for raw_symbol, values in result.items():
        if not isinstance(raw_symbol, str) or not isinstance(values, Iterable):
            continue
        symbol = normalize_ticker(raw_symbol)
        rows: list[MarketDailyBarRecord] = []
        for value in values:
            if not isinstance(value, Mapping):
                continue
            row = _bar_from_mapping(
                symbol,
                value,
                provider=provider,
                ingested_at=ingested_at,
            )
            if row is not None:
                rows.append(row)
        if rows:
            normalized[symbol] = tuple(rows)
    return normalized


def _bar_from_mapping(
    symbol: str,
    value: Mapping[str, Any],
    *,
    provider: str,
    ingested_at: datetime,
) -> MarketDailyBarRecord | None:
    trade_date = value.get("trade_date", value.get("date"))
    if isinstance(trade_date, datetime):
        trade_date = trade_date.date()
    if not isinstance(trade_date, date):
        return None
    close_raw = value.get("close_raw", value.get("close"))
    if not isinstance(close_raw, (int, float)):
        return None
    return MarketDailyBarRecord(
        ticker=symbol,
        trade_date=trade_date,
        open_raw=_number(value.get("open_raw", value.get("open"))),
        high_raw=_number(value.get("high_raw", value.get("high"))),
        low_raw=_number(value.get("low_raw", value.get("low"))),
        close_raw=float(close_raw),
        adj_close=_number(value.get("adj_close")) or float(close_raw),
        volume_raw=_integer(value.get("volume_raw", value.get("volume"))),
        dividend=_number(value.get("dividend")) or 0.0,
        stock_split=_number(value.get("stock_split")) or 0.0,
        provider=provider,
        ingested_at=ingested_at,
        available_for_decision_at=ingested_at,
    )


def _normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            normalize_ticker(symbol)
            for symbol in symbols
            if isinstance(symbol, str) and symbol.strip()
        )
    )


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _integer(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
