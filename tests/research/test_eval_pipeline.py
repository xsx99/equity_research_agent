"""Unit tests for src/research/eval_pipeline.py."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.evaluation import EvalOutcomeLabel
from src.db.models.research import ResearchOutput, ResearchRun, RunStatus


# ---------------------------------------------------------------------------
# apply_rule_v1 — imported after the module exists
# ---------------------------------------------------------------------------


class TestRuleV1:
    """Exhaustive label matrix tests. No I/O required."""

    def _label(self, decision, realized, benchmark=0.01, threshold=0.01):
        from src.research.eval_pipeline import apply_rule_v1
        return apply_rule_v1(decision, realized, benchmark, neutral_threshold=threshold)

    # --- realized_return is None ---

    def test_none_realized_returns_none(self):
        assert self._label("bullish", None) is None

    def test_none_realized_bearish_returns_none(self):
        assert self._label("bearish", None) is None

    def test_none_realized_neutral_returns_none(self):
        assert self._label("neutral", None) is None

    # --- bullish ---

    def test_bullish_positive_outperforms_benchmark_is_correct(self):
        assert self._label("bullish", 0.05, benchmark=0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bullish_positive_equals_benchmark_is_correct(self):
        assert self._label("bullish", 0.03, benchmark=0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bullish_positive_underperforms_benchmark_is_partially_correct(self):
        assert self._label("bullish", 0.01, benchmark=0.05) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bullish_exactly_zero_is_partially_correct(self):
        assert self._label("bullish", 0.0, benchmark=0.01) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bullish_negative_is_wrong_direction(self):
        assert self._label("bullish", -0.03, benchmark=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_bullish_none_benchmark_positive_is_partially_correct(self):
        # Can't confirm outperformance without benchmark
        assert self._label("bullish", 0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # --- bearish ---

    def test_bearish_negative_beats_benchmark_is_correct(self):
        # stock fell -5%, SPY fell -3% → stock fell more → bearish correct
        assert self._label("bearish", -0.05, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_equals_benchmark_is_correct(self):
        assert self._label("bearish", -0.03, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_outperforms_benchmark_is_partially_correct(self):
        # stock fell -1%, SPY fell -5% → stock held up better → partial
        assert self._label("bearish", -0.01, benchmark=-0.05) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_exactly_zero_is_partially_correct(self):
        assert self._label("bearish", 0.0, benchmark=-0.01) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_positive_is_wrong_direction(self):
        assert self._label("bearish", 0.03, benchmark=-0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_bearish_none_benchmark_negative_is_partially_correct(self):
        assert self._label("bearish", -0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # --- neutral / abstain ---

    def test_neutral_small_move_is_uninformative(self):
        assert self._label("neutral", 0.005, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_neutral_exactly_at_threshold_is_uninformative(self):
        assert self._label("neutral", 0.01, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_neutral_exceeds_threshold_positive_is_wrong_direction(self):
        assert self._label("neutral", 0.02, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_neutral_exceeds_threshold_negative_is_wrong_direction(self):
        assert self._label("neutral", -0.02, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_abstain_small_move_is_uninformative(self):
        assert self._label("abstain", 0.005, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_abstain_large_move_is_wrong_direction(self):
        assert self._label("abstain", 0.05, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value


# ---------------------------------------------------------------------------
# Helpers for EvalPipeline tests
# ---------------------------------------------------------------------------

_AS_OF = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
_CUTOFF = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)


def _make_run(ticker="AAPL", as_of=_AS_OF) -> MagicMock:
    run = MagicMock(spec=ResearchRun)
    run.run_id = uuid.uuid4()
    run.ticker = ticker
    run.as_of = as_of
    run.status = RunStatus.SUCCEEDED.value
    return run


def _make_output(decision="bullish", time_horizon="3d") -> MagicMock:
    output = MagicMock(spec=ResearchOutput)
    output.decision = decision
    output.time_horizon = time_horizon
    return output


class _StubProvider:
    """Returns a fixed return for every ticker/date pair."""

    def __init__(self, return_value: Optional[float] = 0.05):
        self.call_count = 0
        self._return_value = return_value

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        self.call_count += 1
        if self._return_value is None:
            raise RuntimeError("simulated_market_failure")
        # Fake two bars that produce the configured return
        return [100.0, 100.0 * (1 + self._return_value)]

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        return []

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# TestEvalPipelineHappyPath
# ---------------------------------------------------------------------------


class TestEvalPipelineHappyPath:

    @patch("src.research.eval_pipeline.repository")
    def test_happy_path_calls_upsert(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(
            session=MagicMock(),
            provider=_StubProvider(return_value=0.05),
        )
        result = pipeline.run_all(as_of=_CUTOFF)

        mock_repo.upsert_eval_result.assert_called_once()
        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["run_id"] == run.run_id
        assert call_kwargs["horizon_days"] == 3
        assert call_kwargs["outcome_label"] is not None
        assert result.evaluated == 1
        assert result.failed == 0

    @patch("src.research.eval_pipeline.repository")
    def test_benchmark_fetched_only_once_per_unique_key(self, mock_repo):
        """Two runs with same as_of, same horizon → SPY fetched once."""
        from src.research.eval_pipeline import EvalPipeline

        run1 = _make_run("AAPL", as_of=_AS_OF)
        run2 = _make_run("MSFT", as_of=_AS_OF)
        output1 = _make_output("bullish", "3d")
        output2 = _make_output("bullish", "3d")
        mock_repo.get_eligible_runs.return_value = [(run1, output1), (run2, output2)]

        provider = _StubProvider(return_value=0.05)
        pipeline = EvalPipeline(session=MagicMock(), provider=provider, benchmark_symbol="SPY")
        pipeline.run_all(as_of=_CUTOFF)

        # 2 ticker calls (AAPL, MSFT) + 1 SPY call = 3 total
        assert provider.call_count == 3

    @patch("src.research.eval_pipeline.repository")
    def test_market_failure_writes_null_outcome_no_exception(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(
            session=MagicMock(),
            provider=_StubProvider(return_value=None),
        )
        result = pipeline.run_all(as_of=_CUTOFF)

        mock_repo.upsert_eval_result.assert_called_once()
        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["realized_return"] is None
        assert call_kwargs["outcome_label"] is None
        assert result.evaluated == 1  # written, so counts as evaluated

    @patch("src.research.eval_pipeline.repository")
    def test_correct_outcome_label_for_bullish_outperform(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output(decision="bullish", time_horizon="3d")
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        # ticker returns 5%, SPY returns 2% → bullish correct
        call_count = {"n": 0}
        class _DirectedProvider:
            def fetch_daily_closes_range(self, ticker, start_date, end_date):
                call_count["n"] += 1
                if ticker == "SPY":
                    return [100.0, 102.0]
                return [100.0, 105.0]
            def fetch_daily_closes(self, ticker, lookback_days):
                return []
            def fetch_context(self, ticker):
                return {}

        pipeline = EvalPipeline(session=MagicMock(), provider=_DirectedProvider())
        pipeline.run_all(as_of=_CUTOFF)

        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["outcome_label"] == EvalOutcomeLabel.CORRECT.value


# ---------------------------------------------------------------------------
# TestEvalPipelineEdgeCases
# ---------------------------------------------------------------------------


class TestEvalPipelineEdgeCases:

    @patch("src.research.eval_pipeline.repository")
    def test_no_eligible_runs_returns_zero_counts(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline, EvalPipelineResult

        mock_repo.get_eligible_runs.return_value = []
        pipeline = EvalPipeline(session=MagicMock(), provider=_StubProvider())
        result = pipeline.run_all(as_of=_CUTOFF)

        assert isinstance(result, EvalPipelineResult)
        assert result.evaluated == 0
        assert result.failed == 0
        mock_repo.upsert_eval_result.assert_not_called()

    @patch("src.research.eval_pipeline.repository")
    def test_run_single_bypasses_eligibility(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run_id = uuid.uuid4()
        run = _make_run()
        run.run_id = run_id
        output = _make_output()

        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [run, output]

        pipeline = EvalPipeline(session=session, provider=_StubProvider())
        result = pipeline.run_single(run_id)

        assert result.success is True
        assert result.run_id == run_id
        mock_repo.upsert_eval_result.assert_called_once()

    @patch("src.research.eval_pipeline.repository")
    def test_run_single_no_output_returns_failure(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run_id = uuid.uuid4()
        run = _make_run()
        run.run_id = run_id

        session = MagicMock()
        # First query returns run, second (output) returns None
        session.query.return_value.filter.return_value.first.side_effect = [run, None]

        pipeline = EvalPipeline(session=session, provider=_StubProvider())
        result = pipeline.run_single(run_id)

        assert result.success is False
        assert result.error == "no_output_row"
        mock_repo.upsert_eval_result.assert_not_called()

    @patch("src.research.eval_pipeline.repository")
    def test_run_all_twice_calls_upsert_twice(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(session=MagicMock(), provider=_StubProvider())
        pipeline.run_all(as_of=_CUTOFF)
        pipeline.run_all(as_of=_CUTOFF)

        assert mock_repo.upsert_eval_result.call_count == 2
