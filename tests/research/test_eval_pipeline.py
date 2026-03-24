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
