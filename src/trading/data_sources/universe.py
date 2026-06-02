"""Universe provider contracts and deterministic liquidity filters."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass(frozen=True)
class UniverseAsset:
    """Normalized provider asset row used by the universe scanner."""

    symbol: str
    company_name: str | None
    asset_type: str
    exchange: str | None
    sector: str | None
    industry: str | None
    price: float | None
    avg_dollar_volume: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_ticker(self.symbol))
        object.__setattr__(self, "asset_type", self.asset_type.strip().lower())


@dataclass(frozen=True)
class UniverseFilterConfig:
    """User-editable active universe filter profile."""

    profile_name: str = "default"
    version: int = 1
    min_price: float = 5.0
    min_avg_dollar_volume: float = 25_000_000.0
    included_sectors: tuple[str, ...] = ()
    excluded_sectors: tuple[str, ...] = ()
    included_industries: tuple[str, ...] = ()
    excluded_industries: tuple[str, ...] = ()
    exchanges: tuple[str, ...] = ()
    asset_types: tuple[str, ...] = ("common_stock",)
    manual_include: tuple[str, ...] = ()
    manual_exclude: tuple[str, ...] = ()
    is_active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "included_sectors", _normalize_names(self.included_sectors))
        object.__setattr__(self, "excluded_sectors", _normalize_names(self.excluded_sectors))
        object.__setattr__(self, "included_industries", _normalize_names(self.included_industries))
        object.__setattr__(self, "excluded_industries", _normalize_names(self.excluded_industries))
        object.__setattr__(self, "exchanges", tuple(value.strip().upper() for value in self.exchanges))
        object.__setattr__(self, "asset_types", tuple(value.strip().lower() for value in self.asset_types))
        object.__setattr__(self, "manual_include", tuple(normalize_ticker(value) for value in self.manual_include))
        object.__setattr__(self, "manual_exclude", tuple(normalize_ticker(value) for value in self.manual_exclude))


@dataclass(frozen=True)
class UniverseSymbolDecision:
    """Inclusion or exclusion decision for one symbol in a universe snapshot."""

    symbol: str
    status: str
    exclusion_reason: str | None
    asset: UniverseAsset


@dataclass(frozen=True)
class UniverseSnapshotResult:
    """Deterministic universe scan output."""

    snapshot_id: str
    snapshot_time: datetime
    filter_config: UniverseFilterConfig
    included: tuple[UniverseSymbolDecision, ...]
    excluded: tuple[UniverseSymbolDecision, ...]
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def included_symbols(self) -> tuple[str, ...]:
        return tuple(decision.symbol for decision in self.included)


class UniverseProvider(Protocol):
    """Provider contract for tradable asset discovery."""

    def fetch_universe_assets(self) -> list[UniverseAsset]:
        """Return normalized assets that may enter the universe filter."""


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker symbols used by trading helpers."""
    return ticker.strip().upper()


def apply_universe_filters(
    assets: Iterable[UniverseAsset],
    config: UniverseFilterConfig,
    *,
    snapshot_time: datetime | None = None,
) -> UniverseSnapshotResult:
    """Apply user-editable universe filters and record exclusion reasons."""
    included: list[UniverseSymbolDecision] = []
    excluded: list[UniverseSymbolDecision] = []
    seen: set[str] = set()

    for asset in assets:
        if asset.symbol in seen:
            continue
        seen.add(asset.symbol)
        reason = _exclusion_reason(asset, config)
        if reason is None:
            included.append(UniverseSymbolDecision(asset.symbol, "included", None, asset))
        else:
            excluded.append(UniverseSymbolDecision(asset.symbol, "excluded", reason, asset))

    included.sort(key=lambda item: item.symbol)
    excluded.sort(key=lambda item: item.symbol)
    return UniverseSnapshotResult(
        snapshot_id=str(uuid.uuid4()),
        snapshot_time=snapshot_time or datetime.now(timezone.utc),
        filter_config=config,
        included=tuple(included),
        excluded=tuple(excluded),
        metadata={"input_count": len(seen)},
    )


def load_universe_assets_from_env(
    *,
    env_var: str = "TRADING_UNIVERSE_SYMBOLS",
    default_price: float | None = None,
    default_avg_dollar_volume: float | None = None,
) -> list[UniverseAsset]:
    """Build common-stock universe rows from a local/dev env fallback."""
    raw_symbols = os.getenv(env_var, "")
    symbols = [normalize_ticker(symbol) for symbol in raw_symbols.split(",") if symbol.strip()]
    return [
        UniverseAsset(
            symbol=symbol,
            company_name=None,
            asset_type="common_stock",
            exchange=None,
            sector=None,
            industry=None,
            price=default_price,
            avg_dollar_volume=default_avg_dollar_volume,
        )
        for symbol in symbols
    ]


def _exclusion_reason(asset: UniverseAsset, config: UniverseFilterConfig) -> str | None:
    if asset.symbol in config.manual_exclude:
        return "manual_exclude"
    if config.asset_types and asset.asset_type not in config.asset_types:
        return "not_common_stock" if "common_stock" in config.asset_types else "asset_type_excluded"
    if asset.price is None or asset.price < config.min_price:
        return "below_min_price"
    if asset.avg_dollar_volume is None or asset.avg_dollar_volume < config.min_avg_dollar_volume:
        return "below_min_dollar_volume"
    if config.exchanges and (asset.exchange or "").strip().upper() not in config.exchanges:
        return "exchange_excluded"

    sector = _normalize_optional_name(asset.sector)
    industry = _normalize_optional_name(asset.industry)
    if config.included_sectors and sector not in config.included_sectors:
        return "sector_not_included"
    if config.excluded_sectors and sector in config.excluded_sectors:
        return "sector_excluded"
    if config.included_industries and industry not in config.included_industries:
        return "industry_not_included"
    if config.excluded_industries and industry in config.excluded_industries:
        return "industry_excluded"
    return None


def _normalize_names(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(_normalize_optional_name(value) for value in values if value.strip())


def _normalize_optional_name(value: str | None) -> str:
    return (value or "").strip().casefold()
