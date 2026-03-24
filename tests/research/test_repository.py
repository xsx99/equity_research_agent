"""Unit tests for src/research/repository.py.

Uses mock sessions to avoid PostgreSQL-specific types (JSONB/UUID) that
don't work with SQLite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.db.models.evaluation import EvalResult, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, RunStatus
from src.db.models.watch_list import Watchlist
from src.research import repository


_AS_OF = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)
_EVAL_AS_OF = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
_EVAL_CUTOFF = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)  # well past all horizons


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
    "time_horizon_rationale": "Recent insider buying should matter over the next few trading sessions.",
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


def _make_run_and_output(
    time_horizon="3d",
    status=RunStatus.SUCCEEDED.value,
    as_of=_EVAL_AS_OF,
):
    run_id = uuid.uuid4()
    run = MagicMock(spec=ResearchRun)
    run.run_id = run_id
    run.ticker = "AAPL"
    run.as_of = as_of
    run.status = status

    output = MagicMock(spec=ResearchOutput)
    output.run_id = run_id
    output.decision = "bullish"
    output.time_horizon = time_horizon
    return run, output


class TestGetEligibleRuns:
    def test_returns_eligible_run(self):
        run, output = _make_run_and_output()
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (run, output)
        ]
        results = repository.get_eligible_runs(session, as_of_cutoff=_EVAL_CUTOFF)
        assert len(results) == 1
        assert results[0] == (run, output)

    def test_filters_out_run_whose_window_has_not_elapsed(self):
        # as_of + 3 days = 2026-03-04, cutoff = 2026-03-03 → not elapsed
        run, output = _make_run_and_output(
            time_horizon="3d",
            as_of=datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
        )
        early_cutoff = datetime(2026, 3, 3, 9, 0, 0, tzinfo=timezone.utc)
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (run, output)
        ]
        results = repository.get_eligible_runs(session, as_of_cutoff=early_cutoff)
        assert results == []

    def test_returns_empty_when_no_rows(self):
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = []
        results = repository.get_eligible_runs(session, as_of_cutoff=_EVAL_CUTOFF)
        assert results == []


class TestUpsertEvalResult:
    def _call(self, session, existing=None, run_id=None):
        run_id = run_id or uuid.uuid4()
        session.query.return_value.filter.return_value.first.return_value = existing
        return repository.upsert_eval_result(
            session,
            run_id=run_id,
            horizon_days=3,
            realized_return=0.05,
            benchmark_return=0.02,
            benchmark_symbol="SPY",
            evaluation_method=EvaluationMethod.RULE_V1.value,
            evaluation_params=None,
            outcome_label="correct",
        )

    def test_inserts_when_no_existing_row(self):
        session = MagicMock()
        result = self._call(session, existing=None)
        session.add.assert_called_once_with(result)
        assert result.outcome_label == "correct"
        assert result.horizon_days == 3

    def test_updates_when_existing_row(self):
        existing = MagicMock(spec=EvalResult)
        session = MagicMock()
        result = self._call(session, existing=existing)
        assert result is existing
        session.add.assert_not_called()
        assert existing.outcome_label == "correct"
        assert existing.realized_return == 0.05

    def test_upsert_overwrites_outcome_label(self):
        existing = MagicMock(spec=EvalResult)
        existing.outcome_label = "partially_correct"
        session = MagicMock()
        run_id = uuid.uuid4()
        self._call(session, existing=existing, run_id=run_id)
        existing.outcome_label = "correct"
        self._call(session, existing=existing, run_id=run_id)
        assert existing.outcome_label == "correct"
