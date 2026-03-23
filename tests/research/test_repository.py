"""Unit tests for src/research/repository.py.

Uses mock sessions to avoid PostgreSQL-specific types (JSONB/UUID) that
don't work with SQLite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.db.models.research import ResearchRun, RunStatus
from src.db.models.watch_list import Watchlist
from src.research import repository


_AS_OF = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(**overrides) -> ResearchRun:
    defaults = dict(
        run_id=uuid.uuid4(),
        ticker="AAPL",
        as_of=_AS_OF,
        prompt_version="v1",
        model_name="gemini-2.5-flash-lite",
        input_json={"ticker": "AAPL"},
        status=RunStatus.QUEUED.value,
        started_at=None,
        finished_at=None,
        error_message=None,
    )
    defaults.update(overrides)
    run = MagicMock(spec=ResearchRun)
    for k, v in defaults.items():
        setattr(run, k, v)
    return run


# ---------------------------------------------------------------------------
# get_active_tickers
# ---------------------------------------------------------------------------


class TestGetActiveTickers:
    def test_returns_ticker_strings(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            MagicMock(ticker="AAPL"),
            MagicMock(ticker="MSFT"),
        ]
        result = repository.get_active_tickers(session)
        assert result == ["AAPL", "MSFT"]

    def test_returns_empty_list_when_none(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        result = repository.get_active_tickers(session)
        assert result == []


# ---------------------------------------------------------------------------
# add_ticker
# ---------------------------------------------------------------------------


class TestAddTicker:
    def test_adds_new_ticker(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        row = repository.add_ticker(session, "aapl")
        session.add.assert_called_once()
        assert row.ticker == "AAPL"
        assert row.is_active is True

    def test_uppercases_ticker(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        row = repository.add_ticker(session, "msft")
        assert row.ticker == "MSFT"

    def test_reactivates_existing_inactive(self):
        existing = MagicMock(spec=Watchlist, ticker="AAPL", is_active=False)
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = existing

        row = repository.add_ticker(session, "AAPL")
        assert row.is_active is True
        session.add.assert_not_called()

    def test_does_not_duplicate_active(self):
        existing = MagicMock(spec=Watchlist, ticker="AAPL", is_active=True)
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = existing

        row = repository.add_ticker(session, "AAPL")
        assert row is existing
        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# deactivate_ticker
# ---------------------------------------------------------------------------


class TestDeactivateTicker:
    def test_deactivates_and_returns_true(self):
        existing = MagicMock(spec=Watchlist, ticker="AAPL", is_active=True)
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = existing

        result = repository.deactivate_ticker(session, "aapl")
        assert result is True
        assert existing.is_active is False

    def test_returns_false_when_not_found(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        result = repository.deactivate_ticker(session, "ZZZZ")
        assert result is False


# ---------------------------------------------------------------------------
# create_run
# ---------------------------------------------------------------------------


class TestCreateRun:
    def test_creates_run_with_queued_status(self):
        session = MagicMock()
        run = repository.create_run(
            session,
            ticker="AAPL",
            as_of=_AS_OF,
            prompt_version="v1",
            model_name="gemini-2.5-flash-lite",
            input_json={"ticker": "AAPL"},
        )
        session.add.assert_called_once_with(run)
        assert run.ticker == "AAPL"
        assert run.status == RunStatus.QUEUED.value
        assert run.started_at is None
        assert run.finished_at is None
        assert run.error_message is None

    def test_run_id_is_uuid(self):
        session = MagicMock()
        run = repository.create_run(
            session,
            ticker="AAPL",
            as_of=_AS_OF,
            prompt_version="v1",
            model_name="gemini-2.5-flash-lite",
            input_json={},
        )
        assert isinstance(run.run_id, uuid.UUID)


# ---------------------------------------------------------------------------
# Status transition helpers
# ---------------------------------------------------------------------------


class TestMarkRunRunning:
    def test_sets_running_status_and_started_at(self):
        run = _make_run()
        session = MagicMock()
        repository.mark_run_running(session, run)
        assert run.status == RunStatus.RUNNING.value
        assert run.started_at is not None


class TestMarkRunSucceeded:
    def test_sets_succeeded_status_and_finished_at(self):
        run = _make_run(status=RunStatus.RUNNING.value)
        session = MagicMock()
        repository.mark_run_succeeded(session, run)
        assert run.status == RunStatus.SUCCEEDED.value
        assert run.finished_at is not None


class TestMarkRunFailed:
    def test_sets_failed_status_error_and_finished_at(self):
        run = _make_run(status=RunStatus.RUNNING.value)
        session = MagicMock()
        repository.mark_run_failed(session, run, "boom")
        assert run.status == RunStatus.FAILED.value
        assert run.error_message == "boom"
        assert run.finished_at is not None


# ---------------------------------------------------------------------------
# persist_output
# ---------------------------------------------------------------------------


_SAMPLE_OUTPUT = {
    "decision": "bullish",
    "confidence": 0.75,
    "time_horizon": "3d",
    "actionability": "watch",
    "thesis_summary": "Strong insider buying.",
    "key_drivers": ["insider buying"],
    "counterarguments": ["high valuation"],
    "invalidators": ["earnings miss"],
}


class TestPersistOutput:
    def test_persists_all_fields(self):
        run_id = uuid.uuid4()
        session = MagicMock()
        output = repository.persist_output(session, run_id, _SAMPLE_OUTPUT)
        session.add.assert_called_once_with(output)
        assert output.run_id == run_id
        assert output.decision == "bullish"
        assert output.confidence == 0.75
        assert output.time_horizon == "3d"
        assert output.actionability == "watch"
        assert output.thesis_summary == "Strong insider buying."
        assert output.output_json == _SAMPLE_OUTPUT
