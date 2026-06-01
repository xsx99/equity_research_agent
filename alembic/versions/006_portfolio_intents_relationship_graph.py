"""Add portfolio intents and relationship graph tables.

Revision ID: 006
Revises: 005
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_intents",
        sa.Column("portfolio_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("intent_type", sa.String(length=64), nullable=False),
        sa.Column("target_weight", sa.Numeric(), nullable=False),
        sa.Column("max_weight", sa.Numeric(), nullable=False),
        sa.Column("add_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trim_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thesis_invalidators_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "allowed_tactical_interactions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "intent_type IN ('core_growth', 'core_index', 'core_theme', 'core_cash_like')",
            name="ck_portfolio_intents_intent_type",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'paused', 'retired')",
            name="ck_portfolio_intents_lifecycle_status",
        ),
        sa.CheckConstraint("target_weight >= 0", name="ck_portfolio_intents_target_weight"),
        sa.CheckConstraint("max_weight >= target_weight", name="ck_portfolio_intents_max_weight"),
        sa.PrimaryKeyConstraint("portfolio_intent_id"),
    )
    op.create_index("ix_portfolio_intents_lifecycle_status", "portfolio_intents", ["lifecycle_status"], unique=False)
    op.create_index("ix_portfolio_intents_ticker", "portfolio_intents", ["ticker"], unique=False)

    op.create_table(
        "ticker_relationships",
        sa.Column("ticker_relationship_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_ticker", sa.String(length=16), nullable=False),
        sa.Column("target_ticker", sa.String(length=16), nullable=False),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("theme_id", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("strength_score", sa.Numeric(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_uses_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            (
                "relationship_type IN ('peer', 'customer', 'supplier', 'competitor', "
                "'sector_leader', 'etf_component', 'theme_leader', 'theme_constituent')"
            ),
            name="ck_ticker_relationships_relationship_type",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_ticker_relationships_confidence"),
        sa.CheckConstraint(
            "strength_score >= 0 AND strength_score <= 1",
            name="ck_ticker_relationships_strength_score",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_ticker_relationships_valid_window",
        ),
        sa.PrimaryKeyConstraint("ticker_relationship_id"),
    )
    op.create_index("ix_ticker_relationships_source_ticker", "ticker_relationships", ["source_ticker"], unique=False)
    op.create_index("ix_ticker_relationships_target_ticker", "ticker_relationships", ["target_ticker"], unique=False)
    op.create_index("ix_ticker_relationships_theme_id", "ticker_relationships", ["theme_id"], unique=False)

    op.create_table(
        "peer_baskets",
        sa.Column("peer_basket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("basket_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("members_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("construction_method", sa.String(length=64), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("peer_basket_id"),
        sa.UniqueConstraint("basket_key", "version", "trade_date", name="uq_peer_baskets_key_version_trade_date"),
    )
    op.create_index("ix_peer_baskets_basket_key_version", "peer_baskets", ["basket_key", "version"], unique=False)
    op.create_index("ix_peer_baskets_trade_date", "peer_baskets", ["trade_date"], unique=False)

    op.create_table(
        "theme_taxonomy",
        sa.Column("theme_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("parent_theme_id", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'retired')",
            name="ck_theme_taxonomy_lifecycle_status",
        ),
        sa.PrimaryKeyConstraint("theme_id"),
    )
    op.create_index("ix_theme_taxonomy_lifecycle_status", "theme_taxonomy", ["lifecycle_status"], unique=False)
    op.create_index("ix_theme_taxonomy_parent_theme_id", "theme_taxonomy", ["parent_theme_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_theme_taxonomy_parent_theme_id", table_name="theme_taxonomy")
    op.drop_index("ix_theme_taxonomy_lifecycle_status", table_name="theme_taxonomy")
    op.drop_table("theme_taxonomy")

    op.drop_index("ix_peer_baskets_trade_date", table_name="peer_baskets")
    op.drop_index("ix_peer_baskets_basket_key_version", table_name="peer_baskets")
    op.drop_table("peer_baskets")

    op.drop_index("ix_ticker_relationships_theme_id", table_name="ticker_relationships")
    op.drop_index("ix_ticker_relationships_target_ticker", table_name="ticker_relationships")
    op.drop_index("ix_ticker_relationships_source_ticker", table_name="ticker_relationships")
    op.drop_table("ticker_relationships")

    op.drop_index("ix_portfolio_intents_ticker", table_name="portfolio_intents")
    op.drop_index("ix_portfolio_intents_lifecycle_status", table_name="portfolio_intents")
    op.drop_table("portfolio_intents")
