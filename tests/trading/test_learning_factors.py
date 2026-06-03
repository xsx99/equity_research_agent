from src.trading.reflection_pipeline import derive_learning_factor_status


def test_risk_tightening_learning_factor_can_auto_activate():
    status = derive_learning_factor_status(
        activation_policy="auto_risk_tightening",
        effect_tags=("reduce_exposure", "require_confirmation"),
    )

    assert status == "active"


def test_observation_learning_factor_stays_observation():
    status = derive_learning_factor_status(
        activation_policy="observation",
        effect_tags=("note_only",),
    )

    assert status == "observation"


def test_expansionary_learning_factor_cannot_auto_activate():
    status = derive_learning_factor_status(
        activation_policy="auto_risk_tightening",
        effect_tags=("increase_score", "expand_eligibility"),
    )

    assert status == "candidate"
