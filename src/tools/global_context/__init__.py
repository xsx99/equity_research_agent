"""Global macro/context providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from src.core.logging import get_logger
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext
from src.tools.global_context.ap_news_provider import APWorldNewsProvider
from src.tools.global_context.fred_provider import FredMacroDataProvider
from src.tools.global_context.helpers import (
    _empty_indicators_from_fred,
    _filter_geopolitical_updates,
    _filter_official_updates,
    _filter_trump_updates,
    _normalized_datetime,
)
from src.tools.global_context.types import (
    GlobalContextSnapshot,
    GlobalNewsItem,
    MacroIndicatorProvider,
    MacroIndicatorValue,
    NewsFeedProvider,
    _FRED_SERIES,
)
from src.tools.global_context.whitehouse_provider import WhiteHouseUpdatesProvider

__all__ = [
    "APWorldNewsProvider",
    "FredMacroDataProvider",
    "GlobalContextSnapshot",
    "GlobalContextTool",
    "GlobalNewsItem",
    "MacroIndicatorProvider",
    "MacroIndicatorValue",
    "NewsFeedProvider",
    "WhiteHouseUpdatesProvider",
    "get_global_context",
]

logger = get_logger(__name__)


def get_global_context(
    *,
    as_of: Optional[Any] = None,
    limit: int = 5,
    macro_provider: Optional[MacroIndicatorProvider] = None,
    official_updates_provider: Optional[NewsFeedProvider] = None,
    trump_updates_provider: Optional[NewsFeedProvider] = None,
    geopolitical_provider: Optional[NewsFeedProvider] = None,
    include_official_updates: bool = False,
) -> GlobalContextSnapshot:
    """Build the replayable global context snapshot."""
    snapshot_as_of = _normalized_datetime(as_of)
    bounded_limit = max(1, min(limit, 5))

    macro = macro_provider or FredMacroDataProvider()
    official = official_updates_provider or WhiteHouseUpdatesProvider()
    trump = trump_updates_provider
    geopolitical = geopolitical_provider or APWorldNewsProvider()

    try:
        indicators = macro.fetch_indicators(snapshot_as_of)
    except Exception as exc:
        logger.warning("global_context_macro_failed", error=str(exc))
        indicators = _empty_indicators_from_fred()

    official_candidates: list[GlobalNewsItem] = []
    if include_official_updates or trump is None:
        try:
            official_candidates = official.fetch_recent(max(bounded_limit * 3, 15))
        except Exception as exc:
            logger.warning("global_context_official_updates_failed", error=str(exc))

    official_updates = (
        _filter_official_updates(official_candidates, as_of=snapshot_as_of, limit=bounded_limit)
        if include_official_updates else []
    )

    if trump is None:
        trump_candidates = official_candidates
    else:
        try:
            trump_candidates = trump.fetch_recent(max(bounded_limit * 3, 15))
        except Exception as exc:
            logger.warning("global_context_trump_updates_failed", error=str(exc))
            trump_candidates = []
    trump_updates = _filter_trump_updates(trump_candidates, as_of=snapshot_as_of, limit=bounded_limit)

    try:
        geopolitical_candidates = geopolitical.fetch_recent(max(bounded_limit * 3, 15))
    except Exception as exc:
        logger.warning("global_context_geopolitical_failed", error=str(exc))
        geopolitical_candidates = []
    geopolitical_news = _filter_geopolitical_updates(geopolitical_candidates, as_of=snapshot_as_of, limit=bounded_limit)

    return {
        "as_of": snapshot_as_of.isoformat(),
        "indicators": indicators,
        "official_updates": official_updates[:bounded_limit],
        "trump_updates": trump_updates[:bounded_limit],
        "geopolitical_news": geopolitical_news[:bounded_limit],
    }


class GlobalContextTool(BaseTool):
    """Fetch a replayable global macro/news context block."""

    name = "get_global_context"

    def __init__(
        self,
        *,
        macro_provider: Optional[MacroIndicatorProvider] = None,
        official_updates_provider: Optional[NewsFeedProvider] = None,
        trump_updates_provider: Optional[NewsFeedProvider] = None,
        geopolitical_provider: Optional[NewsFeedProvider] = None,
        include_official_updates: bool = False,
    ) -> None:
        self._macro_provider = macro_provider
        self._official_updates_provider = official_updates_provider
        self._trump_updates_provider = trump_updates_provider
        self._geopolitical_provider = geopolitical_provider
        self._include_official_updates = include_official_updates

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch a replayable global context snapshot including macro "
                "indicators, official US government updates, Trump-related "
                "official updates, and geopolitical news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "Optional ISO-8601 timestamp for the snapshot."},
                    "limit": {"type": "integer", "description": "Maximum items per news bucket (1-5, default 5).", "default": 5},
                },
                "required": [],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        try:
            return get_global_context(
                as_of=input.get("as_of"),
                limit=int(input.get("limit", 5)),
                macro_provider=self._macro_provider,
                official_updates_provider=self._official_updates_provider,
                trump_updates_provider=self._trump_updates_provider,
                geopolitical_provider=self._geopolitical_provider,
                include_official_updates=self._include_official_updates,
            )
        except Exception as exc:
            raise ToolError(str(exc), tool_name=self.name) from exc
