"""Phidata/OpenAI wrapper for structured research outputs."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PROMPT_VERSION = "v1"
DEFAULT_MODEL_NAME = os.getenv("RESEARCH_MODEL_NAME", "gpt-4.1-mini")
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


class ResearchPriceSnapshot(BaseModel):
    """Input schema for price snapshot."""

    model_config = ConfigDict(extra="forbid")

    last_price: float | None = None
    return_1d: float | None = None
    return_5d: float | None = None


class ResearchContext(BaseModel):
    """Input schema for optional context fields."""

    model_config = ConfigDict(extra="forbid")

    sector: str | None = None
    earnings_in_days: int | None = None


class ResearchNewsItem(BaseModel):
    """Input schema for a news item."""

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""


class ResearchInputPayload(BaseModel):
    """Input schema passed to the LLM layer."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: datetime
    price_snapshot: ResearchPriceSnapshot
    context: ResearchContext = Field(default_factory=ResearchContext)
    news: list[ResearchNewsItem] = Field(default_factory=list, max_length=5)


class StructuredResearchOutput(BaseModel):
    """Structured output schema persisted in research_outputs."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["bullish", "bearish", "neutral", "abstain"]
    confidence: float = Field(ge=0, le=1)
    time_horizon: Literal["1d", "3d", "5d"]
    actionability: Literal["abstain", "watch", "actionable"]
    thesis_summary: str = Field(min_length=1)
    key_drivers: list[str]
    counterarguments: list[str]
    invalidators: list[str]


PromptLoader = Callable[[str], str]
AgentRunner = Callable[[str, str], Any]


class ResearchLLMClient:
    """Client that composes prompts, executes model calls, and validates output."""

    def __init__(
        self,
        *,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        model_name: str = DEFAULT_MODEL_NAME,
        prompt_loader: PromptLoader | None = None,
        agent_runner: AgentRunner | None = None,
    ) -> None:
        self.prompt_version = prompt_version
        self.model_name = model_name
        self.prompt_loader = prompt_loader or load_prompt_template
        self.agent_runner = agent_runner or _default_agent_runner

        self._prompt_template = self.prompt_loader(self.prompt_version)

    def run(self, input_payload: dict[str, Any]) -> StructuredResearchOutput:
        """Generate and validate one structured research output."""
        validated_input = ResearchInputPayload.model_validate(input_payload)
        prompt = self._build_prompt(validated_input)
        raw_response = self.agent_runner(prompt, self.model_name)

        try:
            parsed_response = _coerce_json_object(raw_response)
            return StructuredResearchOutput.model_validate(parsed_response)
        except ValidationError as exc:
            logger.error(
                "structured_output_validation_failed",
                ticker=validated_input.ticker,
                model_name=self.model_name,
                prompt_version=self.prompt_version,
                error=str(exc),
            )
            raise
        except Exception as exc:
            logger.error(
                "llm_output_parse_failed",
                ticker=validated_input.ticker,
                model_name=self.model_name,
                prompt_version=self.prompt_version,
                error=str(exc),
                exc_info=True,
            )
            raise

    def run_as_dict(self, input_payload: dict[str, Any]) -> dict[str, Any]:
        """Same as run(), but returns a plain dict for persistence."""
        return self.run(input_payload).model_dump()

    def _build_prompt(self, payload: ResearchInputPayload) -> str:
        payload_json = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2)
        return (
            f"{self._prompt_template.strip()}\n\n"
            "Input JSON:\n"
            f"{payload_json}\n\n"
            "Return only one JSON object with no surrounding markdown."
        )


def _prompt_filename(prompt_version: str) -> str:
    normalized = prompt_version.strip().lower()
    if normalized.startswith("research_"):
        return f"{normalized}.txt"
    return f"research_{normalized}.txt"


def load_prompt_template(prompt_version: str) -> str:
    """Load prompt text from prompts/research_<version>.txt."""
    prompt_path = PROMPTS_DIR / _prompt_filename(prompt_version)
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt_template_not_found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _default_agent_runner(prompt: str, model_name: str) -> Any:
    """Invoke Phidata Agent with OpenAI model."""
    try:
        from phi.agent import Agent
        from phi.model.openai import OpenAIChat
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "Phidata/OpenAI dependencies are required for default agent runner."
        ) from exc

    agent = Agent(
        model=OpenAIChat(id=model_name),
        markdown=False,
    )
    response = agent.run(prompt)
    return getattr(response, "content", response)


def _coerce_json_object(raw_response: Any) -> dict[str, Any]:
    """Normalize common Agent response shapes into a JSON object."""
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

    # Most providers return a raw JSON string. If not, extract the first JSON object.
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

