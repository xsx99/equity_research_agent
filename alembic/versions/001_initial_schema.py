"""Initial schema for insider_trades table.

Revision ID: 001
Revises: 
Create Date: 2026-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'insider_trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('accession_number', sa.String(length=25), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('company_cik', sa.String(length=10), nullable=True),
        sa.Column('insider_name', sa.String(length=255), nullable=False),
        sa.Column('insider_title', sa.String(length=100), nullable=True),
        sa.Column('insider_cik', sa.String(length=10), nullable=True),
        sa.Column('is_director', sa.Boolean(), nullable=True),
        sa.Column('is_officer', sa.Boolean(), nullable=True),
        sa.Column('is_ten_percent_owner', sa.Boolean(), nullable=True),
        sa.Column('transaction_type', sa.String(length=5), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('shares', sa.Integer(), nullable=True),
        sa.Column('price_per_share', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('total_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('shares_owned_after', sa.BigInteger(), nullable=True),
        sa.Column('filing_date', sa.Date(), nullable=False),
        sa.Column('filing_url', sa.Text(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('accession_number')
    )
    op.create_index('ix_insider_trades_filing_date', 'insider_trades', ['filing_date'], unique=False)
    op.create_index('ix_insider_trades_insider_name', 'insider_trades', ['insider_name'], unique=False)
    op.create_index('ix_insider_trades_ticker', 'insider_trades', ['ticker'], unique=False)
    op.create_index('ix_insider_trades_transaction_date', 'insider_trades', ['transaction_date'], unique=False)
    op.create_index('ix_insider_trades_transaction_type', 'insider_trades', ['transaction_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_insider_trades_transaction_type', table_name='insider_trades')
    op.drop_index('ix_insider_trades_transaction_date', table_name='insider_trades')
    op.drop_index('ix_insider_trades_ticker', table_name='insider_trades')
    op.drop_index('ix_insider_trades_insider_name', table_name='insider_trades')
    op.drop_index('ix_insider_trades_filing_date', table_name='insider_trades')
    op.drop_table('insider_trades')
