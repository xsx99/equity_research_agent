from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.providers.global_context.fred_provider import FredMacroDataProvider


class _StubResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None):
        self.text = text
        self._json_data = json_data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


class _CsvClient:
    def get(self, _url, *, params=None, **_kwargs):
        series_id = (params or {}).get("id")
        return _StubResponse(
            text=f"observation_date,{series_id}\n2026-07-18,78.4\n2026-07-21,79.2\n"
        )


def test_fetch_from_csv_reads_observation_date_header():
    client = MagicMock()
    client.get.return_value = _StubResponse(
        text="observation_date,VIXCLS\n2026-03-24,26.95\n2026-03-25,25.33\n"
    )
    provider = FredMacroDataProvider(client=client)

    value, observed_on = provider._fetch_from_csv("VIXCLS")

    assert value == 25.33
    assert observed_on == "2026-03-25"


def test_fetch_indicators_uses_live_vix_when_fred_is_stale():
    provider = FredMacroDataProvider(client=MagicMock())
    provider._fetch_latest_observation = MagicMock(
        side_effect=lambda series_id, as_of: (
            (25.33, "2026-03-25") if series_id == "VIXCLS" else (1.23, "2026-03-26")
        )
    )
    provider._fetch_live_vix_from_yahoo = MagicMock(return_value=(27.44, "2026-03-26"))

    indicators = provider.fetch_indicators(datetime(2026, 3, 26, 21, 59, tzinfo=timezone.utc))

    assert indicators["vix"]["value"] == 27.44
    assert indicators["vix"]["observed_on"] == "2026-03-26"
    assert indicators["vix"]["source"] == "YAHOO:^VIX"


def test_fetch_indicators_keeps_fred_vix_when_live_fallback_missing():
    provider = FredMacroDataProvider(client=MagicMock())
    provider._fetch_latest_observation = MagicMock(
        side_effect=lambda series_id, as_of: (
            (25.33, "2026-03-25") if series_id == "VIXCLS" else (1.23, "2026-03-26")
        )
    )
    provider._fetch_live_vix_from_yahoo = MagicMock(return_value=(None, None))

    indicators = provider.fetch_indicators(datetime(2026, 3, 26, 21, 59, tzinfo=timezone.utc))

    assert indicators["vix"]["value"] == 25.33
    assert indicators["vix"]["observed_on"] == "2026-03-25"
    assert indicators["vix"]["source"] == "FRED:VIXCLS"


def test_fetch_indicators_uses_gold_proxy_for_gold_without_querying_removed_fred_series():
    provider = FredMacroDataProvider(client=MagicMock())
    provider._fetch_latest_observation = MagicMock(return_value=(1.23, "2026-03-26"))
    provider._fetch_gold_proxy_from_market_data = MagicMock(return_value=(313.12, "2026-03-26"))
    provider._fetch_live_vix_from_yahoo = MagicMock(return_value=(27.44, "2026-03-26"))

    indicators = provider.fetch_indicators(datetime(2026, 3, 26, 21, 59, tzinfo=timezone.utc))

    queried_series = [call.args[0] for call in provider._fetch_latest_observation.call_args_list]

    assert indicators["gold_price"] == {
        "label": "Gold Proxy (GLD ETF)",
        "source": "ALPACA:GLD_PROXY",
        "unit": "USD/share",
        "value": 313.12,
        "observed_on": "2026-03-26",
    }
    assert "GOLDAMGBD228NLBM" not in queried_series


def test_fetch_indicators_populates_previous_close_for_return_display():
    provider = FredMacroDataProvider(client=_CsvClient())
    provider._fetch_gold_proxy_from_market_data = MagicMock(return_value=(374.42, "2026-07-21", 370.0))
    provider._fetch_live_vix_from_yahoo = MagicMock(return_value=(None, None))

    indicators = provider.fetch_indicators(datetime(2026, 7, 21, 21, 0, tzinfo=timezone.utc))

    assert indicators["oil_price"]["value"] == 79.2
    assert indicators["oil_price"]["previous_close"] == 78.4
    assert indicators["oil_price"]["return_vs_previous_close"] == pytest.approx((79.2 - 78.4) / 78.4)
    assert indicators["vix"]["previous_close"] == 78.4
    assert indicators["gold_price"]["previous_close"] == 370.0
    assert indicators["gold_price"]["return_vs_previous_close"] == pytest.approx((374.42 - 370.0) / 370.0)
