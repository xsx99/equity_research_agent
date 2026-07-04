"""Compatibility shim for smoke fixture support helpers."""
from __future__ import annotations

import sys

from src.trading.phases._shell import smoke_support as _canonical

_FakePaperStockBroker = _canonical._FakePaperStockBroker
_FixtureMarketProvider = _canonical._FixtureMarketProvider
_FixtureNewsProvider = _canonical._FixtureNewsProvider
_FixtureUniverseProvider = _canonical._FixtureUniverseProvider
_SingleTickerUniverseProvider = _canonical._SingleTickerUniverseProvider
_build_preopen_fixture_run = _canonical._build_preopen_fixture_run
_build_universe_and_snapshots = _canonical._build_universe_and_snapshots
_decimal_or_none = _canonical._decimal_or_none
_empty_portfolio_context = _canonical._empty_portfolio_context
_fixed_now = _canonical._fixed_now
_fixture_source_ingestion_records = _canonical._fixture_source_ingestion_records
_manual_snapshot = _canonical._manual_snapshot
_reflection_agent_runner = _canonical._reflection_agent_runner
_seed_strategy_definitions = _canonical._seed_strategy_definitions
_simple_strategy_definition = _canonical._simple_strategy_definition
_strategy_evolution_agent_runner = _canonical._strategy_evolution_agent_runner
_uuid_or_none = _canonical._uuid_or_none

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

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
