"""Unit tests for src/research/eval_pipeline.py."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.evaluation import EvalOutcomeLabel
from src.db.models.research import ResearchOutput, ResearchRun, RunStatus


class TestRuleV1:
    """Exhaustive label matrix tests. No I/O required."""

    def _label(self, decision, realized, benchmark=0.01, threshold=0.01):
        from src.research.workflows.evaluation import apply_rule_v1
        return apply_rule_v1(decision, realized, benchmark, neutral_threshold=threshold)

    def test_none_realized_returns_none(self):
        assert self._label("bullish", None) is None

    def test_none_realized_bearish_returns_none(self):
        assert self._label("bearish", None) is None

    def test_none_realized_neutral_returns_none(self):
        assert self._label("neutral", None) is None

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
        assert self._label("bullish", 0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_negative_beats_benchmark_is_correct(self):
        assert self._label("bearish", -0.05, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_equals_benchmark_is_correct(self):
        assert self._label("bearish", -0.03, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_outperforms_benchmark_is_partially_correct(self):
        assert self._label("bearish", -0.01, benchmark=-0.05) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_exactly_zero_is_partially_correct(self):
        assert self._label("bearish", 0.0, benchmark=-0.01) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_positive_is_wrong_direction(self):
        assert self._label("bearish", 0.03, benchmark=-0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_bearish_none_benchmark_negative_is_partially_correct(self):
        assert self._label("bearish", -0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

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


_PRE_OPEN_AS_OF = datetime(2026, 3, 24, 13, 20, 0, tzinfo=timezone.utc)  # 9:20 ET
_POST_OPEN_AS_OF = datetime(2026, 3, 24, 15, 15, 0, tzinfo=timezone.utc)  # 11:15 ET
_EVAL_AS_OF = datetime(2026, 3, 24, 20, 10, 0, tzinfo=timezone.utc)  # 16:10 ET


def _make_run(
    ticker: str = "AAPL",
    as_of: datetime = _PRE_OPEN_AS_OF,
    input_json: dict | None = None,
) -> MagicMock:
    run = MagicMock(spec=ResearchRun)
    run.run_id = uuid.uuid4()
    run.ticker = ticker
    run.as_of = as_of
    run.status = RunStatus.SUCCEEDED.value
    run.input_json = input_json or {"price_snapshot": {"last_price": 150.0}}
    return run


def _make_output(decision: str = "bullish", time_horizon: str = "1d") -> MagicMock:
    output = MagicMock(spec=ResearchOutput)
    output.decision = decision
    output.time_horizon = time_horizon
    return output


class TestEvalPipelineSameDay:
    @patch("src.research.workflows.evaluation.fetch_price_at_or_before")
    @patch("src.research.workflows.evaluation.fetch_close_price_on_date")
    @patch("src.research.workflows.evaluation.fetch_open_to_close_return")
    @patch("src.research.workflows.evaluation.repository")
    def test_pre_open_run_uses_open_to_close_window(
        self,
        mock_repo,
        mock_open_to_close,
        mock_close_price,
        mock_price_at_or_before,
    ):
        from src.research.workflows.evaluation import EvalPipeline

        run = _make_run(as_of=_PRE_OPEN_AS_OF)
        output = _make_output()
        mock_repo.get_same_day_eval_candidates.return_value = [(run, output)]

        def _open_to_close_side_effect(ticker, trade_date, provider=None):
            return 0.03 if ticker == "SPY" else 0.05

        mock_open_to_close.side_effect = _open_to_close_side_effect

        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock(), benchmark_symbol="SPY")
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        mock_repo.upsert_eval_result.assert_called_once()
        kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert kwargs["horizon_days"] == 1
        assert kwargs["outcome_label"] == EvalOutcomeLabel.CORRECT.value
        assert kwargs["evaluation_params"]["price_window"] == "open_to_close"
        assert kwargs["evaluation_params"]["entry_price_source"] == "session_open"
        assert kwargs["evaluation_params"]["benchmark_entry_price_source"] == "session_open"
        assert result.evaluated == 1
        mock_close_price.assert_not_called()
        mock_price_at_or_before.assert_not_called()

    @patch("src.research.workflows.evaluation.fetch_price_at_or_before")
    @patch("src.research.workflows.evaluation.fetch_close_price_on_date")
    @patch("src.research.workflows.evaluation.fetch_open_to_close_return")
    @patch("src.research.workflows.evaluation.repository")
    def test_post_open_manual_run_uses_run_snapshot_price_to_close(
        self,
        mock_repo,
        mock_open_to_close,
        mock_close_price,
        mock_price_at_or_before,
    ):
        from src.research.workflows.evaluation import EvalPipeline

        run = _make_run(
            as_of=_POST_OPEN_AS_OF,
            input_json={"price_snapshot": {"last_price": 150.0}},
        )
        output = _make_output()
        mock_repo.get_same_day_eval_candidates.return_value = [(run, output)]

        def _close_price_side_effect(ticker, trade_date, provider=None):
            return 512.0 if ticker == "SPY" else 153.0

        mock_close_price.side_effect = _close_price_side_effect
        mock_price_at_or_before.return_value = 500.0

        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock(), benchmark_symbol="SPY")
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert kwargs["realized_return"] == pytest.approx((153.0 / 150.0) - 1)
        assert kwargs["benchmark_return"] == pytest.approx((512.0 / 500.0) - 1)
        assert kwargs["outcome_label"] == EvalOutcomeLabel.PARTIALLY_CORRECT.value
        assert kwargs["evaluation_params"]["price_window"] == "run_time_price_to_close"
        assert kwargs["evaluation_params"]["entry_price_source"] == "research_input_last_price"
        assert kwargs["evaluation_params"]["benchmark_entry_price_source"] == "market_price_at_or_before_run_time"
        assert result.evaluated == 1
        mock_open_to_close.assert_not_called()

    @patch("src.research.workflows.evaluation.fetch_price_at_or_before")
    @patch("src.research.workflows.evaluation.fetch_close_price_on_date")
    @patch("src.research.workflows.evaluation.fetch_open_to_close_return")
    @patch("src.research.workflows.evaluation.repository")
    def test_post_open_manual_run_missing_entry_price_writes_null_outcome(
        self,
        mock_repo,
        mock_open_to_close,
        mock_close_price,
        mock_price_at_or_before,
    ):
        from src.research.workflows.evaluation import EvalPipeline

        run = _make_run(
            as_of=_POST_OPEN_AS_OF,
            input_json={"price_snapshot": {"last_price": None}},
        )
        output = _make_output()
        mock_repo.get_same_day_eval_candidates.return_value = [(run, output)]
        mock_close_price.return_value = 153.0
        mock_price_at_or_before.return_value = 500.0

        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock(), benchmark_symbol="SPY")
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert kwargs["realized_return"] is None
        assert kwargs["outcome_label"] is None
        assert kwargs["evaluation_params"]["price_window"] == "run_time_price_to_close"
        assert result.evaluated == 1
        mock_open_to_close.assert_not_called()

    @patch("src.research.workflows.evaluation.repository")
    def test_no_candidates_returns_zero_counts(self, mock_repo):
        from src.research.workflows.evaluation import EvalPipeline, EvalPipelineResult

        mock_repo.get_same_day_eval_candidates.return_value = []
        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock())
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        assert isinstance(result, EvalPipelineResult)
        assert result.evaluated == 0
        assert result.failed == 0
        mock_repo.upsert_eval_result.assert_not_called()

    @patch("src.research.workflows.evaluation.fetch_open_to_close_return")
    @patch("src.research.workflows.evaluation.repository")
    def test_run_single_bypasses_candidate_selection(self, mock_repo, mock_open_to_close):
        from src.research.workflows.evaluation import EvalPipeline

        run_id = uuid.uuid4()
        run = _make_run(as_of=_PRE_OPEN_AS_OF)
        run.run_id = run_id
        output = _make_output()
        mock_open_to_close.side_effect = lambda ticker, trade_date, provider=None: 0.03 if ticker == "SPY" else 0.05

        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [run, output]

        pipeline = EvalPipeline(session=session, provider=MagicMock(), benchmark_symbol="SPY")
        result = pipeline.run_single(run_id)

        assert result.success is True
        assert result.run_id == run_id
        mock_repo.upsert_eval_result.assert_called_once()

    @patch("src.research.workflows.evaluation.fetch_open_to_close_return")
    @patch("src.research.workflows.evaluation.repository")
    def test_upsert_exception_does_not_abort_batch(self, mock_repo, mock_open_to_close):
        from src.research.workflows.evaluation import EvalPipeline

        run1 = _make_run("AAPL", as_of=_PRE_OPEN_AS_OF)
        run2 = _make_run("MSFT", as_of=_PRE_OPEN_AS_OF)
        output1 = _make_output()
        output2 = _make_output()
        mock_repo.get_same_day_eval_candidates.return_value = [(run1, output1), (run2, output2)]
        mock_open_to_close.side_effect = lambda ticker, trade_date, provider=None: 0.03 if ticker == "SPY" else 0.05

        call_count = {"n": 0}

        def _upsert_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("db_constraint_error")

        mock_repo.upsert_eval_result.side_effect = _upsert_side_effect

        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock(), benchmark_symbol="SPY")
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        assert result.failed == 1
        assert result.evaluated == 1
        assert len(result.ticker_results) == 2

    @patch("src.research.workflows.evaluation.repository")
    def test_invalid_horizon_increments_skipped(self, mock_repo):
        from src.research.workflows.evaluation import EvalPipeline

        run = _make_run()
        output = _make_output(time_horizon="invalid_horizon")
        mock_repo.get_same_day_eval_candidates.return_value = [(run, output)]

        pipeline = EvalPipeline(session=MagicMock(), provider=MagicMock())
        result = pipeline.run_all(as_of=_EVAL_AS_OF)

        assert result.skipped == 1
        assert result.failed == 0
        assert result.evaluated == 0
        mock_repo.upsert_eval_result.assert_not_called()
