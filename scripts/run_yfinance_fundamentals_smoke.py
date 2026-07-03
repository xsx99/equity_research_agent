#!/usr/bin/env python3
"""Fetch yfinance fundamental backfill fields for a small ticker list."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.market_data.yfinance_fundamentals import YFinanceFundamentalsProvider


DEFAULT_TICKERS = ("MRVL", "AMAT", "CRDO")


def run_smoke(tickers: tuple[str, ...] = DEFAULT_TICKERS) -> dict[str, Any]:
    provider = YFinanceFundamentalsProvider()
    return {ticker.upper(): provider.fetch(ticker) for ticker in tickers}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tickers",
        nargs="*",
        default=DEFAULT_TICKERS,
        help="Ticker symbols to fetch once via yfinance.",
    )
    args = parser.parse_args(argv)

    result = run_smoke(tuple(args.tickers))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
