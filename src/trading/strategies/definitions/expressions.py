"""Expression-bucket seed definitions exposed through the split definitions package."""
from __future__ import annotations

from src.trading.strategies.catalog import INITIAL_STRATEGY_CATALOG, StrategyCatalogItem


INITIAL_EXPRESSION_DEFINITIONS: tuple[StrategyCatalogItem, ...] = tuple(
    item
    for item in INITIAL_STRATEGY_CATALOG
    if item.strategy_layer == "expression_bucket"
)


def get_initial_expression_definitions() -> list[dict[str, object]]:
    """Return expression-bucket seed rows ready for StrategyDefinition insertion."""
    return [
        {
            "strategy_id": item.strategy_id,
            "version": item.version,
            "display_name": item.display_name,
            "strategy_layer": item.strategy_layer,
            "typical_horizon": item.typical_horizon,
            "allowed_common_stock_direction": "long_only",
            "config_json": item.config_json(),
            "lifecycle_status": "active",
            "source": "seed",
            "parent_strategy_id": None,
            "evidence_json": {},
            "is_active": True,
        }
        for item in INITIAL_EXPRESSION_DEFINITIONS
    ]
