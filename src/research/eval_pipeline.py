"""Evaluation pipeline — batch orchestration for scoring matured research runs.

Responsible for:
- Querying succeeded runs whose time_horizon window has elapsed.
- Fetching realized return (ticker) and benchmark return (SPY by default).
- Applying rule_v1 labeling.
- Upserting EvalResult rows via the repository layer.

Does not commit; callers own transaction boundaries.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models.evaluation import EvalOutcomeLabel, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon
from src.research import repository
from src.tools.market_data import AlpacaMarketDataProvider, MarketDataProvider, fetch_return_over_range

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure labeling function
# ---------------------------------------------------------------------------


def apply_rule_v1(
    decision: str,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    neutral_threshold: float = 0.01,
) -> Optional[str]:
    """Apply rule_v1 label matrix.

    Returns None when realized_return is None (market data unavailable).
    When benchmark_return is None, bullish/bearish cannot achieve 'correct'
    (defaults to 'partially_correct' for correct-direction moves).
    """
    if realized_return is None:
        return None

    if decision == "bullish":
        if realized_return < 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return > 0
            and benchmark_return is not None
            and realized_return >= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    if decision == "bearish":
        if realized_return > 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return < 0
            and benchmark_return is not None
            and realized_return <= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # neutral or abstain
    if abs(realized_return) > neutral_threshold:
        return EvalOutcomeLabel.WRONG_DIRECTION.value
    return EvalOutcomeLabel.UNINFORMATIVE.value
