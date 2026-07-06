"""Standalone smoke checks for LLM usage and cost accounting.

Default fixture mode does not call external APIs. Use --live-openrouter or
--live-gemini for opt-in live checks.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.llm_models import estimate_llm_cost, run_openrouter_chat_completion
from src.agents.trading import _default_agent_runner, _normalize_runner_response
from src.core import config as app_config


DEFAULT_PROMPT = 'Return exactly this JSON object and nothing else: {"ok": true}'


def run_fixture_smoke() -> dict[str, Any]:
    original_key = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = original_key or "fixture-openrouter-key"
    try:
        openrouter = run_openrouter_chat_completion(
            DEFAULT_PROMPT,
            "moonshotai/kimi-k2.6",
            http_client_cls=_FixtureOpenRouterClient,
            now_ms=lambda: 1000,
            monotonic_ms=lambda: 1123,
        )["usage"]
    finally:
        if original_key is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = original_key

    gemini = {
        "provider": "google",
        "model": "gemini-2.5-flash-lite",
        "prompt_tokens": 1_000_000,
        "completion_tokens": 1_000_000,
        "total_tokens": 2_000_000,
        "estimated_cost": estimate_llm_cost(
            "gemini-2.5-flash-lite",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        ),
    }
    return {
        "status": "passed",
        "mode": "fixture",
        "openrouter": openrouter,
        "gemini": gemini,
    }


def run_live_openrouter_smoke(prompt: str = DEFAULT_PROMPT) -> dict[str, Any]:
    if not app_config.OPENROUTER_API_KEY:
        return {"status": "skipped", "mode": "live_openrouter", "reason": "OPENROUTER_API_KEY not configured"}
    response = run_openrouter_chat_completion(prompt, app_config.REFLECTION_MODEL_NAME)
    raw_output, usage = _normalize_runner_response(response, app_config.REFLECTION_MODEL_NAME)
    return {
        "status": "passed",
        "mode": "live_openrouter",
        "content_preview": raw_output[:200],
        "usage": usage,
    }


def run_live_gemini_smoke(prompt: str = DEFAULT_PROMPT) -> dict[str, Any]:
    if not app_config.GOOGLE_API_KEY:
        return {"status": "skipped", "mode": "live_gemini", "reason": "GOOGLE_API_KEY not configured"}
    response = _default_agent_runner(prompt, app_config.TRADING_MODEL_NAME)
    raw_output, usage = _normalize_runner_response(response, app_config.TRADING_MODEL_NAME)
    return {
        "status": "passed",
        "mode": "live_gemini",
        "content_preview": raw_output[:200],
        "usage": usage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--live-openrouter", action="store_true", help="Run one live OpenRouter usage smoke.")
    parser.add_argument("--live-gemini", action="store_true", help="Run one live Gemini usage smoke.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt for live LLM smoke calls.")
    args = parser.parse_args(argv)

    if args.live_openrouter or args.live_gemini:
        checks = []
        if args.live_openrouter:
            checks.append(run_live_openrouter_smoke(args.prompt))
        if args.live_gemini:
            checks.append(run_live_gemini_smoke(args.prompt))
        report = {"status": _aggregate_status(checks), "mode": "live", "checks": checks}
    else:
        report = run_fixture_smoke()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"[{report['status'].upper()}] llm_usage_smoke mode={report['mode']}")
    return 0 if report["status"] in {"passed", "skipped"} else 1


def _aggregate_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "failed" in statuses:
        return "failed"
    if statuses == {"skipped"}:
        return "skipped"
    return "passed"


class _FixtureResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FixtureOpenRouterClient:
    def __init__(self, *, timeout: int) -> None:
        self.timeout = timeout

    def __enter__(self) -> "_FixtureOpenRouterClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FixtureResponse:
        return _FixtureResponse(
            {
                "id": "gen-fixture",
                "model": "moonshotai/kimi-k2.6-fixture",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "cost": 0.0002,
                },
            }
        )

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, str]) -> _FixtureResponse:
        return _FixtureResponse(
            {
                "data": {
                    "model": "moonshotai/kimi-k2.6-fixture",
                    "tokens_prompt": 13,
                    "tokens_completion": 9,
                    "total_cost": 0.00042,
                    "latency": 456,
                }
            }
        )


if __name__ == "__main__":
    raise SystemExit(main())
