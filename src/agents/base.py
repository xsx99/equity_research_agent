"""Abstract base class for all LLM agents."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional

from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry
from src.prompts.registry import PromptRegistry


@dataclass
class AgentResult:
    """
    Standardised result returned by any agent run.

    Attributes:
        prompt_id:      Logical prompt identifier used for this run, e.g. ``"research"``.
        prompt_version: Prompt version used, e.g. ``"v1"``.
        model_name:     LLM model name used for the run.
        input_data:     The raw input payload passed to the agent.
        output_data:    The validated structured output, or ``None`` on failure.
        error:          Error message if the run failed, otherwise ``None``.
        success:        ``True`` when the run completed without errors.
    """

    prompt_id: str
    prompt_version: str
    model_name: str
    input_data: dict[str, Any]
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(abc.ABC):
    """
    Abstract base for all LLM agents.

    Agents receive a :class:`~src.tools.registry.ToolRegistry` and a
    :class:`~src.prompts.registry.PromptRegistry` at construction time.
    Each :meth:`run` call receives a :class:`~src.tools.context.ToolContext`
    scoped to that single invocation (carrying the DB session, etc.).

    Subclasses must implement:

    * :meth:`run` — the main entry point.
    * :meth:`_build_prompt` — assembles the final prompt string from a
      validated payload and a :class:`~src.prompts.registry.Prompt` template.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        prompt_registry: PromptRegistry,
        *,
        model_name: str,
    ) -> None:
        self.tool_registry = tool_registry
        self.prompt_registry = prompt_registry
        self.model_name = model_name

    @abc.abstractmethod
    def run(self, input_payload: dict[str, Any], context: ToolContext) -> AgentResult:
        """
        Execute one agent turn.

        *input_payload* is an agent-specific dict (validated inside the
        concrete implementation).  *context* carries the DB session and
        any runtime config.  Returns an :class:`AgentResult`.
        """
        ...

    @abc.abstractmethod
    def _build_prompt(self, payload: Any, template: str) -> str:
        """Assemble the final prompt string from a validated payload and template text."""
        ...
