"""PR05 bounded trading decision agent with retry and safe fallback."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import ValidationError

from src.agents.base import AgentResult, BaseAgent
from src.agents.prompt_registry import PromptRegistry, PromptTemplate, RenderedPrompt
from src.agents.trading_schemas import (
    TradingDecisionInput,
    TradingDecisionOutput,
    TradingDecisionOutputFallback,
)
from src.core import config as app_config
from src.core.logging import get_logger
from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)

DEFAULT_MODEL_NAME = app_config.TRADING_MODEL_NAME
DEFAULT_PROMPT_VERSION = "v1"

AgentRunner = Callable[[str, str], Any]


@dataclass(frozen=True)
class PromptRunRecord:
    """Persistable LLM prompt-run telemetry."""

    pipeline_name: str
    rendered_prompt_hash: str
    rendered_prompt_redacted: str
    input_context_json: dict[str, Any]
    raw_output_text: str
    parsed_output_json: dict[str, Any]
    parse_status: str
    validation_errors_json: list[str]
    fallback_action: str | None
    error_message: str | None


@dataclass(frozen=True)
class UsageEventRecord:
    """Persistable LLM usage telemetry for one prompt run."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    latency_ms: int
    retry_count: int
    status: str


class TradingAgent(BaseAgent):
    """Bounded trading decision agent with one repair retry."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None,
        prompt_registry: PromptRegistry,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        agent_runner: Optional[AgentRunner] = None,
    ) -> None:
        super().__init__(tool_registry, prompt_registry, model_name=model_name)
        self.prompt_version = prompt_version
        self._agent_runner = agent_runner or _default_agent_runner

    def run(self, input_payload: dict[str, Any], context: ToolContext) -> AgentResult:
        validated = TradingDecisionInput.model_validate(input_payload)
        rendered = self.prompt_registry.render(
            "trading_decision",
            self.prompt_version,
            {
                "ticker": validated.ticker,
                "input_payload_json": json.dumps(validated.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            },
        )

        validation_errors: list[str] = []
        usage_events: list[UsageEventRecord] = []
        raw_output_text = ""
        parsed_output_json: dict[str, Any] = {}
        final_error: str | None = None

        for attempt in range(2):
            prompt = rendered.text if attempt == 0 else self._repair_prompt(rendered, validation_errors[-1])
            response = self._agent_runner(prompt, self.model_name)
            raw_output_text, usage = _normalize_runner_response(response, self.model_name)
            usage_events.append(UsageEventRecord(retry_count=attempt, status="succeeded", **usage))
            try:
                parsed_output_json = _coerce_json_object(raw_output_text)
                output = TradingDecisionOutput.model_validate(parsed_output_json)
                prompt_run = PromptRunRecord(
                    pipeline_name="trading",
                    rendered_prompt_hash=rendered.rendered_prompt_hash,
                    rendered_prompt_redacted=prompt,
                    input_context_json=validated.model_dump(mode="json"),
                    raw_output_text=raw_output_text,
                    parsed_output_json=output.model_dump(mode="json"),
                    parse_status="succeeded",
                    validation_errors_json=list(validation_errors),
                    fallback_action=None,
                    error_message=None,
                )
                return AgentResult(
                    prompt_id="trading_decision",
                    prompt_version=self.prompt_version,
                    model_name=self.model_name,
                    input_data=input_payload,
                    output_data=output.model_dump(mode="json"),
                    success=True,
                    metadata={
                        "retry_count": attempt,
                        "validation_errors": list(validation_errors),
                        "prompt_template": rendered.template,
                        "prompt_run": prompt_run,
                        "usage_events": usage_events,
                    },
                )
            except (ValidationError, ValueError, TypeError) as exc:
                final_error = str(exc)
                validation_errors.append(final_error)

        fallback = TradingDecisionOutputFallback(
            ticker=validated.ticker,
            decision=validated.fallback_action,
            fallback_action=validated.fallback_action,
            fallback_reason="validation_failed_after_retry",
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
        )
        prompt_run = PromptRunRecord(
            pipeline_name="trading",
            rendered_prompt_hash=rendered.rendered_prompt_hash,
            rendered_prompt_redacted=self._repair_prompt(rendered, validation_errors[-1]),
            input_context_json=validated.model_dump(mode="json"),
            raw_output_text=raw_output_text,
            parsed_output_json=fallback.model_dump(mode="json"),
            parse_status="failed",
            validation_errors_json=list(validation_errors),
            fallback_action=fallback.fallback_action,
            error_message=final_error,
        )
        logger.error(
            "trading_agent_failed",
            ticker=validated.ticker,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            error=final_error,
        )
        return AgentResult(
            prompt_id="trading_decision",
            prompt_version=self.prompt_version,
            model_name=self.model_name,
            input_data=input_payload,
            output_data=fallback.model_dump(mode="json"),
            error=final_error,
            success=False,
            metadata={
                "retry_count": 1,
                "validation_errors": list(validation_errors),
                "prompt_template": rendered.template,
                "prompt_run": prompt_run,
                "usage_events": usage_events,
            },
        )

    def _build_prompt(self, payload: Any, template: str) -> str:
        return template

    def _repair_prompt(self, rendered: RenderedPrompt, validation_error: str) -> str:
        return (
            f"{rendered.text.rstrip()}\n\n"
            "Previous validation error:\n"
            f"{validation_error}\n\n"
            "Return only one corrected JSON object with no markdown."
        )


def _normalize_runner_response(response: Any, model_name: str) -> tuple[str, dict[str, Any]]:
    if isinstance(response, dict) and "content" in response:
        content = response["content"]
        usage = response.get("usage") or {}
    else:
        content = response
        usage = {}

    if isinstance(content, dict):
        raw_output = json.dumps(content, ensure_ascii=False)
    elif isinstance(content, bytes):
        raw_output = content.decode("utf-8")
    else:
        raw_output = str(content)

    return raw_output, {
        "provider": str(usage.get("provider", "unknown")),
        "model": str(usage.get("model", model_name)),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
        "estimated_cost": float(usage.get("estimated_cost", 0.0)),
        "latency_ms": int(usage.get("latency_ms", 0)),
    }


def _coerce_json_object(raw_response: Any) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return raw_response

    candidate = raw_response
    if isinstance(candidate, bytes):
        candidate = candidate.decode("utf-8")
    if not isinstance(candidate, str):
        raise TypeError(f"unsupported_llm_response_type: {type(candidate)!r}")

    text = candidate.strip()
    if not text:
        raise ValueError("empty_llm_response")

    blobs = [text]
    left = text.find("{")
    right = text.rfind("}")
    if left != -1 and right != -1 and right > left:
        blobs.append(text[left : right + 1])

    for blob in blobs:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("llm_response_is_not_valid_json_object")


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
            "Phidata dependencies are required for the default trading agent runner."
        ) from exc
    agent = Agent(model=_build_phi_model(model_name), markdown=False)
    response = agent.run(prompt)
    return getattr(response, "content", response)
