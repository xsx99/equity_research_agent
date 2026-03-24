"""Unit tests for src/research/pipeline.py.

All external dependencies (DB session, market data, news, LLM) are replaced
with stubs so tests run without network access or API keys.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from src.agents.research import ResearchAgent
from src.db.models.research import RunStatus
from src.db.models.watch_list import Watchlist
from src.prompts.registry import PromptRegistry
from src.research.pipeline import ResearchPipeline, TickerResult
from src.tools import ToolContext, ToolRegistry
from src.tools.base import BaseTool


# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_AS_OF = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)

_GOOD_OUTPUT = {
    "decision": "bullish",
    "confidence": 0.8,
    "time_horizon": "3d",
    "actionability": "actionable",
    "thesis_summary": "Strong insider buying cluster.",
    "key_drivers": ["insider buying"],
    "counterarguments": ["macro uncertainty"],
    "invalidators": ["price drops below 200-day MA"],
}


def _good_runner(prompt: str, model_name: str) -> str:
    return json.dumps(_GOOD_OUTPUT)


def _failing_runner(prompt: str, model_name: str) -> str:
    raise RuntimeError("llm_unavailable")


def _make_agent(runner=_good_runner) -> ResearchAgent:
    return ResearchAgent(
        tool_registry=ToolRegistry(),
        prompt_registry=PromptRegistry.get_default(),
        model_name="gemini-2.5-flash-lite",
        agent_runner=runner,
    )


def _make_stub_tool_registry() -> ToolRegistry:
    class _StubMarketTool(BaseTool):
        name = "get_market_snapshot"

        @property
        def schema(self) -> dict[str, Any]:
            return {"name": self.name, "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}

        def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
            return {
                "last_price": 150.0,
                "return_1d": 0.01,
                "return_5d": 0.03,
                "return_since_market_open": 0.02,
                "sector": "Technology",
                "earnings_in_days": 30,
            }

    class _StubNewsTool(BaseTool):
        name = "get_recent_news"

        @property
        def schema(self) -> dict[str, Any]:
            return {"name": self.name, "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}

        def run(self, input: dict[str, Any], context: ToolContext) -> list[dict[str, str]]:
            return [{"title": "AAPL hits record", "summary": "All-time high."}]

    registry = ToolRegistry()
    registry.register(_StubMarketTool())
    registry.register(_StubNewsTool())
    return registry


def _make_session() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# run_ticker — happy path
# ---------------------------------------------------------------------------


class TestRunTickerHappyPath:
    """Pipeline happy path: run creates, transitions, and persists correctly."""

    def _run(self, session=None):
        session = session or _make_session()
        pipeline = ResearchPipeline(
            session=session,
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        return pipeline.run_ticker("aapl", as_of=_AS_OF), session

    def test_returns_success_result(self):
        result, _ = self._run()
        assert result.success is True
        assert result.ticker == "AAPL"
        assert result.run_id is not None
        assert result.error is None

    @patch("src.research.pipeline.repository")
    def test_calls_status_transitions_in_order(self, mock_repo):
        """create_run → mark_running → (agent) → persist_output → mark_succeeded."""
        run = MagicMock()
        run.run_id = uuid.uuid4()
        mock_repo.create_run.return_value = run

        session = _make_session()
        pipeline = ResearchPipeline(
            session=session,
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        pipeline.run_ticker("AAPL", as_of=_AS_OF)

        mock_repo.create_run.assert_called_once()
        mock_repo.mark_run_running.assert_called_once_with(session, run)
        mock_repo.persist_output.assert_called_once()
        mock_repo.mark_run_succeeded.assert_called_once_with(session, run)
        mock_repo.mark_run_failed.assert_not_called()

    @patch("src.research.pipeline.repository")
    def test_input_json_includes_market_and_news(self, mock_repo):
        run = MagicMock()
        run.run_id = uuid.uuid4()
        mock_repo.create_run.return_value = run

        session = _make_session()
        pipeline = ResearchPipeline(
            session=session,
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        pipeline.run_ticker("AAPL", as_of=_AS_OF)

        _, kwargs = mock_repo.create_run.call_args
        input_json = kwargs["input_json"]
        assert input_json["ticker"] == "AAPL"
        assert input_json["price_snapshot"]["last_price"] == 150.0
        assert input_json["price_snapshot"]["return_since_market_open"] == 0.02
        assert len(input_json["news"]) >= 1


# ---------------------------------------------------------------------------
# run_ticker — agent failure
# ---------------------------------------------------------------------------


class TestRunTickerAgentFailure:

    @patch("src.research.pipeline.repository")
    def test_marks_run_failed_on_agent_error(self, mock_repo):
        run = MagicMock()
        run.run_id = uuid.uuid4()
        mock_repo.create_run.return_value = run

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(runner=_failing_runner),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_ticker("AAPL", as_of=_AS_OF)

        assert result.success is False
        assert result.error is not None
        mock_repo.mark_run_failed.assert_called_once()
        mock_repo.mark_run_succeeded.assert_not_called()
        mock_repo.persist_output.assert_not_called()

    @patch("src.research.pipeline.repository")
    def test_failed_result_has_run_id(self, mock_repo):
        run_id = uuid.uuid4()
        run = MagicMock()
        run.run_id = run_id
        mock_repo.create_run.return_value = run

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(runner=_failing_runner),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_ticker("AAPL", as_of=_AS_OF)

        assert result.run_id == run_id

    @patch("src.research.pipeline.repository")
    def test_does_not_raise(self, mock_repo):
        run = MagicMock()
        run.run_id = uuid.uuid4()
        mock_repo.create_run.return_value = run

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(runner=_failing_runner),
            tool_registry=_make_stub_tool_registry(),
        )
        # Should not raise — failure must be captured in the result.
        result = pipeline.run_ticker("AAPL", as_of=_AS_OF)
        assert isinstance(result, TickerResult)


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------


class TestRunAll:

    @patch("src.research.pipeline.repository")
    def test_empty_watchlist_returns_zero_counts(self, mock_repo):
        mock_repo.get_active_tickers.return_value = []

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_all(as_of=_AS_OF)
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.ticker_results == []

    @patch("src.research.pipeline.repository")
    def test_all_succeed(self, mock_repo):
        mock_repo.get_active_tickers.return_value = ["AAPL", "MSFT"]
        runs = [MagicMock(run_id=uuid.uuid4()), MagicMock(run_id=uuid.uuid4())]
        mock_repo.create_run.side_effect = runs

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_all(as_of=_AS_OF)
        assert result.succeeded == 2
        assert result.failed == 0
        assert len(result.ticker_results) == 2

    @patch("src.research.pipeline.repository")
    def test_one_failure_does_not_abort_batch(self, mock_repo):
        """A failing ticker must not prevent remaining tickers from running."""
        mock_repo.get_active_tickers.return_value = ["AAPL", "FAIL", "MSFT"]

        call_count = {"n": 0}

        def _sometimes_failing(prompt, model_name):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("forced_failure")
            return json.dumps(_GOOD_OUTPUT)

        runs = [MagicMock(run_id=uuid.uuid4()) for _ in range(3)]
        mock_repo.create_run.side_effect = runs

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(runner=_sometimes_failing),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_all(as_of=_AS_OF)

        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.ticker_results) == 3

    @patch("src.research.pipeline.repository")
    def test_inactive_tickers_not_in_results(self, mock_repo):
        """Only active tickers returned by get_active_tickers should be processed."""
        mock_repo.get_active_tickers.return_value = ["AAPL"]
        mock_repo.create_run.return_value = MagicMock(run_id=uuid.uuid4())

        pipeline = ResearchPipeline(
            session=_make_session(),
            agent=_make_agent(),
            tool_registry=_make_stub_tool_registry(),
        )
        result = pipeline.run_all(as_of=_AS_OF)
        tickers = [r.ticker for r in result.ticker_results]
        assert "TSLA" not in tickers
        assert tickers == ["AAPL"]
