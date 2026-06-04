"""Shared helpers for trading runtime report building and dependency bootstrap."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from src.trading.strategies.catalog import get_initial_strategy_definitions
from src.trading.strategies.matching import StrategyDefinitionRecord


def seed_initial_strategy_definitions(repository: Any) -> None:
    """Seed the initial strategy catalog only when the repository is empty."""
    if repository.load_strategy_definitions():
        return
    for row in get_initial_strategy_definitions():
        repository.save_strategy_definition(StrategyDefinitionRecord.from_mapping(row))


def build_execution_report(*, mode: str, orders_submitted: int) -> dict[str, Any]:
    """Normalize runtime execution reporting across live trading phases."""
    return {
        "mode": mode,
        "orders_submitted": orders_submitted,
    }


def build_runtime_report(
    *,
    phase: str,
    as_of: datetime,
    summary: dict[str, Any],
    status: str = "passed",
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize scheduler-facing runtime responses."""
    report: dict[str, Any] = {
        "status": status,
        "phase": phase,
        "as_of": as_of.isoformat(),
        "summary": summary,
    }
    if execution is not None:
        report["execution"] = execution
    return report


def build_default_news_provider() -> Any | None:
    """Build the preferred live news provider from available credentials/providers."""
    if os.getenv("FINNHUB_API_KEY"):
        from src.providers.news_data.finnhub import FinnhubNewsProvider

        return FinnhubNewsProvider()
    try:
        from src.providers.news_data.alpaca import AlpacaNewsProvider

        return AlpacaNewsProvider()
    except Exception:
        return None
