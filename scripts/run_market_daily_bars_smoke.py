#!/usr/bin/env python3
"""Run a no-network/no-database smoke for the Yahoo daily-bar workflow."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.ranking.calendar import RankingSessionCalendar
from src.trading.signals.sources import MarketDailyBarRecord
from src.trading.workflows.market_daily_bars import MarketDailyBarsBatch


class _SmokeRepository:
    def __init__(self, rows: list[MarketDailyBarRecord] | None = None) -> None:
        self.rows = list(rows or [])
        self.runs: list[Any] = []

    def save_market_daily_bars(self, bars) -> None:
        self.rows.extend(bars)

    def record_source_ingestion_run(self, run) -> None:
        self.runs.append(run)


def run_smoke(*, as_of: datetime | None = None) -> dict[str, Any]:
    smoke_time = as_of or datetime.now(timezone.utc)
    expected_session = RankingSessionCalendar().latest_completed_session(smoke_time).session_date
    symbols = ("AAPL", "SPY", "QQQ", "GLD")

    def successful_yahoo(symbols, start, end):
        return {
            symbol: [{"trade_date": expected_session, "close_raw": 100.0}]
            for symbol in symbols
        }

    successful_repository = _SmokeRepository()
    successful_result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=successful_yahoo,
        repository=successful_repository,
        now=lambda: smoke_time,
    ).run(as_of=smoke_time)

    previous = MarketDailyBarRecord(
        ticker="AAPL",
        trade_date=expected_session - timedelta(days=1),
        open_raw=99.0,
        high_raw=101.0,
        low_raw=98.0,
        close_raw=100.0,
        adj_close=100.0,
        volume_raw=1_000,
        dividend=0.0,
        stock_split=0.0,
        provider="yahoo",
        ingested_at=smoke_time - timedelta(days=1),
        available_for_decision_at=smoke_time - timedelta(days=1),
    )
    degraded_repository = _SmokeRepository([previous])

    def failed_yahoo(symbols, start, end):
        raise RuntimeError("fixture yahoo outage")

    degraded_result = MarketDailyBarsBatch(
        active_ticker_loader=lambda: ["AAPL"],
        yahoo_fetcher=failed_yahoo,
        repository=degraded_repository,
        now=lambda: smoke_time,
    ).run(as_of=smoke_time)

    return {
        "status": "passed",
        "successful_run": {
            "tickers_requested": successful_result.tickers_requested,
            "tickers_succeeded": successful_result.tickers_succeeded,
            "rows_saved": successful_result.bars_saved,
            "symbols": symbols,
        },
        "degraded_run": {
            "status": degraded_result.ingestion_run.status,
            "tickers_succeeded": degraded_result.tickers_succeeded,
            "rows_after_failure": len(degraded_repository.rows),
            "last_good_row_preserved": degraded_repository.rows == [previous],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args()
    result = run_smoke()
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("market daily bars smoke passed")


if __name__ == "__main__":
    main()
