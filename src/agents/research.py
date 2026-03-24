"""Research agent — structured equity research from insider trading data."""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.base import AgentResult, BaseAgent
from src.core import config as app_config
from src.prompts.registry import PromptRegistry
from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry
from src.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL_NAME = app_config.RESEARCH_MODEL_NAME
DEFAULT_PROMPT_VERSION = "v1"

# Type aliases for injectable dependencies (simplifies testing)
AgentRunner = Callable[[str, str], Any]


# ---------------------------------------------------------------------------
# Pydantic input / output schemas
# ---------------------------------------------------------------------------


class ResearchPriceSnapshot(BaseModel):
    """Price snapshot passed as part of the research input."""

    model_config = ConfigDict(extra="forbid")

    last_price: Optional[float] = None
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_since_market_open: Optional[float] = None


class ResearchContext(BaseModel):
    """Optional contextual fields for the research input."""

    model_config = ConfigDict(extra="forbid")

    sector: Optional[str] = None
    earnings_in_days: Optional[int] = None


class ResearchNewsItem(BaseModel):
    """A single news item in the research input."""

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    published_at: Optional[str] = None  # ISO date string, e.g. "2026-03-21"


class ResearchInputPayload(BaseModel):
    """Full input payload validated before it is passed to the LLM."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: Any  # datetime — kept as Any to accept both datetime and ISO string
    price_snapshot: ResearchPriceSnapshot
    context: ResearchContext = Field(default_factory=ResearchContext)
    news: list[ResearchNewsItem] = Field(default_factory=list, max_length=5)


class StructuredResearchOutput(BaseModel):
    """Structured output schema stored in ``research_outputs``."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["bullish", "bearish", "neutral", "abstain"]
    confidence: float = Field(ge=0, le=1)
    time_horizon: Literal["1d"]
    time_horizon_rationale: Optional[str] = None
    actionability: Literal["abstain", "watch", "actionable"]
    thesis_summary: str = Field(min_length=1)
    key_drivers: list[str]
    counterarguments: list[str]
    invalidators: list[str]


# ---------------------------------------------------------------------------
# Research agent
# ---------------------------------------------------------------------------


