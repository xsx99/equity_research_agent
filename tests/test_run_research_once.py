"""Tests for the one-off research runner script."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from src.research.pipeline import TickerResult

from scripts import run_research_once


def test_single_ticker_defaults_to_reuse_latest_global_context(monkeypatch):
    pipeline = MagicMock()
    pipeline.run_ticker.return_value = TickerResult(ticker="AAPL", run_id=None, success=True)

    monkeypatch.setattr(sys, "argv", ["run_research_once.py", "--ticker", "AAPL"])

    with patch("scripts.run_research_once.ResearchAgent"), \
         patch("scripts.run_research_once.build_research_tool_registry"), \
         patch("scripts.run_research_once.PromptRegistry.get_default"), \
         patch("scripts.run_research_once.ResearchPipeline", return_value=pipeline), \
         patch("scripts.run_research_once.get_session") as mock_get_session:
        session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        exit_code = run_research_once.main()

    assert exit_code == 0
    pipeline.run_ticker.assert_called_once_with(
        "AAPL",
        reuse_latest_global_context=True,
    )


def test_single_ticker_refresh_flag_forces_fresh_global_context(monkeypatch):
    pipeline = MagicMock()
    pipeline.run_ticker.return_value = TickerResult(ticker="AAPL", run_id=None, success=True)

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_research_once.py", "--ticker", "AAPL", "--refresh-global-context"],
    )

    with patch("scripts.run_research_once.ResearchAgent"), \
         patch("scripts.run_research_once.build_research_tool_registry"), \
         patch("scripts.run_research_once.PromptRegistry.get_default"), \
         patch("scripts.run_research_once.ResearchPipeline", return_value=pipeline), \
         patch("scripts.run_research_once.get_session") as mock_get_session:
        session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        exit_code = run_research_once.main()

    assert exit_code == 0
    pipeline.run_ticker.assert_called_once_with(
        "AAPL",
        reuse_latest_global_context=False,
    )
