"""Shared LLM model construction for agent runners."""
from __future__ import annotations

import os
from typing import Any, Optional

from src.core import config as app_config

OPENROUTER_MODEL_PREFIXES = ("moonshotai/",)


def should_use_gemini_backend(model_name: str) -> bool:
    return model_name.strip().lower().startswith("gemini")


def should_use_openrouter_backend(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    return normalized.startswith(OPENROUTER_MODEL_PREFIXES)


def get_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or getattr(app_config, "GOOGLE_API_KEY", None)


def get_openrouter_api_key() -> Optional[str]:
    return os.getenv("OPENROUTER_API_KEY") or getattr(app_config, "OPENROUTER_API_KEY", None)


def build_phi_model(
    model_name: str,
    *,
    gemini_cls: type[Any] | None = None,
    openai_chat_cls: type[Any] | None = None,
) -> Any:
    """Build a Phidata model for the configured provider."""
    if should_use_gemini_backend(model_name):
        if gemini_cls is None:
            try:
                from phi.model.google import Gemini
            except Exception as exc:
                raise RuntimeError(
                    "Gemini model support requires `google-generativeai` and GOOGLE_API_KEY."
                ) from exc
            gemini_cls = Gemini
        return gemini_cls(id=model_name, api_key=get_google_api_key())

    if openai_chat_cls is None:
        try:
            from phi.model.openai import OpenAIChat
        except Exception as exc:
            raise RuntimeError(
                "OpenAI-compatible model support requires the `openai` package."
            ) from exc
        openai_chat_cls = OpenAIChat

    if should_use_openrouter_backend(model_name):
        api_key = get_openrouter_api_key()
        if not api_key:
            raise RuntimeError("OpenRouter model support requires OPENROUTER_API_KEY.")
        return openai_chat_cls(
            id=model_name,
            api_key=api_key,
            base_url=app_config.OPENROUTER_BASE_URL,
        )

    return openai_chat_cls(id=model_name)
