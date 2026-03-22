"""Unit tests for PR2 data sources and LLM client."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from src.research.llm_client import ResearchLLMClient
from src.research.tool import get_market_data as market_data_module
from src.research.tool import get_news_data as news_data_module


@dataclass
class FakeLogger:
    warnings: list[tuple[str, dict]] = field(default_factory=list)
    errors: list[tuple[str, dict]] = field(default_factory=list)

    def warning(self, msg: str, **kwargs):
        self.warnings.append((msg, kwargs))

    def error(self, msg: str, **kwargs):
        self.errors.append((msg, kwargs))


class StubMarketProvider:
    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        assert ticker == "AAPL"
        assert lookback_days == 6
        return [100.0, 101.0, 103.0, 102.0, 104.0, 105.0]

    def fetch_context(self, ticker: str) -> dict:
        assert ticker == "AAPL"
        return {"sector": "Technology", "earnings_in_days": 12}


class BrokenMarketProvider:
    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        raise RuntimeError("upstream_unavailable")

    def fetch_context(self, ticker: str) -> dict:
        return {}


class EmptyNewsProvider:
    def fetch_recent(self, ticker: str, limit: int):
        return []


class WorkingNewsProvider:
    def fetch_recent(self, ticker: str, limit: int):
        assert ticker == "MSFT"
        return [
            {"title": "Headline 1", "summary": "Summary 1"},
            {"title": "Headline 2", "summary": "Summary 2"},
            {"title": "Headline 3", "summary": "Summary 3"},
        ][:limit]


class BrokenNewsProvider:
    def fetch_recent(self, ticker: str, limit: int):
        raise RuntimeError("provider_boom")


def _valid_research_input() -> dict:
    return {
        "ticker": "AAPL",
        "as_of": "2026-03-21T12:00:00Z",
        "price_snapshot": {"last_price": 210.0, "return_1d": 0.01, "return_5d": 0.03},
        "context": {"sector": "Technology", "earnings_in_days": 9},
        "news": [{"title": "Sample headline", "summary": "Sample summary"}],
    }


def test_get_market_snapshot_happy_path():
    snapshot = market_data_module.get_market_snapshot("AAPL", provider=StubMarketProvider())
    assert snapshot["last_price"] == pytest.approx(105.0)
    assert snapshot["return_1d"] == pytest.approx((105.0 / 104.0) - 1)
    assert snapshot["return_5d"] == pytest.approx((105.0 / 100.0) - 1)
    assert snapshot["sector"] == "Technology"
    assert snapshot["earnings_in_days"] == 12


def test_get_market_snapshot_failure_returns_empty_and_logs(monkeypatch):
    fake_logger = FakeLogger()
    monkeypatch.setattr(market_data_module, "logger", fake_logger)

    snapshot = market_data_module.get_market_snapshot("MSFT", provider=BrokenMarketProvider())
    assert snapshot == {
        "last_price": None,
        "return_1d": None,
        "return_5d": None,
        "sector": None,
        "earnings_in_days": None,
    }
    assert fake_logger.errors
    assert fake_logger.errors[0][0] == "market_snapshot_failed"


def test_get_recent_news_uses_fallback_provider():
    items = news_data_module.get_recent_news(
        "MSFT",
        limit=2,
        providers=[EmptyNewsProvider(), WorkingNewsProvider()],
    )
    assert len(items) == 2
    assert items[0]["title"] == "Headline 1"
    assert items[1]["summary"] == "Summary 2"


def test_get_recent_news_logs_provider_failure(monkeypatch):
    fake_logger = FakeLogger()
    monkeypatch.setattr(news_data_module, "logger", fake_logger)

    items = news_data_module.get_recent_news(
        "MSFT",
        providers=[BrokenNewsProvider(), WorkingNewsProvider()],
    )
    assert len(items) == 3
    assert fake_logger.warnings
    assert fake_logger.warnings[0][0] == "news_provider_failed"
    assert fake_logger.warnings[0][1]["provider"] == "BrokenNewsProvider"


def test_llm_client_validates_structured_output():
    def fake_runner(prompt: str, model_name: str):
        assert "Input JSON" in prompt
        assert model_name == "gpt-test-mini"
        return {
            "decision": "bullish",
            "confidence": 0.72,
            "time_horizon": "3d",
            "actionability": "watch",
            "thesis_summary": "Momentum and news flow are improving.",
            "key_drivers": ["Price trend"],
            "counterarguments": ["Valuation risk"],
            "invalidators": ["Break below 20-day moving average"],
        }

    client = ResearchLLMClient(
        prompt_version="v1",
        model_name="gpt-test-mini",
        agent_runner=fake_runner,
    )

    output = client.run(_valid_research_input())
    assert output.decision == "bullish"
    assert output.time_horizon == "3d"
    assert output.confidence == pytest.approx(0.72)


def test_llm_client_invalid_output_logs_and_raises(monkeypatch):
    fake_logger = FakeLogger()
    monkeypatch.setattr("src.research.llm_client.logger", fake_logger)

    def bad_runner(prompt: str, model_name: str):
        return {
            "decision": "bullish",
            "confidence": 1.5,
            "time_horizon": "3d",
            "actionability": "watch",
            "thesis_summary": "Too confident payload.",
            "key_drivers": [],
            "counterarguments": [],
            "invalidators": [],
        }

    client = ResearchLLMClient(prompt_version="v1", model_name="gpt-test-mini", agent_runner=bad_runner)

    with pytest.raises(ValidationError):
        client.run(_valid_research_input())

    assert fake_logger.errors
    assert fake_logger.errors[0][0] == "structured_output_validation_failed"

