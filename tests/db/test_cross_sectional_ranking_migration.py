"""Structural contract for the cross-sectional ranking migration."""
from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/032_cross_sectional_relative_strength_ranking.py"
)


def test_cross_sectional_ranking_migration_creates_and_removes_complete_schema():
    source = MIGRATION_PATH.read_text()

    assert 'revision: str = "032"' in source
    assert 'down_revision: Union[str, None] = "031"' in source
    for fragment in (
        'op.create_table(\n        "universe_ranking_runs"',
        'op.create_table(\n        "universe_rankings"',
        '"uq_universe_rankings_run_ticker"',
        '"ix_universe_rankings_run_rank"',
        '"ix_universe_rankings_ticker_decision_time"',
        '"ix_universe_rankings_automatic_shortlist"',
        '"universe_ranking_run_id"',
        '"universe_ranking_id"',
        'op.drop_table("universe_rankings")',
        'op.drop_table("universe_ranking_runs")',
    ):
        assert fragment in source

    assert source.index('op.drop_column("candidate_scores", "universe_ranking_id")') < source.index(
        'op.drop_table("universe_rankings")'
    )
