"""Yahoo Finance daily OHLCV provider."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime
from math import isfinite
from typing import Any


_YAHOO_FIELDS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
    "Dividends",
    "Stock Splits",
)


def fetch_daily_bars_for_symbols(
    symbols: Iterable[str],
    start: date | datetime | str,
    end: date | datetime | str,
    batch_size: int = 40,
    *,
    download_fn: Callable[..., Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch and normalize Yahoo daily bars in controlled ticker batches.

    ``download_fn`` is a test seam. When omitted, yfinance is imported lazily so
    importing the provider does not make a network or dependency call.
    """
    normalized_symbols = _normalize_symbols(symbols)
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if not normalized_symbols:
        return {}

    downloader = download_fn or _download_from_yfinance
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}

    for offset in range(0, len(normalized_symbols), batch_size):
        chunk = normalized_symbols[offset : offset + batch_size]
        try:
            frame = downloader(**_download_kwargs(chunk, start, end))
        except Exception:
            # A failed batch is a failed batch. The caller records the missing
            # symbols and keeps any last-good database rows; do not fan out into
            # one request per ticker on the degraded path.
            continue

        for symbol in chunk:
            bars = _normalize_symbol_frame(
                frame,
                symbol,
                allow_flat_columns=len(chunk) == 1,
            )
            if bars:
                bars_by_symbol[symbol] = bars

    return bars_by_symbol


def _download_from_yfinance(**kwargs: Any) -> Any:
    import yfinance as yf

    return yf.download(**kwargs)


def _download_kwargs(
    symbols: tuple[str, ...],
    start: date | datetime | str,
    end: date | datetime | str,
) -> dict[str, Any]:
    return {
        "tickers": list(symbols),
        "start": start,
        "end": end,
        "interval": "1d",
        "group_by": "ticker",
        "auto_adjust": False,
        "actions": True,
        "threads": False,
        "progress": False,
    }


def _normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    if isinstance(symbols, str):
        symbols = (symbols,)
    return tuple(
        dict.fromkeys(
            symbol.strip().upper()
            for symbol in symbols
            if isinstance(symbol, str) and symbol.strip()
        )
    )


def _normalize_symbol_frame(
    frame: Any,
    symbol: str,
    *,
    allow_flat_columns: bool,
) -> list[dict[str, Any]]:
    columns = getattr(frame, "columns", ())
    if columns is None or len(columns) == 0:
        return []

    series_by_field = {
        field: _find_field_series(
            frame,
            columns,
            symbol,
            field,
            allow_flat_columns=allow_flat_columns,
        )
        for field in _YAHOO_FIELDS
    }
    if series_by_field["Close"] is None:
        return []

    index = getattr(frame, "index", ())
    bars: list[dict[str, Any]] = []
    for row_number, index_value in enumerate(index):
        trade_date = _to_date(index_value)
        close_raw = _to_float(_series_value(series_by_field["Close"], row_number))
        if trade_date is None or close_raw is None:
            continue

        bars.append(
            {
                "trade_date": trade_date,
                "open_raw": _to_float(_series_value(series_by_field["Open"], row_number)),
                "high_raw": _to_float(_series_value(series_by_field["High"], row_number)),
                "low_raw": _to_float(_series_value(series_by_field["Low"], row_number)),
                "close_raw": close_raw,
                "adj_close": _to_float(_series_value(series_by_field["Adj Close"], row_number)),
                "volume_raw": _to_int(_series_value(series_by_field["Volume"], row_number)),
                "dividend": _to_float(_series_value(series_by_field["Dividends"], row_number)) or 0.0,
                "stock_split": _to_float(_series_value(series_by_field["Stock Splits"], row_number)) or 0.0,
            }
        )
    return bars


def _find_field_series(
    frame: Any,
    columns: Any,
    symbol: str,
    field: str,
    *,
    allow_flat_columns: bool,
) -> Any:
    if allow_flat_columns:
        try:
            if field in columns:
                return frame[field]
        except (KeyError, TypeError):
            pass

    for column in columns:
        if not isinstance(column, tuple):
            continue
        parts = {str(part) for part in column}
        if symbol in parts and field in parts:
            try:
                return frame[column]
            except (KeyError, TypeError):
                return None
    return None


def _series_value(series: Any, row_number: int) -> Any:
    if series is None:
        return None
    try:
        return series.iloc[row_number]
    except (AttributeError, IndexError, KeyError, TypeError):
        try:
            return series[row_number]
        except (IndexError, KeyError, TypeError):
            return None


def _to_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (ImportError, TypeError, ValueError):
        return False


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    date_method = getattr(value, "date", None)
    if callable(date_method):
        try:
            parsed = date_method()
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, date):
            return parsed
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None
