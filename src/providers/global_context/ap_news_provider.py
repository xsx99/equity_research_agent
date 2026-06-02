"""AP World News geopolitical feed provider."""
from __future__ import annotations

from typing import Optional

import httpx
from lxml import html

from src.core.logging import get_logger
from src.providers.global_context.helpers import (
    _clean_title,
    _extract_page_metadata,
    _normalized_news_item,
)
from src.providers.global_context.types import GlobalNewsItem, _GEOPOLITICAL_KEYWORDS

logger = get_logger(__name__)


class APWorldNewsProvider:
    """Fetch top AP World News headlines as the geopolitical feed."""

    WORLD_NEWS_URL = "https://apnews.com/world-news"

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None

    def fetch_recent(self, limit: int) -> list[GlobalNewsItem]:
        response = self._client.get(self.WORLD_NEWS_URL)
        response.raise_for_status()
        doc = html.fromstring(response.text)
        candidates: list[tuple[int, str, str]] = []
        seen_urls: set[str] = set()

        for anchor in doc.xpath("//a[starts-with(@href, 'https://apnews.com/article/')]"):
            url = str(anchor.get("href", "")).strip()
            title = _clean_title(" ".join(anchor.xpath(".//text()")).strip())
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            score = 1 if any(kw in title.lower() for kw in _GEOPOLITICAL_KEYWORDS) else 0
            candidates.append((score, url, title))

        candidates.sort(key=lambda item: item[0], reverse=True)
        items: list[GlobalNewsItem] = []
        for _, url, title in candidates[: max(limit * 3, 10)]:
            try:
                page_title, summary, published_at = _extract_page_metadata(self._client, url)
            except Exception as exc:
                logger.warning("ap_world_page_metadata_failed", url=url, error=str(exc))
                page_title, summary, published_at = None, None, None
            item = _normalized_news_item(
                source="AP News",
                title=page_title or title,
                summary=summary,
                published_at=published_at,
                url=url,
            )
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
