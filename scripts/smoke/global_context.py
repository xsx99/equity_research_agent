"""Smoke checks for the global context tool."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.tools.context import ToolContext

from scripts.smoke import SmokeCheckResult, _failed, _passed


def _smoke_global_context(registry, limit: int) -> SmokeCheckResult:
    name = "global_context"
    try:
        snapshot = registry.dispatch(
            "get_global_context",
            {"limit": limit},
            ToolContext(),
        )
    except Exception as exc:
        return _failed(name, f"Global context tool failed: {exc}")

    indicators = snapshot.get("indicators") if isinstance(snapshot, dict) else None
    trump_updates = snapshot.get("trump_updates") if isinstance(snapshot, dict) else None
    geopolitical_news = snapshot.get("geopolitical_news") if isinstance(snapshot, dict) else None

    if not isinstance(indicators, dict) or not indicators:
        return _failed(name, "No macro indicators were returned.")

    if not any(
        isinstance(item, dict) and item.get("value") is not None
        for item in indicators.values()
    ):
        return _failed(name, "Macro indicators were returned, but every value is null.")

    if not isinstance(geopolitical_news, list) or not geopolitical_news:
        return _failed(name, "No geopolitical news items were returned.")

    preview = {
        "indicator_keys": sorted(indicators.keys()),
        "trump_count": len(trump_updates) if isinstance(trump_updates, list) else 0,
        "geopolitical_title": geopolitical_news[0].get("title"),
    }
    return _passed(name, "Fetched macro indicators and global news context.", preview=preview)
