from datetime import datetime, timezone

from src.trading.outcomes.lineage import persisted_candidate_maturation_run_id


def test_persisted_candidate_maturation_run_id_is_stable_for_exact_lineage_tuple():
    source_decision_time = datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc)
    evaluation_as_of_session = datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc)

    first = persisted_candidate_maturation_run_id(
        source_decision_time=source_decision_time,
        snapshot_type="manual",
        evaluation_as_of_session=evaluation_as_of_session,
    )
    retry = persisted_candidate_maturation_run_id(
        source_decision_time=source_decision_time,
        snapshot_type="manual",
        evaluation_as_of_session=evaluation_as_of_session,
    )

    assert first == retry


def test_persisted_candidate_maturation_run_id_changes_for_new_evaluation_session():
    source_decision_time = datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc)

    prior = persisted_candidate_maturation_run_id(
        source_decision_time=source_decision_time,
        snapshot_type="pre_open",
        evaluation_as_of_session=datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc),
    )
    later = persisted_candidate_maturation_run_id(
        source_decision_time=source_decision_time,
        snapshot_type="pre_open",
        evaluation_as_of_session=datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc),
    )

    assert prior != later
