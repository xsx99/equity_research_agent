"""Shared types and helpers for tool smoke checks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

SmokeStatus = Literal["passed", "failed", "skipped"]


@dataclass
class SmokeCheckResult:
    name: str
    status: SmokeStatus
    details: str
    preview: Any | None = None


def _passed(name: str, details: str, preview: Any | None = None) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="passed", details=details, preview=preview)


def _failed(name: str, details: str, preview: Any | None = None) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="failed", details=details, preview=preview)


def _skipped(name: str, details: str) -> SmokeCheckResult:
    return SmokeCheckResult(name=name, status="skipped", details=details)


def _preview(value: Any, max_chars: int = 280) -> str:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    if len(rendered) <= max_chars:
        return rendered
    return f"{rendered[: max_chars - 3]}..."


def _print_results(results: list[SmokeCheckResult], *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": result.name,
                        "status": result.status,
                        "details": result.details,
                        "preview": result.preview,
                    }
                    for result in results
                ],
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return

    for result in results:
        print(f"[{result.status.upper():7}] {result.name}: {result.details}")
        if result.preview is not None:
            print(f"          preview={_preview(result.preview)}")

    passed = sum(result.status == "passed" for result in results)
    failed = sum(result.status == "failed" for result in results)
    skipped = sum(result.status == "skipped" for result in results)
    print()
    print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")
