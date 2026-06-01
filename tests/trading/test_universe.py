from datetime import datetime, timezone

from src.trading.universe import (
    UniverseAsset,
    UniverseFilterConfig,
    apply_universe_filters,
    load_universe_assets_from_env,
)


def test_universe_filters_common_stock_liquidity_and_manual_exclude():
    config = UniverseFilterConfig(
        min_price=5.0,
        min_avg_dollar_volume=25_000_000,
        excluded_sectors=("Energy",),
        manual_exclude=("MSFT",),
    )
    assets = [
        UniverseAsset("AAPL", "Apple", "common_stock", "NASDAQ", "Technology", "Hardware", 182.0, 90_000_000),
        UniverseAsset("PENNY", "Penny", "common_stock", "NYSE", "Technology", "Software", 2.0, 80_000_000),
        UniverseAsset("THIN", "Thin", "common_stock", "NYSE", "Technology", "Software", 40.0, 10_000_000),
        UniverseAsset("OIL", "Oil", "common_stock", "NYSE", "Energy", "Exploration", 70.0, 90_000_000),
        UniverseAsset("ETF1", "ETF", "etf", "NYSE", "Financials", "ETF", 50.0, 90_000_000),
        UniverseAsset("MSFT", "Microsoft", "common_stock", "NASDAQ", "Technology", "Software", 320.0, 90_000_000),
    ]

    result = apply_universe_filters(
        assets,
        config,
        snapshot_time=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
    )

    assert result.included_symbols == ("AAPL",)
    exclusions = {symbol.symbol: symbol.exclusion_reason for symbol in result.excluded}
    assert exclusions == {
        "PENNY": "below_min_price",
        "THIN": "below_min_dollar_volume",
        "OIL": "sector_excluded",
        "ETF1": "not_common_stock",
        "MSFT": "manual_exclude",
    }


def test_universe_filter_env_fallback_uses_configured_symbols(monkeypatch):
    monkeypatch.setenv("TRADING_UNIVERSE_SYMBOLS", " aapl, msft ,,nvda ")

    assets = load_universe_assets_from_env(
        default_price=25.0,
        default_avg_dollar_volume=30_000_000,
    )

    assert [asset.symbol for asset in assets] == ["AAPL", "MSFT", "NVDA"]
    assert all(asset.asset_type == "common_stock" for asset in assets)
