"""Economic-calendar provider helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

from src.core.logging import get_logger


logger = get_logger(__name__)


class EconomicCalendarFallback:
    """Return events from the first configured economic calendar with data."""

    def __init__(self, *providers: Any) -> None:
        self._providers = tuple(provider for provider in providers if provider is not None)

    def macro_events(self, as_of: date) -> tuple[dict[str, Any], ...]:
        for provider in self._providers:
            try:
                events = tuple(provider.macro_events(as_of))
            except Exception as exc:
                logger.warning(
                    "economic_calendar_provider_failed",
                    provider=provider.__class__.__name__,
                    error=str(exc),
                )
                continue
            if events:
                return events
        return ()
