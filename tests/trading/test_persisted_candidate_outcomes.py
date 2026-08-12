from datetime import datetime, timezone

import pytest

from src.trading.outcomes.evaluator import evaluate_directional_outcome


def test_bullish_outcome_uses_raw_return_for_alpha_and_excursion():
    outcome = evaluate_directional_outcome(
        direction="bullish",
        candidate_start_price=100,
        candidate_end_price=110,
        path_high_prices=(102, 112, 110),
        path_low_prices=(98, 101, 109),
        primary_comparator_return=0.03,
        aligned_active_returns=(0.01, 0.02, 0.00),
    )

    assert outcome.directional_edge_eligible is True
    assert outcome.candidate_return == pytest.approx(0.10)
    assert outcome.alpha == pytest.approx(0.07)
    assert outcome.max_favorable_excursion == pytest.approx(0.12)
    assert outcome.max_adverse_excursion == pytest.approx(-0.02)
    assert outcome.comparator_information_ratio is not None


def test_bearish_outcome_inverts_return_alpha_and_excursions():
    outcome = evaluate_directional_outcome(
        direction="bearish",
        candidate_start_price=100,
        candidate_end_price=90,
        path_high_prices=(103, 98, 92),
        path_low_prices=(97, 88, 89),
        primary_comparator_return=-0.02,
        aligned_active_returns=(0.01, 0.00, 0.02),
    )

    assert outcome.directional_edge_eligible is True
    assert outcome.candidate_return == pytest.approx(0.10)
    assert outcome.alpha == pytest.approx(0.08)
    assert outcome.max_favorable_excursion == pytest.approx(0.12)
    assert outcome.max_adverse_excursion == pytest.approx(-0.03)


def test_neutral_outcome_is_observational_without_alpha():
    outcome = evaluate_directional_outcome(
        direction="neutral",
        candidate_start_price=100,
        candidate_end_price=105,
        path_high_prices=(106,),
        path_low_prices=(99,),
        primary_comparator_return=0.02,
        aligned_active_returns=(0.01, 0.02),
    )

    assert outcome.candidate_return == pytest.approx(0.05)
    assert outcome.alpha is None
    assert outcome.directional_edge_eligible is False
    assert outcome.evaluation_disposition == "observational"


def test_unsupported_direction_is_terminal_observational_without_text_inference():
    outcome = evaluate_directional_outcome(
        direction="risk_warning",
        candidate_start_price=100,
        candidate_end_price=95,
        path_high_prices=(102,),
        path_low_prices=(94,),
        primary_comparator_return=-0.01,
        aligned_active_returns=(0.01, -0.01),
    )

    assert outcome.alpha is None
    assert outcome.directional_edge_eligible is False
    assert outcome.evaluation_disposition == "unsupported_direction"


def test_information_ratio_uses_sample_standard_deviation():
    outcome = evaluate_directional_outcome(
        direction="long",
        candidate_start_price=100,
        candidate_end_price=100,
        path_high_prices=(100,),
        path_low_prices=(100,),
        primary_comparator_return=0.0,
        aligned_active_returns=(0.01, 0.03),
    )

    assert outcome.comparator_information_ratio == pytest.approx(22.4499443206)
