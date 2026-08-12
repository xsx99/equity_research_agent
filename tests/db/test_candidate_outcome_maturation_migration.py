"""Structural contract for candidate outcome maturity migration."""
from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/033_candidate_outcome_maturation_idempotency.py"
)


def test_migration_adds_maturation_idempotency_and_manual_lineage_contracts():
    source = MIGRATION_PATH.read_text()

    assert 'revision: str = "033"' in source
    assert 'down_revision: Union[str, None] = "032"' in source
    for fragment in (
        '"evaluation_as_of_session"',
        '"uq_candidate_outcomes_maturation_checkpoint"',
        '"ix_candidate_outcomes_due_checkpoint"',
        "snapshot_type IN ('pre_open', 'manual', 'intraday')",
        '"ck_strategy_runs_snapshot_type"',
        '"ck_historical_replay_runs_snapshot_type"',
    ):
        assert fragment in source


def test_migration_downgrade_reverses_constraints_before_column_removal():
    source = MIGRATION_PATH.read_text()

    assert source.index('op.drop_constraint(\n        "uq_candidate_outcomes_maturation_checkpoint"') < source.index(
        'op.drop_column("historical_replay_runs", "evaluation_as_of_session")'
    )
