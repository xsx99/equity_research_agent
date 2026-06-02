"""Shared types for the news data subsystem."""
from __future__ import annotations

from typing import Optional, Protocol, TypedDict


class NewsItem(TypedDict):
    """A single news headline and summary."""

    title: str
    summary: str
    published_at: Optional[str]  # ISO-8601 date string, e.g. "2026-03-21"
    source: Optional[str]
    url: Optional[str]
    signal_type: Optional[str]


class NewsProvider(Protocol):
    """Contract for pluggable news providers."""

    def fetch_recent(self, ticker: str, limit: int) -> list[NewsItem]:
        """Fetch recent news for a ticker."""
