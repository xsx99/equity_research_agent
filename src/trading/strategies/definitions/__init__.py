"""Split definitions entrypoints for tactical strategies and expression buckets."""
from __future__ import annotations

from src.trading.strategies.catalog import StrategyCatalogItem
from src.trading.strategies.definitions.expressions import (
    INITIAL_EXPRESSION_DEFINITIONS,
    get_initial_expression_definitions,
)
from src.trading.strategies.definitions.strategies import (
    INITIAL_STRATEGY_DEFINITIONS,
    get_initial_strategy_definitions,
)

StrategyDefinitionSeed = StrategyCatalogItem
ExpressionDefinitionSeed = StrategyCatalogItem


def load_all_trading_definitions() -> list[dict[str, object]]:
    """Return tactical strategy rows followed by expression-bucket rows."""
    return [
        *get_initial_strategy_definitions(),
        *get_initial_expression_definitions(),
    ]


__all__ = [
    "ExpressionDefinitionSeed",
    "INITIAL_EXPRESSION_DEFINITIONS",
    "INITIAL_STRATEGY_DEFINITIONS",
    "StrategyDefinitionSeed",
    "get_initial_expression_definitions",
    "get_initial_strategy_definitions",
    "load_all_trading_definitions",
]
