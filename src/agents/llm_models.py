"""Shared LLM model construction for agent runners."""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

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

    if should_use_openrouter_backend(model_name):
        raise RuntimeError(
            "OpenRouter models use the direct OpenRouter runner, not a Phi model."
        )

    raise RuntimeError(f"Unsupported default LLM model for Phi runner: {model_name}")


def run_openrouter_chat_completion(
    prompt: str,
    model_name: str,
    *,
    http_client_cls: type[Any] = httpx.Client,
    now_ms: Any | None = None,
    monotonic_ms: Any | None = None,
) -> dict[str, Any]:
    """Call OpenRouter directly through its OpenAI-compatible HTTP endpoint."""
    api_key = get_openrouter_api_key()
    if not api_key:
        raise RuntimeError("OpenRouter model support requires OPENROUTER_API_KEY.")

    start_ms = int(time.monotonic() * 1000) if now_ms is None else int(now_ms())
    with http_client_cls(timeout=120) as client:
        response = client.post(
            f"{app_config.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
        )
    response.raise_for_status()
    elapsed_ms = (
        int(time.monotonic() * 1000) - start_ms
        if monotonic_ms is None
        else int(monotonic_ms()) - start_ms
    )

    payload = response.json()
    choices = payload.get("choices") or ()
    message = choices[0].get("message") if choices else {}
    content = (message or {}).get("content")
    if content is None:
        content = ""
    usage = payload.get("usage") or {}
    return {
        "content": content,
        "usage": {
            "provider": "openrouter",
            "model": str(payload.get("model") or model_name),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "estimated_cost": float(usage.get("estimated_cost", usage.get("cost") or 0.0)),
            "latency_ms": max(elapsed_ms, 0),
        },
    }
