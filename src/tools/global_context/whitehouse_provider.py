"""White House updates provider."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from lxml import etree

from src.core.logging import get_logger
from src.tools.global_context.helpers import (
    _extract_page_metadata,
    _normalized_news_item,
    _parse_optional_datetime,
    _title_from_url,
)
from src.tools.global_context.types import GlobalNewsItem

logger = get_logger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class WhiteHouseUpdatesProvider:
    """Fetch recent White House posts from the public sitemap."""

    SITEMAP_URL = "https://www.whitehouse.gov/post-sitemap.xml"

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_recent(self, limit: int) -> list[GlobalNewsItem]:
        response = self._client.get(self.SITEMAP_URL)
        response.raise_for_status()
        root = etree.fromstring(response.content)
        candidates: list[tuple[datetime, str, str]] = []
        for node in root.xpath("//sm:url", namespaces=_SITEMAP_NS):
            loc = "".join(node.xpath("./sm:loc/text()", namespaces=_SITEMAP_NS)).strip()
            lastmod = "".join(node.xpath("./sm:lastmod/text()", namespaces=_SITEMAP_NS)).strip()
            if not loc or loc.endswith("/news/"):
                continue
            parsed_lastmod = _parse_optional_datetime(lastmod) or datetime.min.replace(tzinfo=timezone.utc)
            candidates.append((parsed_lastmod, loc, lastmod))

        candidates.sort(key=lambda item: item[0], reverse=True)
        items: list[GlobalNewsItem] = []
        for _, url, lastmod in candidates[: max(limit * 3, 8)]:
            try:
                title, summary, published_at = _extract_page_metadata(self._client, url)
            except Exception as exc:
                logger.warning("white_house_page_metadata_failed", url=url, error=str(exc))
                title, summary, published_at = None, None, None
            item = _normalized_news_item(
                source="whitehouse.gov",
                title=title or _title_from_url(url),
                summary=summary,
                published_at=published_at or lastmod or None,
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
