"""Drop dead persistence tables that production never uses."""
from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_learning_factor_applications_application_scope", table_name="learning_factor_applications")
    op.drop_index("ix_learning_factor_applications_trading_decision_id", table_name="learning_factor_applications")
    op.drop_index("ix_learning_factor_applications_learning_factor_id", table_name="learning_factor_applications")
    op.drop_table("learning_factor_applications")

    op.drop_index("ix_macro_readthrough_events_ticker_available", table_name="macro_readthrough_events")
    op.drop_index("ix_macro_readthrough_events_source_ticker", table_name="macro_readthrough_events")
    op.drop_index("ix_macro_readthrough_events_event_time", table_name="macro_readthrough_events")
    op.drop_index("ix_macro_readthrough_events_available_for_decision_at", table_name="macro_readthrough_events")
    op.drop_table("macro_readthrough_events")


def downgrade() -> None:
    raise NotImplementedError(
        "Irreversible cleanup migration. Restore the tables from migrations 014, 022, and 025 if rollback is required."
    )
