from datetime import date, datetime, timezone

import pytest

from src.trading.outcomes.horizons import OutcomeHorizonPolicy, UnsupportedOutcomeHorizon


@pytest.mark.parametrize(
    ("typical_horizon", "interim_offset", "final_offset"),
    (
        ("intraday-2d", 1, 2),
        ("intraday-3d", 1, 3),
        ("1d-2w", 1, 10),
        ("2d-3w", 2, 15),
        ("2d-4w", 2, 20),
        ("3d-4w", 3, 20),
        ("1-6w", 5, 30),
        ("1-8w", 5, 40),
        ("2-8w", 10, 40),
        ("2w-8w", 10, 40),
        ("2w-3m", 10, 63),
        ("1-3m", 21, 63),
        ("2-12w", 10, 60),
        ("intraday-3m", 1, 63),
        ("intraday-4w", 1, 20),
        ("multi-month+", 63, 126),
    ),
)
def test_policy_exposes_every_approved_canonical_horizon(
    typical_horizon: str,
    interim_offset: int,
    final_offset: int,
):
    policy = OutcomeHorizonPolicy()

    checkpoints = policy.offsets_for(typical_horizon)

    assert checkpoints.interim_session_offset == interim_offset
    assert checkpoints.final_session_offset == final_offset


def test_policy_uses_xnys_sessions_across_holiday_and_weekend():
    policy = OutcomeHorizonPolicy()

    checkpoints = policy.checkpoints_for(
        typical_horizon="intraday-2d",
        decision_session=date(2026, 7, 2),
    )

    assert checkpoints.interim_session == date(2026, 7, 6)
    assert checkpoints.final_session == date(2026, 7, 7)


def test_policy_rejects_unknown_horizon_without_guessing():
    with pytest.raises(UnsupportedOutcomeHorizon, match="unsupported_horizon:overnight"):
        OutcomeHorizonPolicy().offsets_for("overnight")


def test_session_close_uses_xnys_dst_offset():
    policy = OutcomeHorizonPolicy()

    assert policy.session_close(date(2026, 7, 6)) == datetime(
        2026, 7, 6, 20, 0, tzinfo=timezone.utc
    )
    assert policy.session_close(date(2026, 12, 7)) == datetime(
        2026, 12, 7, 21, 0, tzinfo=timezone.utc
    )
