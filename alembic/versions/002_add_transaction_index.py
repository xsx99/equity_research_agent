"""Add transaction_index and adjust uniqueness.

Revision ID: 002
Revises: 001
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'insider_trades',
        sa.Column('transaction_index', sa.Integer(), nullable=False, server_default='0')
    )

    # Drop old unique constraint on accession_number
    op.execute(
        'ALTER TABLE insider_trades '
        'DROP CONSTRAINT IF EXISTS insider_trades_accession_number_key'
    )

    op.create_unique_constraint(
        'uq_insider_trades_accession_txn_index',
        'insider_trades',
        ['accession_number', 'transaction_index']
    )

    op.alter_column('insider_trades', 'transaction_index', server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        'uq_insider_trades_accession_txn_index',
        'insider_trades',
        type_='unique'
    )

    op.create_unique_constraint(
        'insider_trades_accession_number_key',
        'insider_trades',
        ['accession_number']
    )

    op.drop_column('insider_trades', 'transaction_index')
