"""Internal helpers for global context filtering, normalization, and parsing."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from lxml import html

from src.tools.global_context.types import (
    GlobalNewsItem,
    MacroIndicatorValue,
    _FRED_SERIES,
    _GEOPOLITICAL_KEYWORDS,
    _MARKET_IMPACT_KEYWORDS,
    _TRUMP_KEYWORDS,
)


def _normalized_datetime(value: Optional[Any]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise TypeError(f"Unsupported datetime value: {type(value)!r}")


def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_news_item(
    *,
    source: str,
    title: Optional[str],
    summary: Optional[str] = None,
    published_at: Optional[str] = None,
    url: Optional[str] = None,
) -> Optional[GlobalNewsItem]:
    clean_title = " ".join((title or "").split())
    if not clean_title:
        return None
    return {
        "source": source.strip(),
        "title": clean_title,
        "summary": " ".join((summary or "").split()),
        "published_at": published_at,
        "url": url,
    }


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _clean_title(text: str) -> str:
    title = " ".join(text.split()).strip()
    for suffix in (" | AP News", " - AP News", " | The White House", " - The White House"):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def _contains_keyword(haystack: str, keyword: str) -> bool:
    escaped = re.escape(keyword.strip()).replace(r"\ ", r"\s+")
    return re.search(rf"\b{escaped}\b", haystack, flags=re.IGNORECASE) is not None


def _contains_any_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(_contains_keyword(haystack, kw) for kw in keywords)


def _extract_page_metadata(
    client: Any, url: str
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    response = client.get(url)
    response.raise_for_status()
    doc = html.fromstring(response.text)

    def _first(xpath: str) -> Optional[str]:
        for value in doc.xpath(xpath):
            if isinstance(value, str):
                clean = " ".join(value.split()).strip()
                if clean:
                    return clean
        return None

    title = _first("//meta[@property='og:title']/@content") or _first("//title/text()")
    summary = _first("//meta[@property='og:description']/@content") or _first("//meta[@name='description']/@content")
    published_at = _first("//meta[@property='article:published_time']/@content") or _first("//meta[@name='parsely-pub-date']/@content")
    if title:
        title = _clean_title(title)
    return title, summary, published_at


def _sorted_recent_items(items: list[GlobalNewsItem]) -> list[GlobalNewsItem]:
    return sorted(
        items,
        key=lambda item: _parse_optional_datetime(item.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _filter_trump_updates(items: list[GlobalNewsItem], *, as_of: datetime, limit: int) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if not _contains_any_keyword(haystack, _TRUMP_KEYWORDS):
            continue
        if not _contains_any_keyword(haystack, _MARKET_IMPACT_KEYWORDS):
            continue
        key = item.get("url") or item.get("title") or ""
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _filter_official_updates(items: list[GlobalNewsItem], *, as_of: datetime, limit: int) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if _contains_any_keyword(haystack, _TRUMP_KEYWORDS):
            continue
        if not _contains_any_keyword(haystack, _MARKET_IMPACT_KEYWORDS):
            continue
        key = item.get("url") or item.get("title") or ""
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _filter_geopolitical_updates(items: list[GlobalNewsItem], *, as_of: datetime, limit: int) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if not _contains_any_keyword(haystack, _GEOPOLITICAL_KEYWORDS):
            continue
        key = item.get("url") or item.get("title") or ""
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _empty_indicator(label: str, source: str, unit: str) -> MacroIndicatorValue:
    return {"label": label, "source": source, "unit": unit, "value": None, "observed_on": None}


def _empty_indicators_from_fred() -> dict[str, MacroIndicatorValue]:
    return {
        key: _empty_indicator(meta["label"], f"FRED:{meta['series_id']}", meta["unit"])
        for key, meta in _FRED_SERIES.items()
    }
