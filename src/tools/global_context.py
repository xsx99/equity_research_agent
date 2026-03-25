"""Global macro/context providers and tool for the research pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
import csv
import io
import os
import re
from typing import Any, Optional, Protocol, TypedDict

import httpx
from lxml import etree, html

from src.core.logging import get_logger
from src.tools.market_data import AlpacaMarketDataProvider
from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext

logger = get_logger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_TRUMP_KEYWORDS = (
    "trump",
    "president donald j. trump",
    "president trump",
    "donald j. trump",
)
_MARKET_IMPACT_KEYWORDS = (
    "tariff",
    "tariffs",
    "sanction",
    "sanctions",
    "treasury",
    "commerce",
    "export control",
    "export controls",
    "chip",
    "chips",
    "semiconductor",
    "ai",
    "artificial intelligence",
    "antitrust",
    "economy",
    "economic",
    "trade",
    "market",
    "markets",
    "oil",
    "energy",
    "iran",
    "china",
    "rates",
    "treasury yield",
    "credit",
)
_GEOPOLITICAL_KEYWORDS = (
    "war",
    "military",
    "troops",
    "missile",
    "airstrike",
    "airstrikes",
    "diplomatic",
    "ceasefire",
    "sanction",
    "tariff",
    "iran",
    "israel",
    "gaza",
    "ukraine",
    "russia",
    "china",
    "taiwan",
    "nato",
    "embassy",
    "mideast",
    "middle east",
    "oil",
    "energy",
    "shipping",
    "refinery",
    "defense",
)
_FRED_SERIES: dict[str, dict[str, str]] = {
    "oil_price": {
        "series_id": "DCOILWTICO",
        "label": "WTI Crude Oil Spot Price",
        "unit": "USD/bbl",
    },
    "gold_price": {
        "series_id": "GOLDAMGBD228NLBM",
        "label": "Gold Fixing Price",
        "unit": "USD/troy_oz",
    },
    "us_treasury_2y": {
        "series_id": "DGS2",
        "label": "US Treasury 2Y",
        "unit": "pct",
    },
    "us_treasury_10y": {
        "series_id": "DGS10",
        "label": "US Treasury 10Y",
        "unit": "pct",
    },
    "us_treasury_20y": {
        "series_id": "DGS20",
        "label": "US Treasury 20Y",
        "unit": "pct",
    },
    "credit_spread": {
        "series_id": "BAMLH0A0HYM2",
        "label": "ICE BofA US High Yield OAS",
        "unit": "pct",
    },
    "vix": {
        "series_id": "VIXCLS",
        "label": "CBOE Volatility Index",
        "unit": "index",
    },
}


class MacroIndicatorValue(TypedDict):
    """Normalized macro indicator value."""

    label: str
    source: str
    unit: str
    value: Optional[float]
    observed_on: Optional[str]


class GlobalNewsItem(TypedDict):
    """Normalized official or geopolitical news item."""

    source: str
    title: str
    summary: str
    published_at: Optional[str]
    url: Optional[str]


class GlobalContextSnapshot(TypedDict):
    """Replayable global context block stored inside research input_json."""

    as_of: str
    indicators: dict[str, MacroIndicatorValue]
    official_updates: list[GlobalNewsItem]
    trump_updates: list[GlobalNewsItem]
    geopolitical_news: list[GlobalNewsItem]


class MacroIndicatorProvider(Protocol):
    def fetch_indicators(self, as_of: datetime) -> dict[str, MacroIndicatorValue]:
        """Fetch the configured macro indicator set."""


class NewsFeedProvider(Protocol):
    def fetch_recent(self, limit: int) -> list[GlobalNewsItem]:
        """Fetch normalized official/geopolitical updates."""


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


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = slug.replace("-", " ").replace("_", " ").strip()
    return slug.title()


def _clean_title(text: str) -> str:
    title = " ".join(text.split()).strip()
    for suffix in (
        " | AP News",
        " - AP News",
        " | The White House",
        " - The White House",
    ):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def _contains_keyword(haystack: str, keyword: str) -> bool:
    escaped = re.escape(keyword.strip()).replace(r"\ ", r"\s+")
    pattern = rf"\b{escaped}\b"
    return re.search(pattern, haystack, flags=re.IGNORECASE) is not None


def _contains_any_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(_contains_keyword(haystack, keyword) for keyword in keywords)


def _extract_page_metadata(client: httpx.Client, url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    response = client.get(url)
    response.raise_for_status()
    doc = html.fromstring(response.text)

    def _first(xpath: str) -> Optional[str]:
        values = doc.xpath(xpath)
        for value in values:
            if isinstance(value, str):
                clean = " ".join(value.split()).strip()
                if clean:
                    return clean
        return None

    title = _first("//meta[@property='og:title']/@content")
    title = title or _first("//title/text()")
    summary = _first("//meta[@property='og:description']/@content")
    summary = summary or _first("//meta[@name='description']/@content")
    published_at = _first("//meta[@property='article:published_time']/@content")
    published_at = published_at or _first("//meta[@name='parsely-pub-date']/@content")
    if title:
        title = _clean_title(title)
    return title, summary, published_at


def _filter_trump_updates(
    items: list[GlobalNewsItem],
    *,
    as_of: datetime,
    limit: int,
) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen_keys: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if not _contains_any_keyword(haystack, _TRUMP_KEYWORDS):
            continue
        if not _contains_any_keyword(haystack, _MARKET_IMPACT_KEYWORDS):
            continue
        dedupe_key = item.get("url") or item.get("title") or ""
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _filter_official_updates(
    items: list[GlobalNewsItem],
    *,
    as_of: datetime,
    limit: int,
) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen_keys: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if _contains_any_keyword(haystack, _TRUMP_KEYWORDS):
            continue
        if not _contains_any_keyword(haystack, _MARKET_IMPACT_KEYWORDS):
            continue
        dedupe_key = item.get("url") or item.get("title") or ""
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _filter_geopolitical_updates(
    items: list[GlobalNewsItem],
    *,
    as_of: datetime,
    limit: int,
) -> list[GlobalNewsItem]:
    results: list[GlobalNewsItem] = []
    seen_keys: set[str] = set()
    for item in _sorted_recent_items(items):
        published_at = _parse_optional_datetime(item.get("published_at"))
        if published_at is None or (as_of - published_at).days > 3:
            continue
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if not _contains_any_keyword(haystack, _GEOPOLITICAL_KEYWORDS):
            continue
        dedupe_key = item.get("url") or item.get("title") or ""
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _sorted_recent_items(items: list[GlobalNewsItem]) -> list[GlobalNewsItem]:
    return sorted(
        items,
        key=lambda item: _parse_optional_datetime(item.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _empty_indicator(label: str, source: str, unit: str) -> MacroIndicatorValue:
    return {
        "label": label,
        "source": source,
        "unit": unit,
        "value": None,
        "observed_on": None,
    }


class FredMacroDataProvider:
    """Fetch macro indicators from FRED, falling back to the official CSV export."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def fetch_indicators(self, as_of: datetime) -> dict[str, MacroIndicatorValue]:
        indicators: dict[str, MacroIndicatorValue] = {}
        for key, metadata in _FRED_SERIES.items():
            indicators[key] = _empty_indicator(
                metadata["label"],
                f"FRED:{metadata['series_id']}",
                metadata["unit"],
            )
            try:
                value, observed_on = self._fetch_latest_observation(metadata["series_id"], as_of)
            except Exception as exc:
                logger.warning(
                    "global_context_fred_series_failed",
                    series_id=metadata["series_id"],
                    error=str(exc),
                )
                value, observed_on = None, None
            if value is None and key == "gold_price":
                value, observed_on = self._fetch_gold_proxy_from_market_data()
                if value is not None:
                    indicators[key]["label"] = "Gold Proxy (GLD ETF)"
                    indicators[key]["source"] = "ALPACA:GLD_PROXY"
                    indicators[key]["unit"] = "USD/share"
            indicators[key]["value"] = value
            indicators[key]["observed_on"] = observed_on
        return indicators

    def _fetch_latest_observation(
        self,
        series_id: str,
        as_of: datetime,
    ) -> tuple[Optional[float], Optional[str]]:
        if self.api_key:
            value, observed_on = self._fetch_from_api(series_id, as_of)
            if observed_on is not None:
                return value, observed_on
        return self._fetch_from_csv(series_id)

    def _fetch_from_api(
        self,
        series_id: str,
        as_of: datetime,
    ) -> tuple[Optional[float], Optional[str]]:
        response = self._client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_end": as_of.date().isoformat(),
                "sort_order": "desc",
                "limit": 10,
            },
        )
        response.raise_for_status()
        payload = response.json()
        observations = payload.get("observations", [])
        for row in observations:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if value in (None, "."):
                continue
            try:
                return float(value), str(row.get("date") or "")
            except (TypeError, ValueError):
                continue
        return None, None

    def _fetch_from_csv(self, series_id: str) -> tuple[Optional[float], Optional[str]]:
        response = self._client.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        last_value: Optional[float] = None
        last_date: Optional[str] = None
        for row in reader:
            value = row.get(series_id)
            if value in (None, "."):
                continue
            try:
                last_value = float(value)
            except (TypeError, ValueError):
                continue
            last_date = row.get("DATE")
        return last_value, last_date

    def _fetch_gold_proxy_from_market_data(self) -> tuple[Optional[float], Optional[str]]:
        provider = AlpacaMarketDataProvider()
        try:
            bars = provider.fetch_daily_bars("GLD", lookback_days=3)
        except Exception as exc:
            logger.warning("global_context_gold_proxy_failed", error=str(exc))
            return None, None
        finally:
            try:
                provider.close()
            except Exception:
                logger.warning("global_context_gold_proxy_close_failed")

        if not bars:
            return None, None
        latest_bar = bars[-1]
        observed_on = latest_bar.get("date")
        observed_iso = observed_on.isoformat() if observed_on is not None else None
        return latest_bar.get("close"), observed_iso

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


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
                logger.warning(
                    "white_house_page_metadata_failed",
                    url=url,
                    error=str(exc),
                )
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
            title = " ".join(anchor.xpath(".//text()")).strip()
            title = _clean_title(title)
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            title_lower = title.lower()
            score = 1 if any(keyword in title_lower for keyword in _GEOPOLITICAL_KEYWORDS) else 0
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


