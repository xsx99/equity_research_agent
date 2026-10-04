"""Post-close batch ingestion of decision-visible daily market bars."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol

from src.db.models.trading import UniverseSnapshot, UniverseSymbol
from src.research.repositories.research_repository import get_active_tickers
from src.trading.data_sources.universe import normalize_ticker
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
    fallback_used: bool
    bars_saved: int


class MarketDailyBarsBatch:
    """Fetch active-symbol daily bars from Yahoo with narrow Alpaca recovery."""

    _SUPPORT_SYMBOLS = ("SPY", "QQQ", "GLD")

    def __init__(
        self,
        *,
        active_ticker_loader: Callable[[], Iterable[str]],
        yahoo_fetcher: Callable[..., Mapping[str, Iterable[Mapping[str, Any]]]],
        alpaca_provider: Any,
        repository: MarketDailyBarsRepository,
        lookback_days: int = 400,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.active_ticker_loader = active_ticker_loader
        self.yahoo_fetcher = yahoo_fetcher
        self.alpaca_provider = alpaca_provider
        self.repository = repository
        self.lookback_days = lookback_days
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self, *, as_of: datetime | None = None) -> MarketDailyBarsBatchResult:
        decision_time = as_of or self.now()
        symbols = _normalize_symbols((*self.active_ticker_loader(), *self._SUPPORT_SYMBOLS))
        start = decision_time.date() - timedelta(days=max(self.lookback_days * 2, 10))
        end = decision_time.date() + timedelta(days=1)
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
        missing = tuple(symbol for symbol in symbols if symbol not in yahoo_bars)
        fallback_used = bool(missing)
        alpaca_error: Exception | None = None
        if missing:
            try:
                alpaca_result = self.alpaca_provider.fetch_daily_bars_for_symbols(
                    missing,
                    lookback_days=self.lookback_days,
                )
            except Exception as exc:
                alpaca_result = {}
                alpaca_error = exc
            alpaca_bars = _normalize_provider_result(
                alpaca_result,
                provider="alpaca",
                ingested_at=decision_time,
            )
        else:
            alpaca_bars = {}

        merged_bars = dict(yahoo_bars)
        merged_bars.update({symbol: bars for symbol, bars in alpaca_bars.items() if symbol in missing})
        final_missing = tuple(symbol for symbol in symbols if symbol not in merged_bars)
        rows = [bar for symbol in symbols for bar in merged_bars.get(symbol, ())]
        if rows:
            self.repository.save_market_daily_bars(rows)

        errors = [error for error in (yahoo_error, alpaca_error) if error is not None]
        status = "succeeded" if not final_missing and not errors else "degraded"
        ingestion_run = SourceIngestionRunRecord(
            source_ingestion_run_id=str(uuid.uuid4()),
            source_family="market_daily_bars",
            run_type="post_close",
            scope_json={"tickers": list(symbols)},
            provider="yahoo+alpaca",
            as_of=decision_time,
            started_at=started_at,
            completed_at=self.now(),
            status=status,
            coverage_json={
                "tickers_requested": len(symbols),
                "tickers_succeeded": len(merged_bars),
                "tickers_missing": list(final_missing),
                "fallback_used": fallback_used,
            },
            error_code=errors[0].__class__.__name__ if errors else None,
            error_message=str(errors[0]) if errors else None,
            metadata_json={
                "yahoo_tickers_succeeded": len(yahoo_bars),
                "alpaca_tickers_succeeded": len(alpaca_bars),
                "lookback_days": self.lookback_days,
            },
        )
        self.repository.record_source_ingestion_run(ingestion_run)
        return MarketDailyBarsBatchResult(
            ingestion_run=ingestion_run,
            tickers_requested=len(symbols),
            tickers_succeeded=len(merged_bars),
            tickers_missing=final_missing,
            fallback_used=fallback_used,
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
