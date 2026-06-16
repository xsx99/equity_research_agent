#!/usr/bin/env python3
"""Standalone smoke checks for insider + social_macro trading signal families."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.runtime.support import seed_initial_strategy_definitions
from src.trading.signals import build_signal_snapshot
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.strategies.matching import StrategyMatcher


def run_fixture_smoke(
    *,
    ticker: str,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    decision_time = as_of or datetime.now(timezone.utc)
    source_records = _fixture_source_records(ticker=ticker, decision_time=decision_time)
    snapshot = build_signal_snapshot(
        ticker=ticker,
        decision_time=decision_time,
        source_records=source_records,
        snapshot_type="pre_open",
    )
    repository = InMemoryTradingRepository()
    seed_initial_strategy_definitions(repository)
    definitions = [
        definition
        for definition in repository.load_active_strategy_definitions()
        if definition.strategy_id == "insider_accumulation_momentum_v1"
    ]
    candidates = StrategyMatcher().match_snapshot(
        snapshot,
        definitions,
        strategy_run_id=f"signal-family-smoke-{uuid.uuid4()}",
    )
    top_candidate = max(candidates, key=lambda item: item.candidate_score) if candidates else None
    return {
        "status": "passed" if top_candidate is not None else "failed",
        "mode": "fixture",
        "ticker": ticker.strip().upper(),
        "snapshot_families": [family for family, values in snapshot.signal_json.items() if values],
        "source_records_by_family": dict(sorted(Counter(record.source_family for record in source_records).items())),
        "signal_summary": {
            "insider": dict(snapshot.signal_json.get("insider") or {}),
            "social_macro": dict(snapshot.signal_json.get("social_macro") or {}),
        },
        "top_candidate": _candidate_json(top_candidate),
    }


def run_live_social_macro_smoke(
    *,
    ticker: str,
    as_of: datetime | None = None,
    global_context_fetcher: Callable[[datetime], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    decision_time = as_of or datetime.now(timezone.utc)
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    fetcher = global_context_fetcher
    if fetcher is None:
        from src.providers.global_context import get_global_context

        fetcher = lambda current_as_of: get_global_context(as_of=current_as_of, limit=5)
    service = SourceIngestionService(
        market_provider=_NoOpMarketDataProvider(),
        news_provider=None,
        global_context_fetcher=fetcher,
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="live_social_macro_smoke",
    )
    result = service.refresh_tickers(
        (ticker,),
        as_of=decision_time,
        run_type="smoke",
        source_families=("social_macro",),
    )
    rows = source_repository.latest_available_by_family(ticker, "social_macro", decision_time)
    return {
        "status": "passed" if rows and artifact_repository.social_macro_items else "failed",
        "mode": "live_social_macro",
        "ticker": ticker.strip().upper(),
        "source_records_by_family": {"social_macro": len(rows)},
        "social_macro_items_persisted": len(artifact_repository.social_macro_items),
        "provider_request_statuses": [run.status for run in artifact_repository.provider_request_runs],
        "orders_created": 0,
        "preview": [
            {
                "category": row.payload.get("category"),
                "headline": row.payload.get("title"),
                "importance_score": row.payload.get("importance_score"),
            }
            for row in rows
        ],
        "ingestion_status": result.ingestion_run.status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="NVDA", help="Ticker used for the smoke check.")
    parser.add_argument("--fixture", action="store_true", help="Run the fully fixture-backed snapshot/candidate smoke.")
    parser.add_argument(
        "--live-social-macro",
        action="store_true",
        help="Call the live global-context path once and confirm social_macro persistence only.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    args = parser.parse_args(argv)

    if args.live_social_macro:
        report = run_live_social_macro_smoke(ticker=args.ticker)
    else:
        report = run_fixture_smoke(ticker=args.ticker)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        _print_report(report)
    return 0 if report["status"] == "passed" else 1


class _NoOpMarketDataProvider:
    def fetch_daily_bars(self, ticker: str, lookback_days: int = 252) -> list[dict[str, Any]]:
        return []

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {}

    def fetch_option_chain(self, ticker: str) -> list[dict[str, Any]]:
        return []


def _fixture_source_records(*, ticker: str, decision_time: datetime) -> tuple[SourceRecord, ...]:
    symbol = ticker.strip().upper()
    available_at = decision_time - timedelta(hours=2)
    prior_day = decision_time.date() - timedelta(days=1)
    two_days_back = decision_time.date() - timedelta(days=2)
    return (
        SourceRecord(
            symbol,
            "technical",
            "fixture",
            "market_bars",
            "bars-1",
            available_at,
            available_at,
            available_at,
            available_at,
            {
                "bars": [
                    {"date": two_days_back, "open": 120.0, "high": 122.0, "low": 119.0, "close": 120.0, "volume": 1_000_000},
                    {"date": prior_day, "open": 120.0, "high": 125.0, "low": 119.0, "close": 124.0, "volume": 2_100_000},
                ],
                "benchmark_returns": {"SPY": 0.01},
            },
        ),
        SourceRecord(
            symbol,
            "fundamental",
            "fixture",
            "fundamental_snapshots",
            "fund-1",
            available_at,
            available_at,
            available_at,
            available_at,
            {"market_cap": 1_500_000_000_000, "sector": "Technology", "revenue_growth_score": 0.7},
        ),
        SourceRecord(
            symbol,
            "events_news",
            "fixture",
            "event_news_items",
            "event-1",
            available_at,
            available_at,
            available_at,
            available_at,
            {"event_type": "analyst_upgrade", "sentiment": "positive", "importance": "high"},
        ),
        SourceRecord(
            symbol,
            "insider",
            "fixture",
            "insider_trades",
            "insider-1",
            available_at,
            available_at,
            available_at,
            available_at,
            {
                "transaction_type": "P",
                "total_value": 180_000.0,
                "is_officer": True,
                "is_director": False,
                "filing_date": decision_time.date().isoformat(),
            },
        ),
        SourceRecord(
            symbol,
            "insider",
            "fixture",
            "insider_trades",
            "insider-2",
            available_at,
            available_at,
            available_at,
            available_at,
            {
                "transaction_type": "BUY",
                "total_value": 140_000.0,
                "is_officer": False,
                "is_director": True,
                "filing_date": decision_time.date().isoformat(),
            },
        ),
        SourceRecord(
            symbol,
            "social_macro",
            "fixture",
            "social_macro_items",
            "social-1",
            available_at,
            available_at,
            available_at,
            available_at,
            {
                "category": "trump_update",
                "title": f"Trump discusses {symbol} export controls",
                "summary": "Comments directly reference the company and chip policy.",
                "importance_score": 0.9,
                "importance_label": "high",
                "sentiment_direction": "negative",
                "explicit_ticker_mention_flag": True,
                "explicit_theme_mention_flag": True,
                "policy_headwind_flag": True,
                "policy_tailwind_flag": False,
                "theme_tags": ["ai_semis"],
            },
        ),
    )


def _candidate_json(candidate: object | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "strategy_id": getattr(candidate, "strategy_id", None),
        "candidate_score": float(getattr(candidate, "candidate_score", 0.0) or 0.0),
        "candidate_status": getattr(candidate, "candidate_status", None),
        "core_signal_evidence": dict(getattr(candidate, "core_signal_evidence", {}) or {}),
        "rejection_reason": getattr(candidate, "rejection_reason", None),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"[{report['status'].upper()}] trading_signal_family_smoke mode={report['mode']} ticker={report['ticker']}")
    if report["mode"] == "fixture":
        print(f"snapshot_families={','.join(report['snapshot_families'])}")
        print(f"source_records_by_family={report['source_records_by_family']}")
        top_candidate = report.get("top_candidate") or {}
        print(
            "top_candidate="
            f"{top_candidate.get('strategy_id')} score={top_candidate.get('candidate_score')} "
            f"status={top_candidate.get('candidate_status')}"
        )
    else:
        print(f"source_records_by_family={report['source_records_by_family']}")
        print(f"social_macro_items_persisted={report['social_macro_items_persisted']}")
        print(f"provider_request_statuses={report['provider_request_statuses']}")


if __name__ == "__main__":
    raise SystemExit(main())
