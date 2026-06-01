import pytest

from src.trading.signals import compute_relative_strength


def test_compute_relative_strength_subtracts_benchmark_return():
    assert compute_relative_strength(0.12, 0.05) == pytest.approx(0.07)


def test_compute_relative_strength_returns_none_when_input_missing():
    assert compute_relative_strength(None, 0.05) is None
    assert compute_relative_strength(0.12, None) is None
