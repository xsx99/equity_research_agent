"""Research agent — structured equity research from insider trading data."""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from pydantic import ValidationError

from src.agents.prompt_registry import PromptRegistry
from src.agents.base import AgentResult, BaseAgent
from src.agents.research_schemas import ResearchInputPayload, StructuredResearchOutput
from src.core import config as app_config
from src.core.logging import get_logger
from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry

# Re-export schemas so existing imports keep working
__all__ = [
    "DEFAULT_MODEL_NAME",
    "DEFAULT_PROMPT_VERSION",
    "ResearchAgent",
    "ResearchInputPayload",
    "StructuredResearchOutput",
    "_coerce_json_object",
    "_get_google_api_key",
    "_should_use_gemini_backend",
]

logger = get_logger(__name__)

DEFAULT_MODEL_NAME = app_config.RESEARCH_MODEL_NAME
DEFAULT_PROMPT_VERSION = "v1"

AgentRunner = Callable[[str, str], Any]


class ResearchAgent(BaseAgent):
    """
    LLM agent that generates structured equity research from insider trading data.

    Workflow:
    1. Validate *input_payload* against ResearchInputPayload.
    2. Load the versioned prompt from the prompt registry.
    3. Build the final prompt and call the LLM.
    4. Parse and validate the response against StructuredResearchOutput.
    5. Return an AgentResult.
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

    def run(self, input_payload: dict[str, Any], context: ToolContext) -> AgentResult:
        """Generate one structured research output for the given payload."""
        try:
            validated = ResearchInputPayload.model_validate(input_payload)
            prompt = self._build_prompt(validated)

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

    def fetch_market_data(self, ticker: str, context: ToolContext) -> dict[str, Any]:
        return self.tool_registry.dispatch("get_market_snapshot", {"ticker": ticker}, context)

    def fetch_news(self, ticker: str, context: ToolContext, limit: int = 5) -> list[dict[str, str]]:
        return self.tool_registry.dispatch("get_recent_news", {"ticker": ticker, "limit": limit}, context)

    def fetch_insider_trades(self, ticker: str, context: ToolContext, days: int = 30) -> list[dict[str, Any]]:
        return self.tool_registry.dispatch("query_trades_by_ticker", {"ticker": ticker, "days": days}, context)

    def _build_prompt(self, payload: ResearchInputPayload, template: str = "") -> str:
        payload_json = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2)
        rendered = self.prompt_registry.render(
            "research",
            self.prompt_version,
            {
                "ticker": payload.ticker,
                "input_payload_json": payload_json,
            },
        )
        return rendered.text


# ---------------------------------------------------------------------------
# LLM runner
# ---------------------------------------------------------------------------


def _should_use_gemini_backend(model_name: str) -> bool:
    return model_name.strip().lower().startswith("gemini")


def _get_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or getattr(app_config, "GOOGLE_API_KEY", None)


def _build_phi_model(model_name: str) -> Any:
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
