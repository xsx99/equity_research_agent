"""Shared deterministic fixtures and builders for trading smoke runtimes."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.trading.brokers.paper_stock import PaperOrderRequest
from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig
from src.trading.phases.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.risk import PortfolioContext
from src.trading.risk.context import RiskFactorExposureRecord
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.signals.sources import InMemorySignalSourceRepository
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.data_sources.universe_scan import UniverseScanPipeline
from src.trading.signals.pipeline import SignalPipeline
from src.trading.strategies.scoring import StrategyPipeline


def _build_preopen_fixture_run(
    decision_time: datetime,
) -> tuple[Any, tuple[Any, ...], Any, InMemoryTradingRepository]:
    repository = InMemoryTradingRepository()
    _seed_strategy_definitions(repository)
    source_repository = InMemorySignalSourceRepository()
    manual_request_service = ManualTickerRequestService(now=lambda: decision_time)
    universe_result = UniverseScanPipeline(
        provider=_FixtureUniverseProvider(),
        config=UniverseFilterConfig(excluded_sectors=("Financials",)),
        now=lambda: decision_time,
    ).run()
    repository.save_universe_snapshot(universe_result)
    ingestion_service = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: decision_time,
        sleeper=lambda seconds: None,
    )
    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=manual_request_service,
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe_result,
        decision_time=decision_time,
    )
    for snapshot in snapshots:
        repository.save_signal_snapshot(snapshot)
    strategy_result = StrategyPipeline(
        repository=repository,
        manual_request_service=manual_request_service,
    ).run(
        snapshots=snapshots,
        decision_time=decision_time,
    )
    return universe_result, snapshots, strategy_result, repository


def _build_universe_and_snapshots(
    decision_time: datetime,
    *,
    with_manual_request: bool = False,
) -> tuple[Any, tuple[Any, ...], InMemoryTradingRepository]:
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository()
    manual_request_service = ManualTickerRequestService(now=lambda: decision_time)
    if with_manual_request:
        manual_request_service.create("NVDA", "manual review fixture", "review_only")
    universe_result = UniverseScanPipeline(
        provider=_FixtureUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: decision_time,
    ).run()
    repository.save_universe_snapshot(universe_result)
    ingestion_service = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: decision_time,
        sleeper=lambda seconds: None,
    )
    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=manual_request_service,
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe_result,
        decision_time=decision_time,
    )
    for snapshot in snapshots:
        repository.save_signal_snapshot(snapshot)
    return universe_result, snapshots, repository


def _seed_strategy_definitions(repository: InMemoryTradingRepository) -> None:
    repository.save_strategy_definition(_simple_strategy_definition())


def _simple_strategy_definition() -> StrategyDefinitionRecord:
    return StrategyDefinitionRecord(
        strategy_definition_id="relative-strength-definition",
        strategy_id="relative_strength_rotation_v1",
        version="v1",
        display_name="Relative Strength Rotation",
        strategy_layer="tactical_pattern",
        typical_horizon="2w-3m",
        config_json={"required_signals": []},
        lifecycle_status="active",
        is_active=True,
        source="seed",
    )


def _manual_snapshot(ticker: str, decision_time: datetime) -> Any:
    source_repository = InMemorySignalSourceRepository()
    source_repository.add(
        *_fixture_source_ingestion_records(ticker=ticker, as_of=decision_time)
    )
    return SignalPipeline(
        source_repository=source_repository,
        manual_request_service=ManualTickerRequestService(now=lambda: decision_time),
    ).build_pre_open_snapshots(
        universe_result=UniverseScanPipeline(
            provider=_SingleTickerUniverseProvider(ticker),
            config=UniverseFilterConfig(),
            now=lambda: decision_time,
        ).run(),
        decision_time=decision_time,
    )[0]


def _fixture_source_ingestion_records(*, ticker: str, as_of: datetime) -> tuple[Any, ...]:
    repository = InMemoryTradingRepository()
    source_repository = InMemorySignalSourceRepository()
    result = SourceIngestionService(
        market_provider=_FixtureMarketProvider(),
        news_provider=_FixtureNewsProvider(),
        source_repository=source_repository,
        artifact_repository=repository,
        provider_name="fixture",
        now=lambda: as_of,
        sleeper=lambda seconds: None,
    ).refresh_tickers((ticker,), as_of=as_of, run_type="fixture")
    return result.source_records


def _empty_portfolio_context(as_of: datetime) -> PortfolioContext:
    return PortfolioContext(
        as_of=as_of,
        account_equity=100_000.0,
        cash_balance=100_000.0,
        buying_power=200_000.0,
        excess_liquidity=100_000.0,
        positions=(),
        open_strategy_exposure={},
        current_factor_exposure=(
            RiskFactorExposureRecord(
                factor_type="sector",
                factor_value="technology",
                gross_exposure=0.0,
                net_exposure=0.0,
                long_exposure=0.0,
                short_exposure=0.0,
                position_count=0,
            ),
        ),
        stock_margin_requirement=0.0,
        option_margin_requirement=0.0,
        total_margin_requirement=0.0,
    )


def _reflection_agent_runner(prompt: str, model_name: str) -> dict[str, Any]:
    return {
        "content": {
            "trade_date": "2026-06-02",
            "portfolio_summary": {
                "realized_pnl": 125.0,
                "unrealized_pnl": -10.0,
                "benchmark_return": 0.01,
            },
            "what_worked": ["Waited for confirmation before adding."],
            "what_failed": ["Late entries after the main move."],
            "attribution": [],
            "learning_factors": [
                {
                    "factor_type": "candidate_filter",
                    "scope": "strategy",
                    "title": "Require confirmation for extended gaps",
                    "strategy_id": "relative_strength_rotation_v1",
                    "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
                    "recommendation": "Require confirmation before entry.",
                    "confidence": 0.7,
                    "activation_policy": "auto_risk_tightening",
                    "effect_tags": ["require_confirmation", "lower_confidence"],
                    "evidence": ["Reduced false starts in fixture outcomes."],
                }
            ],
            "strategy_proposal_hints": [
                {"title": "Post-gap reclaim continuation"}
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    }


def _strategy_evolution_agent_runner(prompt: str, model_name: str) -> dict[str, Any]:
    return {
        "content": {
            "proposals": [
                {
                    "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                    "display_name": "Post-Gap VWAP Reclaim",
                    "source_reflection_ids": ["reflection-1"],
                    "core_thesis": "Stocks that reclaim VWAP after an early fade can continue higher.",
                    "typical_horizon": "intraday-3d",
                    "required_signals": [
                        "opening_gap_pct",
                        "vwap_reclaim",
                        "relative_volume",
                        "opening_range_reclaim",
                    ],
                    "optional_signals": ["fresh_catalyst_type"],
                    "scoring_rules": {"min_opening_gap_pct": 0.02},
                    "risk_tags": ["gap_risk", "intraday_momentum"],
                    "macro_blocked_regimes": ["stressed"],
                    "invalidators": ["re-loses VWAP"],
                    "evidence_summary": "Observed repeatedly in fixture reflection rows.",
                }
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    }


class _FixtureUniverseProvider:
    def fetch_universe_assets(self) -> list[UniverseAsset]:
        return [
            UniverseAsset("AAPL", "Apple", "common_stock", "NASDAQ", "Technology", "Hardware", 180.0, 90_000_000),
            UniverseAsset("MSFT", "Microsoft", "common_stock", "NASDAQ", "Technology", "Software", 320.0, 95_000_000),
            UniverseAsset("NVDA", "NVIDIA", "common_stock", "NASDAQ", "Technology", "Semiconductors", 120.0, 140_000_000),
        ]


class _SingleTickerUniverseProvider:
    def __init__(self, ticker: str) -> None:
        self._ticker = ticker.upper()

    def fetch_universe_assets(self) -> list[UniverseAsset]:
        return [
            UniverseAsset(
                self._ticker,
                self._ticker,
                "common_stock",
                "NASDAQ",
                "Technology",
                "Semiconductors",
                120.0,
                140_000_000,
            )
        ]


class _FixtureMarketProvider:
    def fetch_daily_bars(self, ticker: str, lookback_days: int) -> list[dict[str, Any]]:
        return [
            {"date": date(2026, 6, 1), "open": 100.0, "high": 104.0, "low": 99.0, "close": 101.0, "volume": 1_000_000},
            {"date": date(2026, 6, 2), "open": 101.0, "high": 106.0, "low": 100.0, "close": 104.0, "volume": 2_100_000},
        ]

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {
            "market_cap": 3_000_000_000_000,
            "quality_score": 0.8,
            "revenue_growth_score": 0.7,
            "sector": "Technology",
            "earnings_in_days": 10,
        }


class _FixtureNewsProvider:
    def fetch_recent(self, ticker: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "title": f"{ticker} upgraded after demand check",
                "summary": "Analyst raises rating.",
                "published_at": "2026-06-02T10:30:00+00:00",
                "source": "fixture",
                "signal_type": "analyst_rating",
            }
        ]


class _FakePaperStockBroker:
    def submit_order(self, request: PaperOrderRequest) -> Any:
        self.last_request = request
        return type(
            "Order",
            (),
            {
                "paper_order_id": "paper-order-1",
                "broker_order_id": "broker-order-1",
                "client_order_id": "client-order-1",
                "ticker": request.ticker,
                "status": "filled",
                "rejection_reason": None,
            },
        )()

    def find_execution_by_order_id(self, paper_order_id: str) -> Any:
        return type(
            "Execution",
            (),
            {
                "paper_execution_id": "exec-1",
                "paper_order_id": paper_order_id,
                "broker_order_id": "broker-order-1",
                "ticker": "AAPL",
                "quantity": 0.01,
                "fill_price": 315.0,
                "trade_date": _fixed_now().date(),
                "executed_at": _fixed_now(),
                "net_cash_effect": -3.15,
            },
        )()

    def sync_account(self) -> dict[str, Any]:
        return {
            "cash": "999996.85",
            "equity": "1000000.00",
            "portfolio_value": "1000000.00",
            "buying_power": "1999996.85",
            "long_market_value": "3.15",
            "initial_margin": "1.58",
            "maintenance_margin": "0.95",
            "last_equity": "1000000.00",
        }

    def sync_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "avg_entry_price": "315.00",
                "current_price": "315.00",
                "market_value": "3.15",
                "side": "long",
            }
        ]


def _fixed_now() -> datetime:
    return datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(str(value))


__all__ = [
    "_FakePaperStockBroker",
    "_FixtureMarketProvider",
    "_FixtureNewsProvider",
    "_FixtureUniverseProvider",
    "_SingleTickerUniverseProvider",
    "_build_preopen_fixture_run",
    "_build_universe_and_snapshots",
    "_decimal_or_none",
    "_empty_portfolio_context",
    "_fixed_now",
    "_fixture_source_ingestion_records",
    "_manual_snapshot",
    "_reflection_agent_runner",
    "_seed_strategy_definitions",
    "_simple_strategy_definition",
    "_strategy_evolution_agent_runner",
    "_uuid_or_none",
]
