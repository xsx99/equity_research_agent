"""Per-invocation context threaded through all tool calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    """
    Per-request context passed to every :meth:`BaseTool.run` call.

    The ``session`` is optional — tools that call only external HTTP APIs
    (market data, news) do not need a database session.  Tools that query
    the database (insider queries) require one.

    ``config`` carries any runtime overrides the caller wants to expose,
    such as API key overrides, dry-run flags, or trace IDs.
    """

    session: Optional[Session] = None
    config: dict[str, Any] = field(default_factory=dict)
