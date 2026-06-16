"""Add social macro source rows for research signal expansion.

Revision ID: 024
Revises: 023
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_macro_items",
        sa.Column("social_macro_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=True),
        sa.Column("sentiment_direction", sa.String(length=32), nullable=True),
        sa.Column("importance_score", sa.Numeric(), nullable=True),
        sa.Column("importance_label", sa.String(length=32), nullable=True),
        sa.Column("policy_headwind_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("policy_tailwind_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("explicit_ticker_mention_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("explicit_theme_mention_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("theme_tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("company_name_mentions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_for_decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_ref", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("social_macro_item_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_social_macro_items_dedupe_key"),
    )
    op.create_index("ix_social_macro_items_available_for_decision_at", "social_macro_items", ["available_for_decision_at"], unique=False)
    op.create_index("ix_social_macro_items_category", "social_macro_items", ["category"], unique=False)
    op.create_index("ix_social_macro_items_importance_label", "social_macro_items", ["importance_label"], unique=False)
    op.create_index("ix_social_macro_items_source_key", "social_macro_items", ["source_key"], unique=False)
    op.create_index("ix_social_macro_items_ticker", "social_macro_items", ["ticker"], unique=False)
    op.create_index("ix_social_macro_items_ticker_available", "social_macro_items", ["ticker", "available_for_decision_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_social_macro_items_ticker_available", table_name="social_macro_items")
    op.drop_index("ix_social_macro_items_ticker", table_name="social_macro_items")
    op.drop_index("ix_social_macro_items_source_key", table_name="social_macro_items")
    op.drop_index("ix_social_macro_items_importance_label", table_name="social_macro_items")
    op.drop_index("ix_social_macro_items_category", table_name="social_macro_items")
    op.drop_index("ix_social_macro_items_available_for_decision_at", table_name="social_macro_items")
    op.drop_table("social_macro_items")
