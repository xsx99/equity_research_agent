#!/usr/bin/env python3
"""Run a low-volume live smoke check for PR2 source ingestion.

Default mode fetches only technical market bars for one ticker. Add
`--families fundamental events_news` when you want to verify provider context
and news ingestion as well.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.tools.market_data.alpaca_provider import AlpacaMarketDataProvider
from src.tools.news_data import AlpacaNewsProvider, FinnhubNewsProvider, MarketauxNewsProvider
from src.tools.news_data.types import NewsProvider
from src.trading.repository import InMemoryTradingRepository
from src.trading.signal_sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.source_ingestion import SourceIngestionService
from src.trading.universe import normalize_ticker

_ALL_FAMILIES = ("technical", "fundamental", "events_news")


def run_smoke(
    *,
    ticker: str,
    families: Iterable[str],
    market_provider: Any,
    news_provider: NewsProvider | None,
    provider_name: str,
    as_of: datetime | None = None,
    sleeper=None,
) -> dict[str, Any]:
    """Run source ingestion through the real service and return a compact report."""
    normalized_families = _normalize_families(families)
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    smoke_as_of = as_of or datetime.now(timezone.utc)
    service = SourceIngestionService(
        market_provider=market_provider,
        news_provider=news_provider,
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name=provider_name,
        now=lambda: smoke_as_of,
        sleeper=sleeper or (lambda seconds: None),
    )
    result = service.refresh_tickers(
        (ticker,),
        as_of=smoke_as_of,
        run_type="smoke",
        source_families=normalized_families,
    )
    source_records = source_repository.records_for_ticker(ticker)
    records_by_family = Counter(record.source_family for record in source_records)
    required_families = set(normalized_families)
    if "events_news" in required_families and news_provider is None:
        required_families.remove("events_news")
    missing_families = sorted(family for family in required_families if records_by_family[family] == 0)
    status = "passed" if result.ingestion_run.status in {"succeeded", "degraded"} and not missing_families else "failed"
    return {
        "status": status,
        "ticker": normalize_ticker(ticker),
        "families": list(normalized_families),
        "ingestion_status": result.ingestion_run.status,
        "missing_families": missing_families,
        "source_records_by_family": dict(sorted(records_by_family.items())),
        "fundamental_snapshots": len(result.fundamental_snapshots),
        "event_news_items": len(result.event_news_items),
        "provider_request_statuses": [run.status for run in artifact_repository.provider_request_runs],
        "provider_requests": [
            {
                "endpoint": run.endpoint,
                "source_family": run.source_family,
                "status": run.status,
                "cache_status": run.cache_status,
                "request_count": run.request_count,
                "budget_remaining": run.budget_remaining,
                "degraded_mode": run.degraded_mode,
                "error_code": run.error_code,
            }
            for run in artifact_repository.provider_request_runs
        ],
        "technical_preview": _technical_preview(source_records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", default="AAPL", help="Ticker used for the smoke check.")
    parser.add_argument(
        "--env-file",
        help="Optional dotenv file to load before constructing live providers.",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        choices=_ALL_FAMILIES,
        default=("technical",),
        help="Source families to refresh. Defaults to technical only to save API quota.",
    )
    parser.add_argument(
        "--news-provider",
        choices=("auto", "none", "finnhub", "marketaux", "alpaca"),
        default="auto",
        help="News provider used when events_news is requested.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)

    families = _normalize_families(args.families)
    if "technical" in families and not _has_alpaca_creds():
        print("Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY or ALPACA_API_SECRET.")
        return 2

    market_provider = AlpacaMarketDataProvider()
    news_provider = _build_news_provider(args.news_provider) if "events_news" in families else None
    try:
        report = run_smoke(
            ticker=args.ticker,
            families=families,
            market_provider=market_provider,
            news_provider=news_provider,
            provider_name="live",
        )
    finally:
        _close_if_present(market_provider)
        _close_if_present(news_provider)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        _print_report(report)
    return 0 if report["status"] == "passed" else 1


def _normalize_families(families: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(family.strip() for family in families if family.strip()))
    unsupported = [family for family in normalized if family not in _ALL_FAMILIES]
    if unsupported:
        raise ValueError(f"unsupported_source_families:{','.join(unsupported)}")
    return normalized


def _build_news_provider(selection: str) -> NewsProvider | None:
    if selection == "none":
        return None
    if selection in {"auto", "finnhub"} and os.getenv("FINNHUB_API_KEY"):
        return FinnhubNewsProvider()
    if selection in {"auto", "marketaux"} and os.getenv("MARKETAUX_API_KEY"):
        return MarketauxNewsProvider()
    if selection in {"auto", "alpaca"} and _has_alpaca_creds():
        return AlpacaNewsProvider()
    if selection == "auto":
        return None
    raise RuntimeError(f"missing_{selection}_credentials")


def _has_alpaca_creds() -> bool:
    return bool(
        os.getenv("ALPACA_API_KEY")
        and (os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"))
    )


def _technical_preview(records: tuple[SourceRecord, ...]) -> dict[str, Any]:
    technical_records = [record for record in records if record.source_family == "technical"]
    if not technical_records:
        return {}
    record = max(technical_records, key=lambda item: item.available_for_decision_at)
    bars = record.payload.get("bars") or []
    latest_bar = bars[-1] if bars else {}
    return {
        "bar_count": len(bars),
        "latest_date": latest_bar.get("date"),
        "latest_close": latest_bar.get("close"),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"[{report['status'].upper()}] trading_source_ingestion_smoke ticker={report['ticker']}")
    print(f"families={','.join(report['families'])} ingestion_status={report['ingestion_status']}")
    print(f"source_records_by_family={report['source_records_by_family']}")
    if report["missing_families"]:
        print(f"missing_families={','.join(report['missing_families'])}")
    print(f"provider_request_statuses={report['provider_request_statuses']}")
    if report["technical_preview"]:
        print(f"technical_preview={report['technical_preview']}")


def _close_if_present(value: Any) -> None:
    if value is not None and hasattr(value, "close"):
        value.close()


if __name__ == "__main__":
    raise SystemExit(main())
