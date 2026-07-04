#!/usr/bin/env python3
"""Run a low-volume live smoke check for PR2 source ingestion.

Default mode fetches only technical market bars for one ticker. Add
`--families fundamental events_news` when you want to verify provider context
and news ingestion as well.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config  # noqa: F401
from src.providers.market_data.alpaca_provider import AlpacaMarketDataProvider
from src.providers.news_data import AlpacaNewsProvider, FinnhubNewsProvider, MarketauxNewsProvider
from src.providers.news_data.types import NewsProvider
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.signals.sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.data_sources.universe import normalize_ticker

_ALL_FAMILIES = ("technical", "fundamental", "events_news")


def run_smoke(
    *,
    ticker: str,
    families: Iterable[str],
    market_provider: Any,
    news_provider: NewsProvider | None,
    provider_name: str,
    as_of: datetime | None = None,
    now=None,
    include_records: bool = False,
    sleeper=None,
) -> dict[str, Any]:
    """Run source ingestion through the real service and return a compact report."""
    normalized_families = _normalize_families(families)
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    smoke_as_of = as_of or datetime.now(timezone.utc)
    clock = now or (lambda: datetime.now(timezone.utc))
    service = SourceIngestionService(
        market_provider=market_provider,
        news_provider=news_provider,
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name=provider_name,
        now=clock,
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
    report = {
        "status": status,
        "ticker": normalize_ticker(ticker),
        "families": list(normalized_families),
        "ingestion_status": result.ingestion_run.status,
        "missing_families": missing_families,
        "source_records_by_family": dict(sorted(records_by_family.items())),
        "fundamental_snapshots": len(result.fundamental_snapshots),
        "event_news_items": len(result.event_news_items),
        "news_condensation": dict(result.ingestion_run.metadata_json.get("news_condensation", {})),
        "provider_request_statuses": [run.status for run in artifact_repository.provider_request_runs],
        "provider_requests": [
            {
                "endpoint": run.endpoint,
                "source_family": run.source_family,
                "status": run.status,
                "cache_status": run.cache_status,
                "request_count": run.request_count,
                "budget_remaining": run.budget_remaining,
                "started_at": _iso(run.started_at),
                "completed_at": _iso(run.completed_at),
                "latency_ms": run.latency_ms,
                "degraded_mode": run.degraded_mode,
                "error_code": run.error_code,
            }
            for run in artifact_repository.provider_request_runs
        ],
        "event_news_preview": _event_news_preview(result.event_news_items),
        "technical_preview": _technical_preview(source_records),
    }
    if include_records:
        report["source_records"] = [_source_record_json(record) for record in source_records]
    return report


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
    parser.add_argument(
        "--include-records",
        action="store_true",
        help="Include normalized SourceRecord rows and payloads in JSON output.",
    )
    parser.add_argument(
        "--show-http-logs",
        action="store_true",
        help="Allow httpx INFO logs. Off by default to avoid printing provider query parameters.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    if not args.show_http_logs:
        logging.getLogger("httpx").setLevel(logging.WARNING)

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
            include_records=args.include_records,
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
        "benchmark_returns": record.payload.get("benchmark_returns") or {},
        "premarket_gap_pct": record.payload.get("premarket_gap_pct"),
    }


def _event_news_preview(items) -> list[dict[str, Any]]:
    return [
        {
            "event_type": item.event_type,
            "headline": item.headline,
            "importance": item.importance,
            "published_at": _iso(item.published_at),
            "sentiment": item.sentiment,
            "source": item.provider,
            "summary": item.summary,
        }
        for item in items
    ]


def _source_record_json(record: SourceRecord) -> dict[str, Any]:
    return {
        "ticker": record.ticker,
        "source_family": record.source_family,
        "source": record.source,
        "source_table": record.source_table,
        "source_record_id": record.source_record_id,
        "event_time": _iso(record.event_time),
        "published_at": _iso(record.published_at),
        "ingested_at": _iso(record.ingested_at),
        "available_for_decision_at": _iso(record.available_for_decision_at),
        "payload": record.payload,
    }


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _print_report(report: dict[str, Any]) -> None:
    print(f"[{report['status'].upper()}] trading_source_ingestion_smoke ticker={report['ticker']}")
    print(f"families={','.join(report['families'])} ingestion_status={report['ingestion_status']}")
    print(f"source_records_by_family={report['source_records_by_family']}")
    if report["missing_families"]:
        print(f"missing_families={','.join(report['missing_families'])}")
    if report["news_condensation"]:
        print(f"news_condensation={report['news_condensation']}")
    print(f"provider_request_statuses={report['provider_request_statuses']}")
    if report["event_news_preview"]:
        print(f"event_news_preview={report['event_news_preview']}")
    if report["technical_preview"]:
        print(f"technical_preview={report['technical_preview']}")


def _close_if_present(value: Any) -> None:
    if value is not None and hasattr(value, "close"):
        value.close()


if __name__ == "__main__":
    raise SystemExit(main())
