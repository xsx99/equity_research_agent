"""Compatibility shim for trading runtime support helpers."""
from __future__ import annotations

import sys

from src.trading.phases._shell import support as _canonical

build_default_news_provider = _canonical.build_default_news_provider
build_execution_report = _canonical.build_execution_report
build_runtime_report = _canonical.build_runtime_report
seed_default_universe_filter_config = _canonical.seed_default_universe_filter_config
seed_initial_strategy_definitions = _canonical.seed_initial_strategy_definitions
summarize_execution_attempts = _canonical.summarize_execution_attempts
_has_non_empty_value = _canonical._has_non_empty_value
_merge_missing_seed_config = _canonical._merge_missing_seed_config

__all__ = [
    "build_default_news_provider",
    "build_execution_report",
    "build_runtime_report",
    "seed_default_universe_filter_config",
    "seed_initial_strategy_definitions",
    "summarize_execution_attempts",
    "_has_non_empty_value",
    "_merge_missing_seed_config",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
