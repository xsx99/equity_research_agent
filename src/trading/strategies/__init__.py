"""Trading strategy catalog, matching, selection, classification, and calibration."""
from src.trading.strategies.calibration import ConfidenceCalibrationResult, ConfidenceCalibrator
from src.trading.strategies.catalog import INITIAL_STRATEGY_CATALOG, StrategyCatalogItem, get_initial_strategy_definitions
from src.trading.strategies.classifier import TradeClassificationRecord, TradeClassifier
from src.trading.strategies.matching import (
    CandidateScoreRecord,
    StrategyDefinitionRecord,
    StrategyMatcher,
    StrategyRunRecord,
    create_strategy_run,
)
from src.trading.strategies.selector import PrimaryStrategySelector, SelectedStrategyRecord
from src.trading.strategies.taxonomy import TRADE_IDENTITIES, TradeIdentityPolicy, get_trade_identity_policy

__all__ = [
    "CandidateScoreRecord",
    "ConfidenceCalibrationResult",
    "ConfidenceCalibrator",
    "INITIAL_STRATEGY_CATALOG",
    "PrimaryStrategySelector",
    "SelectedStrategyRecord",
    "StrategyCatalogItem",
    "StrategyDefinitionRecord",
    "StrategyMatcher",
    "StrategyRunRecord",
    "TRADE_IDENTITIES",
    "TradeClassificationRecord",
    "TradeClassifier",
    "TradeIdentityPolicy",
    "create_strategy_run",
    "get_initial_strategy_definitions",
    "get_trade_identity_policy",
]

