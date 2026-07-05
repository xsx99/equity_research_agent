"""PR10 strategy evolution agent with retry and safe fallback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import ValidationError

from src.agents.base import AgentResult, BaseAgent
from src.agents.prompt_registry import PromptRegistry, RenderedPrompt
from src.agents.strategy_evolution_schemas import (
    StrategyEvolutionInput,
    StrategyEvolutionOutput,
    StrategyEvolutionOutputFallback,
)
from src.agents.trading import (
    PromptRunRecord,
    UsageEventRecord,
    _coerce_json_object,
    _default_agent_runner as _trading_default_agent_runner,
    _normalize_runner_response,
)
from src.core import config as app_config
from src.core.logging import get_logger
from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry


logger = get_logger(__name__)

DEFAULT_MODEL_NAME = app_config.STRATEGY_EVOLUTION_MODEL_NAME
DEFAULT_PROMPT_VERSION = "v1"

AgentRunner = Callable[[str, str], Any]


class StrategyEvolutionAgent(BaseAgent):
    """Bounded strategy-proposal synthesis with one repair retry."""

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

    def run(self, input_payload: dict[str, Any], context: ToolContext | None) -> AgentResult:
        validated = StrategyEvolutionInput.model_validate(input_payload)
        rendered = self.prompt_registry.render(
            "strategy_evolution",
            self.prompt_version,
            {
                "trade_date": validated.trade_date.isoformat(),
                "input_payload_json": json.dumps(validated.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            },
        )

        validation_errors: list[str] = []
        usage_events: list[UsageEventRecord] = []
        raw_output_text = ""
        final_error: str | None = None

        for attempt in range(2):
            prompt = rendered.text if attempt == 0 else self._repair_prompt(rendered, validation_errors[-1])
            response = self._agent_runner(prompt, self.model_name)
            raw_output_text, usage = _normalize_runner_response(response, self.model_name)
            usage_events.append(UsageEventRecord(retry_count=attempt, status="succeeded", **usage))
            try:
                parsed_output_json = _coerce_json_object(raw_output_text)
                output = StrategyEvolutionOutput.model_validate(parsed_output_json)
                prompt_run = PromptRunRecord(
                    pipeline_name="strategy_evolution",
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
                    prompt_id="strategy_evolution",
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

        fallback = StrategyEvolutionOutputFallback(
            fallback_reason="validation_failed_after_retry",
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
        )
        prompt_run = PromptRunRecord(
            pipeline_name="strategy_evolution",
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
            "strategy_evolution_agent_failed",
            trade_date=validated.trade_date.isoformat(),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            error=final_error,
        )
        return AgentResult(
            prompt_id="strategy_evolution",
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


def _default_agent_runner(prompt: str, model_name: str) -> Any:
    return _trading_default_agent_runner(prompt, model_name)
