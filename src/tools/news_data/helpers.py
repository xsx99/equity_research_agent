"""Internal helpers for news filtering, ranking, and normalization."""
from __future__ import annotations

import re
from typing import Any, Optional

from src.tools.news_data.types import NewsItem


_LOW_SIGNAL_TITLE_PATTERNS = (
    re.compile(r"\bis it too late\b", flags=re.IGNORECASE),
    re.compile(r"\bshould you buy\b", flags=re.IGNORECASE),
    re.compile(r"\bto buy now\b", flags=re.IGNORECASE),
    re.compile(r"\bhere'?s why\b", flags=re.IGNORECASE),
    re.compile(r"\bwhy .* stock .* (up|down) today\b", flags=re.IGNORECASE),
    re.compile(r"\btop \d+ .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bbest .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bprediction\b", flags=re.IGNORECASE),
)

_SIGNAL_TYPE_PRIORITY = {
    "earnings_guidance": 120,
    "sec_filing": 115,
    "analyst_rating": 110,
    "earnings": 100,
    "company_update": 90,
    "general_news": 70,
}


def _looks_low_signal(title: str) -> bool:
    normalized = " ".join(title.split())
    return any(pattern.search(normalized) for pattern in _LOW_SIGNAL_TITLE_PATTERNS)


def _infer_signal_type(title: str, summary: str, *, source: Optional[str] = None) -> str:
    text = " ".join((title, summary, source or "")).lower()
    if any(keyword in text for keyword in ("guidance", "outlook", "forecast", "preliminary results")):
        return "earnings_guidance"
    if any(keyword in text for keyword in ("upgrade", "upgrades", "downgrade", "downgrades", "price target", "initiates coverage")):
        return "analyst_rating"
    if any(keyword in text for keyword in ("sec", "form 4", "8-k", "10-q", "10-k", "filing")):
        return "sec_filing"
    if any(keyword in text for keyword in ("earnings", "revenue", "eps", "quarter", "profit warning")):
        return "earnings"
    if any(keyword in text for keyword in ("press release", "business wire", "globe newswire")):
        return "company_update"
    return "general_news"


def _normalized_news_item(
    title: Optional[str],
    summary: Optional[str],
    published_at: Optional[str] = None,
    *,
    source: Optional[str] = None,
    url: Optional[str] = None,
    signal_type: Optional[str] = None,
) -> Optional[NewsItem]:
    clean_title = (title or "").strip()
    if not clean_title:
        return None
    clean_summary = (summary or "").strip()
    normalized_signal_type = signal_type or _infer_signal_type(clean_title, clean_summary, source=source)
    return {
        "title": clean_title,
        "summary": clean_summary,
        "published_at": published_at,
        "source": (source or "").strip() or None,
        "url": (url or "").strip() or None,
        "signal_type": normalized_signal_type,
    }


def _normalize_provider_news_item(item: Any) -> Optional[NewsItem]:
    if not isinstance(item, dict):
        return None
    return _normalized_news_item(
        item.get("title"),
        item.get("summary"),
        item.get("published_at"),
        source=item.get("source"),
        url=item.get("url"),
        signal_type=item.get("signal_type"),
    )


def _dedupe_key(item: NewsItem) -> str:
    return (item.get("url") or item["title"]).strip().lower()


def _rank_and_filter_news_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    kept: list[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        if _looks_low_signal(item["title"]):
            continue
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)

    kept.sort(
        key=lambda item: (
            _SIGNAL_TYPE_PRIORITY.get(item.get("signal_type") or "general_news", 0),
            item.get("published_at") or "",
        ),
        reverse=True,
    )
    return kept[:limit]
