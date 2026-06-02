from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.providers.global_context.fred_provider import FredMacroDataProvider


class _StubResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None):
        self.text = text
        self._json_data = json_data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


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
