"""Abstract base class for all agent-callable tools."""
from __future__ import annotations

import abc
from typing import Any

from src.tools.context import ToolContext


class ToolError(Exception):
    """Raised when a tool cannot complete for a known domain reason."""

    def __init__(self, message: str, tool_name: str = "") -> None:
        super().__init__(message)
        self.tool_name = tool_name


class BaseTool(abc.ABC):
    """
    Abstract base for all tools callable by LLM agents.

    Each concrete tool must:

    1. Declare a unique :attr:`name` class attribute.
    2. Implement :attr:`anthropic_schema` returning the Anthropic tool-use
       schema dict (name, description, input_schema).
    3. Implement :meth:`run` to execute the tool logic given parsed input
       and a per-request :class:`~src.tools.context.ToolContext`.
    """

    name: str  # Override as a class attribute in every subclass

    @property
    @abc.abstractmethod
    def anthropic_schema(self) -> dict[str, Any]:
        """
        Return the Anthropic tool-use schema dict::

            {
                "name": "tool_name",
                "description": "...",
                "input_schema": {
                    "type": "object",
                    "properties": {...},
                    "required": [...],
                },
            }
        """
        ...

    @abc.abstractmethod
    def run(self, input: dict[str, Any], context: ToolContext) -> Any:
        """
        Execute the tool.

        *input* is the parsed tool-use arguments from the LLM (or a direct
        caller).  *context* carries the DB session and any runtime config.

        Returns a JSON-serialisable value (dict, list, str, or number).
        Raise :class:`ToolError` for known domain failures.
        """
        ...
