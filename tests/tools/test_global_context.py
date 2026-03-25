"""Unit tests for global context helpers and tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.tools.global_context import GlobalContextTool, get_global_context
from src.tools.context import ToolContext


class _StubMacroProvider:
    def fetch_indicators(self, as_of):
        assert as_of == datetime(2026, 3, 24, 13, 20, tzinfo=timezone.utc)
        return {
            "vix": {
                "label": "CBOE Volatility Index",
                "source": "FRED:VIXCLS",
                "unit": "index",
                "value": 17.4,
                "observed_on": "2026-03-24",
            },
            "credit_spread": {
                "label": "ICE BofA US High Yield OAS",
                "source": "FRED:BAMLH0A0HYM2",
                "unit": "pct",
                "value": 3.8,
                "observed_on": "2026-03-24",
            },
        }


class _StubOfficialProvider:
    def fetch_recent(self, limit):
        assert limit == 15
        return [
            {
                "source": "whitehouse.gov",
                "title": "Treasury and Commerce announce new export controls",
                "summary": "The administration announced new export controls affecting chip shipments.",
                "published_at": "2026-03-24T12:00:00Z",
                "url": "https://www.whitehouse.gov/example",
            },
            {
                "source": "whitehouse.gov",
                "title": "Flying the flag at full-staff",
                "summary": "A ceremonial proclamation.",
                "published_at": "2026-03-24T11:30:00Z",
                "url": "https://www.whitehouse.gov/ceremonial",
            },
            {
                "source": "whitehouse.gov",
                "title": "President Trump Announces Cabinet and Cabinet Level Appointments",
                "summary": "Scott Bessent is nominated to be Secretary of the Treasury.",
                "published_at": "2025-01-20T19:30:00Z",
                "url": "https://www.whitehouse.gov/old-trump-item",
            }
        ]


class _StubTrumpProvider:
    def fetch_recent(self, limit):
        assert limit == 15
        return [
            {
                "source": "whitehouse.gov",
                "title": "President Donald J. Trump delivers remarks",
                "summary": "Remarks on Iran, oil markets, and sanctions.",
                "published_at": "2026-03-24T11:40:00Z",
                "url": "https://www.whitehouse.gov/remarks/example",
            },
            {
                "source": "whitehouse.gov",
                "title": "President Trump greets visitors",
                "summary": "A ceremonial appearance with no market implications.",
                "published_at": "2026-03-24T09:00:00Z",
                "url": "https://www.whitehouse.gov/ceremonial-trump",
            }
        ]


class _StubGeopoliticalProvider:
    def fetch_recent(self, limit):
        assert limit == 15
        return [
            {
                "source": "AP News",
                "title": "Airstrikes hit Iran as diplomatic efforts accelerate",
                "summary": "Regional tensions remained elevated and oil markets stayed volatile.",
                "published_at": "2026-03-24T12:10:00Z",
                "url": "https://apnews.com/article/example",
            },
            {
                "source": "AP News",
                "title": "Jury finds that Bill Cosby sexually assaulted woman in 1972 and awards her nearly $60 million",
                "summary": "A California civil jury has found Bill Cosby liable.",
                "published_at": "2026-03-23T21:00:58Z",
                "url": "https://apnews.com/article/bill-cosby-example",
            }
        ]


def test_get_global_context_omits_official_updates_by_default():
    snapshot = get_global_context(
        as_of=datetime(2026, 3, 24, 13, 20, tzinfo=timezone.utc),
        macro_provider=_StubMacroProvider(),
        official_updates_provider=_StubOfficialProvider(),
        trump_updates_provider=_StubTrumpProvider(),
        geopolitical_provider=_StubGeopoliticalProvider(),
    )

    assert snapshot["as_of"] == "2026-03-24T13:20:00+00:00"
    assert snapshot["indicators"]["vix"]["value"] == pytest.approx(17.4)
    assert snapshot["official_updates"] == []
    assert snapshot["trump_updates"][0]["title"].startswith("President Donald J. Trump")
    assert snapshot["geopolitical_news"][0]["source"] == "AP News"
    assert len(snapshot["geopolitical_news"]) == 1


def test_get_global_context_can_include_filtered_official_updates_when_opted_in():
    snapshot = get_global_context(
        as_of=datetime(2026, 3, 24, 13, 20, tzinfo=timezone.utc),
        macro_provider=_StubMacroProvider(),
        official_updates_provider=_StubOfficialProvider(),
        geopolitical_provider=_StubGeopoliticalProvider(),
        include_official_updates=True,
    )

    assert len(snapshot["official_updates"]) == 1
    assert snapshot["official_updates"][0]["title"] == (
        "Treasury and Commerce announce new export controls"
    )
    assert snapshot["trump_updates"] == []


def test_global_context_tool_runs_helper():
    tool = GlobalContextTool(
        macro_provider=_StubMacroProvider(),
        official_updates_provider=_StubOfficialProvider(),
        trump_updates_provider=_StubTrumpProvider(),
        geopolitical_provider=_StubGeopoliticalProvider(),
    )

    result = tool.run(
        {"as_of": "2026-03-24T13:20:00+00:00"},
        ToolContext(),
    )

    assert result["indicators"]["credit_spread"]["value"] == pytest.approx(3.8)
    assert result["official_updates"] == []
    assert result["trump_updates"][0]["title"] == "President Donald J. Trump delivers remarks"
    assert result["geopolitical_news"][0]["title"] == (
        "Airstrikes hit Iran as diplomatic efforts accelerate"
    )
