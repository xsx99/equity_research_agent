"""Compatibility shim for SQLAlchemy-backed manual review helpers."""
from __future__ import annotations

import sys

from src.trading.phases.manual_review import sqlalchemy as _canonical

ManualReviewAuditRow = _canonical.ManualReviewAuditRow
SQLAlchemyManualTickerRequestService = _canonical.SQLAlchemyManualTickerRequestService

__all__ = [
    "ManualReviewAuditRow",
    "SQLAlchemyManualTickerRequestService",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
