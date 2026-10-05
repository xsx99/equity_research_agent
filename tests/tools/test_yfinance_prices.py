from __future__ import annotations

from datetime import date

import pandas as pd

from src.providers.market_data.yfinance_prices import fetch_daily_bars_for_symbols


def _download_stub(frame: pd.DataFrame, calls: list[dict[str, object]]):
    def _download(**kwargs: object) -> pd.DataFrame:
        calls.append(kwargs)
        return frame

    return _download


def _multi_index_frame(
    payload: dict[str, dict[str, list[object]]],
    index: list[str] | None = None,
) -> pd.DataFrame:
    fields = [
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
        "Dividends",
        "Stock Splits",
    ]
    columns = pd.MultiIndex.from_product([payload, fields])
    rows = index or ["2026-09-28"]
    values = [payload[ticker][field] for ticker in payload for field in fields]
    return pd.DataFrame(dict(zip(columns, values)), index=pd.to_datetime(rows))


def test_fetch_daily_bars_supports_single_symbol_dataframe_and_passes_download_options():
    calls: list[dict[str, object]] = []
    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [104.0],
            "Adj Close": [103.5],
            "Volume": [1_000_000.0],
            "Dividends": [0.0],
            "Stock Splits": [0.0],
        },
        index=pd.to_datetime(["2026-09-28"]),
    )

    result = fetch_daily_bars_for_symbols(
        ["aapl"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, calls),
    )

    assert calls == [
        {
            "tickers": ["AAPL"],
            "start": "2026-09-01",
            "end": "2026-10-01",
            "interval": "1d",
            "group_by": "ticker",
            "auto_adjust": False,
            "actions": True,
            "threads": False,
            "progress": False,
        }
    ]
    assert result == {
        "AAPL": [
            {
                "trade_date": date(2026, 9, 28),
                "open_raw": 100.0,
                "high_raw": 105.0,
                "low_raw": 99.0,
                "close_raw": 104.0,
                "adj_close": 103.5,
                "volume_raw": 1_000_000,
                "dividend": 0.0,
                "stock_split": 0.0,
            }
        ]
    }


def test_fetch_daily_bars_supports_multiple_symbols_in_multiindex_dataframe():
    calls: list[dict[str, object]] = []
    frame = _multi_index_frame(
        {
            "AAPL": {
                "Open": [100.0],
                "High": [105.0],
                "Low": [99.0],
                "Close": [104.0],
                "Adj Close": [103.5],
                "Volume": [1_000_000.0],
                "Dividends": [0.0],
                "Stock Splits": [0.0],
            },
            "MSFT": {
                "Open": [200.0],
                "High": [205.0],
                "Low": [199.0],
                "Close": [204.0],
                "Adj Close": [203.5],
                "Volume": [2_000_000.0],
                "Dividends": [0.0],
                "Stock Splits": [0.0],
            },
        }
    )

    result = fetch_daily_bars_for_symbols(
        ["aapl", "msft"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, calls),
    )

    assert set(result) == {"AAPL", "MSFT"}
    assert result["AAPL"][0]["close_raw"] == 104.0
    assert result["MSFT"][0]["close_raw"] == 204.0


def test_fetch_daily_bars_preserves_raw_close_separately_from_adjusted_close():
    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [104.0],
            "Adj Close": [98.0],
            "Volume": [1_000_000.0],
        },
        index=pd.to_datetime(["2026-09-28"]),
    )

    result = fetch_daily_bars_for_symbols(
        ["AAPL"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, []),
    )

    assert result["AAPL"][0]["close_raw"] == 104.0
    assert result["AAPL"][0]["adj_close"] == 98.0


def test_fetch_daily_bars_maps_dividends_and_stock_splits():
    frame = _multi_index_frame(
        {
            "AAPL": {
                "Open": [100.0],
                "High": [105.0],
                "Low": [99.0],
                "Close": [104.0],
                "Adj Close": [103.5],
                "Volume": [1_000_000.0],
                "Dividends": [0.25],
                "Stock Splits": [2.0],
            }
        }
    )

    result = fetch_daily_bars_for_symbols(
        ["AAPL"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, []),
    )

    assert result["AAPL"][0]["dividend"] == 0.25
    assert result["AAPL"][0]["stock_split"] == 2.0


def test_fetch_daily_bars_skips_all_nan_rows_and_normalizes_optional_nan_values():
    frame = pd.DataFrame(
        {
            "Open": [100.0, float("nan"), float("nan")],
            "High": [105.0, float("nan"), 205.0],
            "Low": [99.0, float("nan"), 199.0],
            "Close": [104.0, float("nan"), 204.0],
            "Adj Close": [103.5, float("nan"), 203.5],
            "Volume": [1_000_000.0, float("nan"), float("nan")],
            "Dividends": [0.0, float("nan"), float("nan")],
            "Stock Splits": [0.0, float("nan"), float("nan")],
        },
        index=pd.to_datetime(["2026-09-26", "2026-09-27", "2026-09-28"]),
    )

    result = fetch_daily_bars_for_symbols(
        ["AAPL"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, []),
    )

    assert [bar["trade_date"] for bar in result["AAPL"]] == [
        date(2026, 9, 26),
        date(2026, 9, 28),
    ]
    assert result["AAPL"][1]["open_raw"] is None
    assert result["AAPL"][1]["volume_raw"] is None
    assert result["AAPL"][1]["dividend"] == 0.0
    assert result["AAPL"][1]["stock_split"] == 0.0


def test_fetch_daily_bars_omits_missing_ticker_without_dropping_returned_ticker():
    frame = _multi_index_frame(
        {
            "AAPL": {
                "Open": [100.0],
                "High": [105.0],
                "Low": [99.0],
                "Close": [104.0],
                "Adj Close": [103.5],
                "Volume": [1_000_000.0],
                "Dividends": [0.0],
                "Stock Splits": [0.0],
            }
        }
    )

    result = fetch_daily_bars_for_symbols(
        ["AAPL", "MISSING"],
        "2026-09-01",
        "2026-10-01",
        download_fn=_download_stub(frame, []),
    )

    assert set(result) == {"AAPL"}


def test_fetch_daily_bars_batches_81_symbols_into_three_download_calls():
    calls: list[dict[str, object]] = []
    symbols = [f"TICKER{index:02d}" for index in range(81)]

    result = fetch_daily_bars_for_symbols(
        symbols,
        "2026-09-01",
        "2026-10-01",
        batch_size=40,
        download_fn=_download_stub(pd.DataFrame(), calls),
    )

    assert result == {}
    assert [len(call["tickers"]) for call in calls] == [40, 40, 1]
    assert calls[0]["tickers"] == symbols[:40]
    assert calls[1]["tickers"] == symbols[40:80]
    assert calls[2]["tickers"] == symbols[80:]


def test_fetch_daily_bars_does_not_fan_out_when_a_batch_download_raises():
    calls: list[dict[str, object]] = []
    symbols = [f"TICKER{index:02d}" for index in range(40)]

    def failing_download(**kwargs: object) -> pd.DataFrame:
        calls.append(kwargs)
        raise RuntimeError("batch unavailable")

    result = fetch_daily_bars_for_symbols(
        symbols,
        "2026-09-01",
        "2026-10-01",
        batch_size=40,
        download_fn=failing_download,
    )

    assert result == {}
    assert len(calls) == 1
    assert calls[0]["tickers"] == symbols
