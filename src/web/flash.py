"""Request-scoped flash message helpers."""
from __future__ import annotations

from fastapi import Request


def flash(request: Request, message: str, level: str = "info") -> None:
    if not hasattr(request.state, "flash"):
        request.state.flash = []
    request.state.flash.append({"message": message, "level": level})


def get_flash(request: Request) -> list[dict]:
    return getattr(request.state, "flash", [])
