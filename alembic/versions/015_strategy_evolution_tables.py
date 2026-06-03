"""Add PR10 strategy evolution tables.

Revision ID: 015
Revises: 014
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_proposals",
        sa.Column("strategy_proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("prompt_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_status", sa.String(length=32), nullable=False),
        sa.Column("proposed_strategy_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("proposed_lifecycle_status", sa.String(length=16), nullable=True),
        sa.Column("duplicate_of_strategy_id", sa.String(length=64), nullable=True),
        sa.Column("rejection_reason", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="reflection_learning"),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("proposal_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "proposal_status IN ('accepted', 'duplicate_rejected', 'proposal_failed')",
            name="ck_strategy_proposals_status",
        ),
        sa.CheckConstraint(
            "proposed_lifecycle_status IS NULL OR proposed_lifecycle_status "
            "IN ('candidate', 'shadow', 'experimental', 'active', 'retired')",
            name="ck_strategy_proposals_lifecycle_status",
        ),
        sa.CheckConstraint(
            "source IN ('seed', 'reflection_learning', 'manual')",
            name="ck_strategy_proposals_source",
        ),
        sa.ForeignKeyConstraint(["prompt_run_id"], ["llm_prompt_runs.prompt_run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("strategy_proposal_id"),
    )
    op.create_index("ix_strategy_proposals_trade_date", "strategy_proposals", ["trade_date"], unique=False)
    op.create_index("ix_strategy_proposals_prompt_run_id", "strategy_proposals", ["prompt_run_id"], unique=False)
    op.create_index("ix_strategy_proposals_status", "strategy_proposals", ["proposal_status"], unique=False)
    op.create_index(
        "ix_strategy_proposals_proposed_strategy_id",
        "strategy_proposals",
        ["proposed_strategy_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_proposals_proposed_lifecycle_status",
        "strategy_proposals",
        ["proposed_lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_proposals_duplicate_of_strategy_id",
        "strategy_proposals",
        ["duplicate_of_strategy_id"],
        unique=False,
    )
    op.create_index("ix_strategy_proposals_source", "strategy_proposals", ["source"], unique=False)

    op.create_table(
        "strategy_evaluation_results",
        sa.Column("strategy_evaluation_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_definition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_type", sa.String(length=64), nullable=False),
        sa.Column("evaluation_status", sa.String(length=16), nullable=False),
        sa.Column("prior_lifecycle_status", sa.String(length=16), nullable=True),
        sa.Column("new_lifecycle_status", sa.String(length=16), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "evaluation_status IN ('observed', 'promoted', 'rejected', 'retired')",
            name="ck_strategy_evaluation_results_status",
        ),
        sa.CheckConstraint(
            "prior_lifecycle_status IS NULL OR prior_lifecycle_status "
            "IN ('candidate', 'shadow', 'experimental', 'active', 'retired')",
            name="ck_strategy_evaluation_results_prior_status",
        ),
        sa.CheckConstraint(
            "new_lifecycle_status IS NULL OR new_lifecycle_status "
            "IN ('candidate', 'shadow', 'experimental', 'active', 'retired')",
            name="ck_strategy_evaluation_results_new_status",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_definition_id"],
            ["strategy_definitions.strategy_definition_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_proposal_id"],
            ["strategy_proposals.strategy_proposal_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("strategy_evaluation_result_id"),
    )
    op.create_index(
        "ix_strategy_evaluation_results_strategy_definition_id",
        "strategy_evaluation_results",
        ["strategy_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_evaluation_results_strategy_proposal_id",
        "strategy_evaluation_results",
        ["strategy_proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_evaluation_results_strategy_id",
        "strategy_evaluation_results",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_evaluation_results_evaluation_type",
        "strategy_evaluation_results",
        ["evaluation_type"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_evaluation_results_evaluation_status",
        "strategy_evaluation_results",
        ["evaluation_status"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_evaluation_results_new_lifecycle_status",
        "strategy_evaluation_results",
        ["new_lifecycle_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_evaluation_results_new_lifecycle_status", table_name="strategy_evaluation_results")
    op.drop_index("ix_strategy_evaluation_results_evaluation_status", table_name="strategy_evaluation_results")
    op.drop_index("ix_strategy_evaluation_results_evaluation_type", table_name="strategy_evaluation_results")
    op.drop_index("ix_strategy_evaluation_results_strategy_id", table_name="strategy_evaluation_results")
    op.drop_index("ix_strategy_evaluation_results_strategy_proposal_id", table_name="strategy_evaluation_results")
    op.drop_index("ix_strategy_evaluation_results_strategy_definition_id", table_name="strategy_evaluation_results")
    op.drop_table("strategy_evaluation_results")

    op.drop_index("ix_strategy_proposals_source", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_duplicate_of_strategy_id", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_proposed_lifecycle_status", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_proposed_strategy_id", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_status", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_prompt_run_id", table_name="strategy_proposals")
    op.drop_index("ix_strategy_proposals_trade_date", table_name="strategy_proposals")
    op.drop_table("strategy_proposals")