def get_global_context(
    *,
    as_of: Optional[Any] = None,
    limit: int = 5,
    macro_provider: Optional[MacroIndicatorProvider] = None,
    official_updates_provider: Optional[NewsFeedProvider] = None,
    trump_updates_provider: Optional[NewsFeedProvider] = None,
    geopolitical_provider: Optional[NewsFeedProvider] = None,
    include_official_updates: bool = False,
) -> GlobalContextSnapshot:
    """Build the replayable global context snapshot."""
    snapshot_as_of = _normalized_datetime(as_of)
    bounded_limit = max(1, min(limit, 5))

    created_macro = macro_provider is None
    macro = macro_provider or FredMacroDataProvider()
    official = official_updates_provider or WhiteHouseUpdatesProvider()
    trump = trump_updates_provider
    geopolitical = geopolitical_provider or APWorldNewsProvider()

    try:
        indicators = macro.fetch_indicators(snapshot_as_of)
    except Exception as exc:
        logger.warning("global_context_macro_failed", error=str(exc))
        indicators = {
            key: _empty_indicator(
                metadata["label"],
                f"FRED:{metadata['series_id']}",
                metadata["unit"],
            )
            for key, metadata in _FRED_SERIES.items()
        }

    official_candidates: list[GlobalNewsItem] = []
    if include_official_updates or trump is None:
        try:
            official_candidates = official.fetch_recent(max(bounded_limit * 3, 15))
        except Exception as exc:
            logger.warning("global_context_official_updates_failed", error=str(exc))
            official_candidates = []
    official_updates = _filter_official_updates(
        official_candidates,
        as_of=snapshot_as_of,
        limit=bounded_limit,
    ) if include_official_updates else []

    if trump is None:
        trump_candidates = official_candidates
    else:
        try:
            trump_candidates = trump.fetch_recent(max(bounded_limit * 3, 15))
        except Exception as exc:
            logger.warning("global_context_trump_updates_failed", error=str(exc))
            trump_candidates = []
    trump_updates = _filter_trump_updates(
        trump_candidates,
        as_of=snapshot_as_of,
        limit=bounded_limit,
    )

    try:
        geopolitical_candidates = geopolitical.fetch_recent(max(bounded_limit * 3, 15))
    except Exception as exc:
        logger.warning("global_context_geopolitical_failed", error=str(exc))
        geopolitical_candidates = []
    geopolitical_news = _filter_geopolitical_updates(
        geopolitical_candidates,
        as_of=snapshot_as_of,
        limit=bounded_limit,
    )

    return {
        "as_of": snapshot_as_of.isoformat(),
        "indicators": indicators,
        "official_updates": official_updates[:bounded_limit],
        "trump_updates": trump_updates[:bounded_limit],
        "geopolitical_news": geopolitical_news[:bounded_limit],
    }


