"""Enforce one active manual review request per ticker.

Revision ID: 023
Revises: 021
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                manual_ticker_request_id,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY created_at DESC, manual_ticker_request_id DESC
                ) AS row_number
            FROM manual_ticker_requests
            WHERE status = 'active'
        )
        UPDATE manual_ticker_requests AS requests
        SET
            status = 'cancelled',
            cancelled_at = COALESCE(requests.cancelled_at, CURRENT_TIMESTAMP)
        FROM ranked
        WHERE requests.manual_ticker_request_id = ranked.manual_ticker_request_id
          AND ranked.row_number > 1
        """
    )
    op.create_index(
        "uq_manual_ticker_requests_active_ticker",
        "manual_ticker_requests",
        ["ticker"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_manual_ticker_requests_active_ticker", table_name="manual_ticker_requests")
