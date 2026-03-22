"""Watchlist ORM model."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class Watchlist(Base):
    """Tracked ticker list for research runs."""

    __tablename__ = "watchlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<Watchlist {self.ticker} active={self.is_active}>"