class ResearchAgent(BaseAgent):
    """
    LLM agent that generates structured equity research from insider trading data.

    **Workflow**

    1. Validate *input_payload* against :class:`ResearchInputPayload`.
    2. Optionally enrich with live market data and news via the tool registry.
    3. Load the versioned prompt from the prompt registry.
    4. Build the final prompt and call the LLM.
    5. Parse and validate the response against :class:`StructuredResearchOutput`.
    6. Return an :class:`~src.agents.base.AgentResult`.

    The ``agent_runner`` parameter can be replaced in tests with a stub that
    returns canned JSON without making real API calls.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        prompt_registry: PromptRegistry,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        agent_runner: Optional[AgentRunner] = None,
    ) -> None:
        super().__init__(tool_registry, prompt_registry, model_name=model_name)
        self.prompt_version = prompt_version
        self._agent_runner: AgentRunner = agent_runner or _default_agent_runner

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, input_payload: dict[str, Any], context: ToolContext) -> AgentResult:
        """Generate one structured research output for the given payload."""
        try:
            validated = ResearchInputPayload.model_validate(input_payload)
            prompt_obj = self.prompt_registry.get("research", self.prompt_version)
            prompt = self._build_prompt(validated, prompt_obj.template)

            raw_response = self._agent_runner(prompt, self.model_name)
            parsed = _coerce_json_object(raw_response)
            output = StructuredResearchOutput.model_validate(parsed)

            return AgentResult(
                prompt_id="research",
                prompt_version=self.prompt_version,
                model_name=self.model_name,
                input_data=input_payload,
                output_data=output.model_dump(),
                success=True,
            )
        except (ValidationError, ValueError, RuntimeError) as exc:
            logger.error(
                "research_agent_failed",
                ticker=input_payload.get("ticker"),
                model_name=self.model_name,
                prompt_version=self.prompt_version,
                error=str(exc),
                exc_info=True,
            )
            return AgentResult(
                prompt_id="research",
                prompt_version=self.prompt_version,
                model_name=self.model_name,
                input_data=input_payload,
                error=str(exc),
                success=False,
            )

    # ------------------------------------------------------------------
    # Tool-based data helpers
    # ------------------------------------------------------------------

    def fetch_market_data(self, ticker: str, context: ToolContext) -> dict[str, Any]:
        """Fetch a market snapshot via the registered ``get_market_snapshot`` tool."""
        return self.tool_registry.dispatch(
            "get_market_snapshot", {"ticker": ticker}, context
        )

    def fetch_news(
        self, ticker: str, context: ToolContext, limit: int = 5
    ) -> list[dict[str, str]]:
        """Fetch recent news via the registered ``get_recent_news`` tool."""
        return self.tool_registry.dispatch(
            "get_recent_news", {"ticker": ticker, "limit": limit}, context
        )

    def fetch_insider_trades(
        self, ticker: str, context: ToolContext, days: int = 30
    ) -> list[dict[str, Any]]:
        """Fetch insider trades via the registered ``query_trades_by_ticker`` tool."""
        return self.tool_registry.dispatch(
            "query_trades_by_ticker", {"ticker": ticker, "days": days}, context
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, payload: ResearchInputPayload, template: str) -> str:
        payload_json = json.dumps(
            payload.model_dump(mode="json"), ensure_ascii=False, indent=2
        )
        return (
            f"{template.strip()}\n\n"
            "Input JSON:\n"
            f"{payload_json}\n\n"
            "Return only one JSON object with no surrounding markdown."
        )


# ---------------------------------------------------------------------------
# Default LLM runner (Phidata / provider-backed chat model)
# ---------------------------------------------------------------------------


def _should_use_gemini_backend(model_name: str) -> bool:
    """Return True when *model_name* should use the Gemini backend."""
    return model_name.strip().lower().startswith("gemini")


def _get_google_api_key() -> Optional[str]:
    """Resolve the Google API key from env first, then app config."""
    return os.getenv("GOOGLE_API_KEY") or getattr(app_config, "GOOGLE_API_KEY", None)


def _build_phi_model(model_name: str) -> Any:
    """Build the Phidata chat model for the configured provider."""
    if _should_use_gemini_backend(model_name):
        try:
            from phi.model.google import Gemini
        except Exception as exc:
            raise RuntimeError(
                "Gemini model support requires `google-generativeai` and GOOGLE_API_KEY."
            ) from exc
        return Gemini(id=model_name, api_key=_get_google_api_key())

    try:
        from phi.model.openai import OpenAIChat
    except Exception as exc:
        raise RuntimeError(
            "OpenAI model support requires the `openai` package and OPENAI_API_KEY."
        ) from exc
    return OpenAIChat(id=model_name)


def _default_agent_runner(prompt: str, model_name: str) -> Any:
    """Invoke a Phidata Agent with the provider implied by *model_name*."""
    try:
        from phi.agent import Agent
    except Exception as exc:
        raise RuntimeError(
            "Phidata dependencies are required for the default agent runner."
        ) from exc

    agent = Agent(model=_build_phi_model(model_name), markdown=False)
    response = agent.run(prompt)
    return getattr(response, "content", response)


# ---------------------------------------------------------------------------
# JSON coercion helper
# ---------------------------------------------------------------------------


def _coerce_json_object(raw_response: Any) -> dict[str, Any]:
    """Normalise common LLM response shapes into a plain dict."""
    if isinstance(raw_response, dict):
        return raw_response

    candidate = raw_response
    if hasattr(candidate, "content"):
        candidate = candidate.content

    if isinstance(candidate, bytes):
        candidate = candidate.decode("utf-8")

    if not isinstance(candidate, str):
        raise TypeError(f"unsupported_llm_response_type: {type(candidate)!r}")

    text = candidate.strip()
    if not text:
        raise ValueError("empty_llm_response")

    candidates = [text]
    left = text.find("{")
    right = text.rfind("}")
    if left != -1 and right != -1 and right > left:
        candidates.append(text[left : right + 1])

    for blob in candidates:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("llm_response_is_not_valid_json_object")
