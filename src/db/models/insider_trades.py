"""Insider trading ORM model."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class InsiderTrade(Base):
    """Insider trading transaction record."""

    __tablename__ = "insider_trades"

    id = Column(Integer, primary_key=True)

    # SEC identifiers
    accession_number = Column(String(25), nullable=False)
    transaction_index = Column(Integer, nullable=False, default=0)

    # Company
    ticker = Column(String(10), nullable=False, index=True)
    company_name = Column(String(255))
    company_cik = Column(String(10))

    # Insider
    insider_name = Column(String(255), nullable=False, index=True)
    insider_title = Column(String(100))
    insider_cik = Column(String(10))
    is_director = Column(Boolean)
    is_officer = Column(Boolean)
    is_ten_percent_owner = Column(Boolean)

    # Transaction
    transaction_type = Column(String(5), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    shares = Column(Integer)
    price_per_share = Column(Numeric(12, 4))
    total_value = Column(Numeric(15, 2))

    # Holdings after transaction
    shares_owned_after = Column(BigInteger)

    # Metadata
    filing_date = Column(Date, nullable=False, index=True)
    filing_url = Column(Text)
    raw_data = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "accession_number",
            "transaction_index",
            name="uq_insider_trades_accession_txn_index",
        ),
    )

    def __repr__(self):
        return f"<InsiderTrade {self.ticker} {self.insider_name} {self.transaction_type} {self.shares}>"
