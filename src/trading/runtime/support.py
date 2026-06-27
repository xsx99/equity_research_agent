"""Shared helpers for trading runtime report building and dependency bootstrap."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from typing import Any

from src.trading.strategies.definitions import load_all_trading_definitions
from src.trading.strategies.matching import StrategyDefinitionRecord


_PATCHABLE_SEED_CONFIG_KEYS = (
    "selection_policy",
    "default_trade_identity",
    "allowed_trade_identities",
    "allowed_instruments",
    "allowed_option_strategy_types",
    "required_option_leg_fields",
    "required_assignment_fields",
    "option_policy",
    "earnings_policy",
    "default_exit_policy",
)


def seed_initial_strategy_definitions(repository: Any) -> None:
    """Insert missing seed definitions and patch missing seed config metadata."""
    existing = {
        (definition.strategy_id, definition.version): definition
        for definition in repository.load_strategy_definitions()
    }
    for row in load_all_trading_definitions():
        expected = StrategyDefinitionRecord.from_mapping(row)
        key = (expected.strategy_id, expected.version)
        current = existing.get(key)
        if current is None:
            repository.save_strategy_definition(expected)
            existing[key] = expected
            continue
        if current.source != "seed":
            continue
        repaired_config = _merge_missing_seed_config(
            current=current.config_json,
            expected=expected.config_json,
        )
        if repaired_config == current.config_json:
            continue
        repaired_definition = replace(current, config_json=repaired_config)
        repository.save_strategy_definition(repaired_definition)
        existing[key] = repaired_definition


def seed_default_universe_filter_config(session: Any) -> None:
    """Insert a permissive active universe filter profile when none exists."""
    from src.db.models.trading import UniverseFilterConfig as UniverseFilterConfigModel

    existing = (
        session.query(UniverseFilterConfigModel)
        .filter(UniverseFilterConfigModel.is_active.is_(True))
        .first()
    )
    if existing is not None:
        return
    session.add(
        UniverseFilterConfigModel(
            profile_name="default",
            version=1,
            is_active=True,
            min_price=5,
            min_avg_dollar_volume=10_000_000,
            included_sectors_json=[],
            excluded_sectors_json=[],
            included_industries_json=[],
            excluded_industries_json=[],
            exchanges_json=[],
            asset_types_json=[],
            manual_include_json=[],
            manual_exclude_json=[],
        )
    )
    session.flush()


def build_execution_report(
    *,
    mode: str,
    orders_submitted: int,
    option_orders_submitted: int = 0,
    orders_skipped: int = 0,
    orders_failed: int = 0,
    skip_reasons: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Normalize runtime execution reporting across live trading phases."""
    return {
        "mode": mode,
        "orders_submitted": orders_submitted,
        "option_orders_submitted": option_orders_submitted,
        "orders_skipped": orders_skipped,
        "orders_failed": orders_failed,
        "skip_reasons": dict(skip_reasons or {}),
    }


def summarize_execution_attempts(
    attempts: tuple[object, ...] | list[object],
) -> dict[str, Any]:
    skipped = 0
    failed = 0
    skip_reasons: dict[str, int] = {}
    for attempt in attempts:
        outcome = str(getattr(attempt, "outcome", "") or "")
        reason_code = str(getattr(attempt, "reason_code", "") or "")
        if outcome == "skipped":
            skipped += 1
            if reason_code:
                skip_reasons[reason_code] = skip_reasons.get(reason_code, 0) + 1
        elif outcome == "failed":
            failed += 1
    return {
        "orders_skipped": skipped,
        "orders_failed": failed,
        "skip_reasons": skip_reasons,
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


def _merge_missing_seed_config(
    *,
    current: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current or {})
    changed = False
    for key in _PATCHABLE_SEED_CONFIG_KEYS:
        if _has_non_empty_value(merged.get(key)):
            continue
        expected_value = expected.get(key)
        if not _has_non_empty_value(expected_value):
            continue
        merged[key] = expected_value
        changed = True
    return merged if changed else dict(current or {})


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    if value == {}:
        return False
    return True
