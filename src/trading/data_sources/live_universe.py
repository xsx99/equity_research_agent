"""Live universe provider adapters."""
from __future__ import annotations

from typing import Any

from src.trading.data_sources.universe import UniverseAsset, UniverseProvider, load_universe_assets_from_env


class LiveUniverseProvider:
    """Adapt market-provider universe payloads into normalized universe assets."""

    def __init__(self, *, market_provider: Any) -> None:
        self.market_provider = market_provider

    def fetch_universe_assets(self) -> list[UniverseAsset]:
        rows = self.market_provider.fetch_universe_assets()
        assets = [_coerce_universe_asset(row) for row in rows]
        normalized = [asset for asset in assets if asset is not None]
        if normalized:
            return normalized
        return load_universe_assets_from_env(
            default_price=100.0,
            default_avg_dollar_volume=50_000_000.0,
        )


def _coerce_universe_asset(row: Any) -> UniverseAsset | None:
    if isinstance(row, UniverseAsset):
        return row
    if not isinstance(row, dict):
        return None
    symbol = row.get("symbol")
    asset_type = row.get("asset_type")
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    if not isinstance(asset_type, str) or not asset_type.strip():
        return None
    return UniverseAsset(
        symbol=symbol,
        company_name=row.get("company_name") if isinstance(row.get("company_name"), str) else None,
        asset_type=asset_type,
        exchange=row.get("exchange") if isinstance(row.get("exchange"), str) else None,
        sector=row.get("sector") if isinstance(row.get("sector"), str) else None,
        industry=row.get("industry") if isinstance(row.get("industry"), str) else None,
        price=float(row["price"]) if isinstance(row.get("price"), (int, float)) else None,
        avg_dollar_volume=(
            float(row["avg_dollar_volume"])
            if isinstance(row.get("avg_dollar_volume"), (int, float))
            else None
        ),
    )
