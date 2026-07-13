#!/usr/bin/env python3
"""Run a low-volume live smoke for batched universe bar enrichment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.market_data.alpaca_provider import AlpacaMarketDataProvider
from src.trading.data_sources.universe import normalize_ticker


def run_smoke(
    *,
    tickers: tuple[str, ...],
    market_provider: Any,
    lookback_days: int = 20,
    batch_size: int = 50,
) -> dict[str, Any]:
    symbols = tuple(dict.fromkeys(normalize_ticker(ticker) for ticker in tickers if ticker.strip()))
    if not symbols:
        raise ValueError("at_least_one_ticker_required")
    bars_by_symbol = market_provider.fetch_daily_bars_for_symbols(
        symbols,
        lookback_days=lookback_days,
        batch_size=batch_size,
    )
    rows = []
    for symbol in symbols:
        bars = bars_by_symbol.get(symbol, [])
        price, avg_dollar_volume = _price_and_avg_dollar_volume(bars)
        rows.append(
            {
                "symbol": symbol,
                "bar_count": len(bars),
                "price": price,
                "avg_dollar_volume": avg_dollar_volume,
                "status": "enriched" if price is not None and avg_dollar_volume is not None else "missing_bars",
            }
        )
    return {
        "status": "passed" if any(row["status"] == "enriched" for row in rows) else "failed",
        "lookback_days": lookback_days,
        "batch_size": batch_size,
        "ticker_count": len(symbols),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=("TSM",), help="Small ticker list to smoke.")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--env-file", help="Optional dotenv file to load before constructing providers.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    else:
        load_dotenv()
    report = run_smoke(
        tickers=tuple(args.tickers),
        market_provider=AlpacaMarketDataProvider(),
        lookback_days=args.lookback_days,
        batch_size=args.batch_size,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"status={report['status']} ticker_count={report['ticker_count']}")
        for row in report["rows"]:
            print(
                f"{row['symbol']} {row['status']} bars={row['bar_count']} "
                f"price={row['price']} avg_dollar_volume={row['avg_dollar_volume']}"
            )
    return 0 if report["status"] == "passed" else 1


def _price_and_avg_dollar_volume(bars: list[Any]) -> tuple[float | None, float | None]:
    normalized_bars = [bar for bar in bars if isinstance(bar, dict)]
    if not normalized_bars:
        return None, None
    last_bar = normalized_bars[-1]
    close = last_bar.get("close")
    if not isinstance(close, (int, float)):
        return None, None
    dollar_volumes = [
        float(bar["close"]) * float(bar["volume"])
        for bar in normalized_bars
        if isinstance(bar.get("close"), (int, float))
        and isinstance(bar.get("volume"), (int, float))
    ]
    avg_dollar_volume = sum(dollar_volumes) / len(dollar_volumes) if dollar_volumes else None
    return float(close), avg_dollar_volume


if __name__ == "__main__":
    raise SystemExit(main())
