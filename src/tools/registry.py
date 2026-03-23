"""Registry for all agent-callable tools."""
from __future__ import annotations

from typing import Any

from src.tools.base import BaseTool
from src.tools.context import ToolContext


class ToolRegistry:
    """
    Holds named tool instances and dispatches LLM tool-use calls.

    Create one registry per agent configuration.  Tools are registered
    explicitly via :meth:`register`; the registry never auto-discovers
    subclasses so dependencies remain visible and grep-able.

    Example::

        registry = ToolRegistry()
        registry.register(MarketDataTool())
        registry.register(NewsDataTool())
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> "ToolRegistry":
        """Register *tool*.  Raises :exc:`ValueError` if the name is taken.

        Returns ``self`` for method chaining.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> BaseTool:
        """Return the tool registered under *name*."""
        if name not in self._tools:
            raise KeyError(f"No tool named '{name}' is registered.")
        return self._tools[name]

    def schemas(self, provider: str = "generic") -> list[dict[str, Any]]:
        """Return all tool schemas in the requested provider format."""
        return [tool.schema_for(provider) for tool in self._tools.values()]

    def dispatch(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """Look up *tool_name* and call ``run(tool_input, context)``."""
        return self.get(tool_name).run(tool_input, context)

    def names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
