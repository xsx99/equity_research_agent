"""Shared LLM model construction for agent runners."""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

from src.core import config as app_config

OPENROUTER_MODEL_PREFIXES = ("moonshotai/",)

_GEMINI_PRICING_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash-lite-preview-09-2025": (0.10, 0.40),
}


def should_use_gemini_backend(model_name: str) -> bool:
    return model_name.strip().lower().startswith("gemini")


def should_use_openrouter_backend(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    return normalized.startswith(OPENROUTER_MODEL_PREFIXES)


def get_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or getattr(app_config, "GOOGLE_API_KEY", None)


def get_openrouter_api_key() -> Optional[str]:
    return os.getenv("OPENROUTER_API_KEY") or getattr(app_config, "OPENROUTER_API_KEY", None)


def run_gemini_chat_completion(
    prompt: str,
    model_name: str,
    *,
    generative_model_cls: type[Any] | None = None,
    configure_fn: Any | None = None,
    now_ms: Any | None = None,
    monotonic_ms: Any | None = None,
) -> dict[str, Any]:
    """Call Gemini directly and preserve SDK token usage metadata."""
    api_key = get_google_api_key()
    if not api_key:
        raise RuntimeError("Gemini model support requires GOOGLE_API_KEY.")

    if generative_model_cls is None or configure_fn is None:
        try:
            import google.generativeai as genai
        except Exception as exc:
            raise RuntimeError(
                "Gemini model support requires `google-generativeai` and GOOGLE_API_KEY."
            ) from exc
        if generative_model_cls is None:
            generative_model_cls = genai.GenerativeModel
        if configure_fn is None:
            configure_fn = genai.configure

    start_ms = int(time.monotonic() * 1000) if now_ms is None else int(now_ms())
    configure_fn(api_key=api_key)
    model = generative_model_cls(model_name=model_name)
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0},
    )
    elapsed_ms = (
        int(time.monotonic() * 1000) - start_ms
        if monotonic_ms is None
        else int(monotonic_ms()) - start_ms
    )
    usage = _normalize_gemini_usage(
        response=response,
        model_name=model_name,
        elapsed_ms=max(elapsed_ms, 0),
    )
    return {
        "content": _extract_gemini_content(response),
        "usage": usage,
    }


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


def estimate_llm_cost(model_name: str, *, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate provider cost from local per-token pricing when the API omits billing cost."""
    normalized = model_name.strip().lower()
    rates = _GEMINI_PRICING_PER_1M_TOKENS.get(normalized)
    if rates is None:
        return 0.0

    input_rate, output_rate = rates
    return (max(prompt_tokens, 0) * input_rate + max(completion_tokens, 0) * output_rate) / 1_000_000


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
    generation_metadata: dict[str, Any] | None = None
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
        payload = response.json()
        generation_metadata = _fetch_openrouter_generation_metadata(
            client=client,
            api_key=api_key,
            generation_id=payload.get("id"),
        )
    elapsed_ms = (
        int(time.monotonic() * 1000) - start_ms
        if monotonic_ms is None
        else int(monotonic_ms()) - start_ms
    )

    choices = payload.get("choices") or ()
    message = choices[0].get("message") if choices else {}
    content = (message or {}).get("content")
    if content is None:
        content = ""
    usage = payload.get("usage") or {}
    normalized_usage = _normalize_openrouter_usage(
        model_name=model_name,
        response_model=payload.get("model"),
        chat_usage=usage,
        generation_metadata=generation_metadata,
        elapsed_ms=max(elapsed_ms, 0),
    )
    return {
        "content": content,
        "usage": normalized_usage,
    }


def _fetch_openrouter_generation_metadata(
    *,
    client: Any,
    api_key: str,
    generation_id: Any,
) -> dict[str, Any] | None:
    if not generation_id:
        return None
    try:
        response = client.get(
            f"{app_config.OPENROUTER_BASE_URL.rstrip('/')}/generation",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"id": str(generation_id)},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else None


def _normalize_openrouter_usage(
    *,
    model_name: str,
    response_model: Any,
    chat_usage: dict[str, Any],
    generation_metadata: dict[str, Any] | None,
    elapsed_ms: int,
) -> dict[str, Any]:
    metadata = generation_metadata or {}
    prompt_tokens = _int_or_none(metadata.get("tokens_prompt"))
    if prompt_tokens is None:
        prompt_tokens = _int_or_none(metadata.get("native_tokens_prompt"))
    if prompt_tokens is None:
        prompt_tokens = _int_or_none(chat_usage.get("prompt_tokens")) or 0

    completion_tokens = _int_or_none(metadata.get("tokens_completion"))
    if completion_tokens is None:
        completion_tokens = _int_or_none(metadata.get("native_tokens_completion"))
    if completion_tokens is None:
        completion_tokens = _int_or_none(chat_usage.get("completion_tokens")) or 0

    total_tokens = _int_or_none(metadata.get("total_tokens"))
    if total_tokens is None and generation_metadata:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens is None:
        total_tokens = _int_or_none(chat_usage.get("total_tokens"))
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    estimated_cost = _float_or_none(metadata.get("total_cost"))
    if estimated_cost is None:
        estimated_cost = _float_or_none(metadata.get("usage"))
    if estimated_cost is None:
        estimated_cost = _float_or_none(chat_usage.get("estimated_cost"))
    if estimated_cost is None:
        estimated_cost = _float_or_none(chat_usage.get("cost")) or 0.0

    latency_ms = _int_or_none(metadata.get("latency"))
    if latency_ms is None:
        latency_ms = elapsed_ms

    return {
        "provider": "openrouter",
        "model": str(metadata.get("model") or response_model or model_name),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
        "latency_ms": max(latency_ms, 0),
    }


def _normalize_gemini_usage(
    *,
    response: Any,
    model_name: str,
    elapsed_ms: int,
) -> dict[str, Any]:
    usage_metadata = _attr_or_key(response, "usage_metadata") or {}
    prompt_tokens = _int_or_none(_attr_or_key(usage_metadata, "prompt_token_count")) or 0
    completion_tokens = _int_or_none(_attr_or_key(usage_metadata, "candidates_token_count")) or 0
    total_tokens = _int_or_none(_attr_or_key(usage_metadata, "total_token_count"))
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "provider": "google",
        "model": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimate_llm_cost(
            model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        "latency_ms": elapsed_ms,
    }


def _extract_gemini_content(response: Any) -> str:
    try:
        text = getattr(response, "text", None)
    except Exception:
        text = None
    if text is not None:
        return str(text)

    candidates = _attr_or_key(response, "candidates") or ()
    if not candidates:
        return ""
    content = _attr_or_key(candidates[0], "content")
    parts = _attr_or_key(content, "parts") or ()
    text_parts = []
    for part in parts:
        part_text = _attr_or_key(part, "text")
        if part_text is not None:
            text_parts.append(str(part_text))
    return "".join(text_parts)


def _attr_or_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