class GlobalContextTool(BaseTool):
    """Fetch a replayable global macro/news context block."""

    name = "get_global_context"

    def __init__(
        self,
        *,
        macro_provider: Optional[MacroIndicatorProvider] = None,
        official_updates_provider: Optional[NewsFeedProvider] = None,
        trump_updates_provider: Optional[NewsFeedProvider] = None,
        geopolitical_provider: Optional[NewsFeedProvider] = None,
        include_official_updates: bool = False,
    ) -> None:
        self._macro_provider = macro_provider
        self._official_updates_provider = official_updates_provider
        self._trump_updates_provider = trump_updates_provider
        self._geopolitical_provider = geopolitical_provider
        self._include_official_updates = include_official_updates

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Fetch a replayable global context snapshot including macro "
                "indicators, official US government updates, Trump-related "
                "official updates, and geopolitical news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {
                        "type": "string",
                        "description": "Optional ISO-8601 timestamp for the snapshot.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum items per news bucket (1-5, default 5).",
                        "default": 5,
                    },
                },
                "required": [],
            },
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        try:
            return get_global_context(
                as_of=input.get("as_of"),
                limit=int(input.get("limit", 5)),
                macro_provider=self._macro_provider,
                official_updates_provider=self._official_updates_provider,
                trump_updates_provider=self._trump_updates_provider,
                geopolitical_provider=self._geopolitical_provider,
                include_official_updates=self._include_official_updates,
            )
        except Exception as exc:
            raise ToolError(str(exc), tool_name=self.name) from exc
