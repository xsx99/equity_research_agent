"""Agent-callable global context tool wrapper."""
from __future__ import annotations

from typing import Any, Optional

from src.providers.global_context import (
    MacroIndicatorProvider,
    NewsFeedProvider,
    get_global_context,
)
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

__all__ = ["GlobalContextTool", "get_global_context"]


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

