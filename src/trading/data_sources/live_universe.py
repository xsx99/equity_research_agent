"""Live universe provider adapters."""
from __future__ import annotations

from typing import Any, Iterable

from src.trading.data_sources.universe import UniverseAsset, UniverseProvider, load_universe_assets_from_env, normalize_ticker


class LiveUniverseProvider:
    """Adapt market-provider universe payloads into normalized universe assets."""

    def __init__(self, *, market_provider: Any, daily_bar_lookback_days: int = 20) -> None:
        self.market_provider = market_provider
        self.daily_bar_lookback_days = daily_bar_lookback_days

    def fetch_universe_assets(self) -> list[UniverseAsset]:
        rows = self.market_provider.fetch_universe_assets()
        assets = [_coerce_universe_asset(row) for row in rows]
        normalized = [asset for asset in assets if asset is not None]
        if normalized:
            return self._enrich_assets_with_batched_daily_bars(normalized)
        return load_universe_assets_from_env(
            default_price=100.0,
            default_avg_dollar_volume=50_000_000.0,
        )

    def fetch_assets_for_symbols(self, symbols: Iterable[str]) -> list[UniverseAsset]:
        assets: list[UniverseAsset] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            symbol = normalize_ticker(raw_symbol)
            if symbol in seen:
                continue
            seen.add(symbol)
            asset = self._build_targeted_asset(symbol)
            if asset is not None:
                assets.append(asset)
        return assets

    def _build_targeted_asset(self, symbol: str) -> UniverseAsset | None:
        try:
            bars = self.market_provider.fetch_daily_bars(symbol, lookback_days=20)
            context = self.market_provider.fetch_context(symbol)
        except Exception:
            return None
        if not isinstance(bars, list) or not bars:
            return None
        last_bar = bars[-1]
        close = last_bar.get("close")
        if not isinstance(close, (int, float)):
            return None
        dollar_volumes = [
            float(bar["close"]) * float(bar["volume"])
            for bar in bars
            if isinstance(bar, dict)
            and isinstance(bar.get("close"), (int, float))
            and isinstance(bar.get("volume"), (int, float))
        ]
        avg_dollar_volume = sum(dollar_volumes) / len(dollar_volumes) if dollar_volumes else None
        return UniverseAsset(
            symbol=symbol,
            company_name=context.get("company_name") if isinstance(context, dict) else None,
            asset_type="common_stock",
            exchange=None,
            sector=context.get("sector") if isinstance(context, dict) else None,
            industry=None,
            price=float(close),
            avg_dollar_volume=avg_dollar_volume,
        )

    def _enrich_assets_with_batched_daily_bars(
        self,
        assets: list[UniverseAsset],
    ) -> list[UniverseAsset]:
        batch_loader = getattr(self.market_provider, "fetch_daily_bars_for_symbols", None)
        if batch_loader is None:
            return assets
        symbols = tuple(asset.symbol for asset in assets if asset.price is None or asset.avg_dollar_volume is None)
        if not symbols:
            return assets
        try:
            bars_by_symbol = batch_loader(symbols, lookback_days=self.daily_bar_lookback_days)
        except Exception:
            return assets
        if not isinstance(bars_by_symbol, dict):
            return assets
        enriched: list[UniverseAsset] = []
        for asset in assets:
            bars = bars_by_symbol.get(asset.symbol)
            enriched.append(_enrich_asset_from_bars(asset, bars if isinstance(bars, list) else []))
        return enriched


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


def _enrich_asset_from_bars(asset: UniverseAsset, bars: list[Any]) -> UniverseAsset:
    normalized_bars = [bar for bar in bars if isinstance(bar, dict)]
    if not normalized_bars:
        return asset
    last_bar = normalized_bars[-1]
    close = last_bar.get("close")
    if not isinstance(close, (int, float)):
        return asset
    dollar_volumes = [
        float(bar["close"]) * float(bar["volume"])
        for bar in normalized_bars
        if isinstance(bar.get("close"), (int, float))
        and isinstance(bar.get("volume"), (int, float))
    ]
    avg_dollar_volume = (
        sum(dollar_volumes) / len(dollar_volumes)
        if dollar_volumes
        else asset.avg_dollar_volume
    )
    return UniverseAsset(
        symbol=asset.symbol,
        company_name=asset.company_name,
        asset_type=asset.asset_type,
        exchange=asset.exchange,
        sector=asset.sector,
        industry=asset.industry,
        price=float(close),
        avg_dollar_volume=avg_dollar_volume,
    )
