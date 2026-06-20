"""Internal helpers for deterministic news normalization and condensation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from src.providers.news_data.types import NewsItem


_LOW_SIGNAL_TITLE_PATTERNS = (
    re.compile(r"\bis it too late\b", flags=re.IGNORECASE),
    re.compile(r"\bshould you buy\b", flags=re.IGNORECASE),
    re.compile(r"\bto buy now\b", flags=re.IGNORECASE),
    re.compile(r"\bwhy .* stock .* (up|down) today\b", flags=re.IGNORECASE),
    re.compile(r"\btop \d+ .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bbest .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bprediction\b", flags=re.IGNORECASE),
)
_COMPANY_CATALYST_TERMS = (
    "upgrade",
    "downgrade",
    "price target",
    "guidance",
    "outlook",
    "forecast",
    "preliminary",
    "earnings",
    "revenue",
    "eps",
    "sec",
    "8-k",
    "10-q",
    "10-k",
    "form 4",
    "offering",
    "bankruptcy",
    "litigation",
    "lawsuit",
    "recall",
    "customer",
    "contract",
    "order",
    "launch",
    "acquire",
    "merger",
    "regulatory",
    "fda",
    "approval",
    "probe",
)
_GENERIC_GENERAL_NEWS_PATTERNS = (
    re.compile(r"\b(in focus|stocks? to watch|market recap|morning news|midday update)\b", flags=re.IGNORECASE),
    re.compile(r"\bone fund\b", flags=re.IGNORECASE),
    re.compile(r"\bmake .* a year\b", flags=re.IGNORECASE),
    re.compile(r"\bcompounds?\b", flags=re.IGNORECASE),
    re.compile(r"\bretire(?:ment)?\b", flags=re.IGNORECASE),
    re.compile(r"\bthese .* stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bbest stocks?\b", flags=re.IGNORECASE),
    re.compile(r"\bmotley\b", flags=re.IGNORECASE),
    re.compile(r"\bshould you buy\b", flags=re.IGNORECASE),
    re.compile(r"\bstocks? to buy\b", flags=re.IGNORECASE),
)
_SIGNAL_TYPE_PRIORITY = {
    "earnings_guidance": 120,
    "sec_filing": 115,
    "analyst_rating": 110,
    "earnings": 100,
    "company_update": 90,
    "general_news": 70,
}
_IMPORTANCE_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "normal": 1, "low": 0}
_BROKER_PATTERNS = (
    "morgan stanley",
    "goldman sachs",
    "jpmorgan",
    "bank of america",
    "ubs",
    "barclays",
    "jefferies",
    "evercore isi",
    "wedbush",
    "bernstein",
    "citi",
    "citigroup",
)
_NEGATIVE_EVENT_TYPES = {
    "analyst_downgrade",
    "guidance_cut",
    "offering",
    "bankruptcy",
    "litigation",
    "recall",
    "regulatory_action",
}
_POSITIVE_EVENT_TYPES = {
    "analyst_upgrade",
    "guidance_raise",
    "earnings_beat_raise",
    "customer_order",
    "customer_win",
    "product_launch",
    "price_target_revision",
}


@dataclass(frozen=True)
class CondensedNewsItem:
    title: str
    summary: str
    source: str | None
    url: str | None
    signal_type: str
    event_type: str
    sentiment: str | None
    importance: str
    published_at: datetime
    available_for_decision_at: datetime
    normalized_headline: str
    specificity_score: int
    duplicate_group_key: str
    duplicate_count: int
    dropped_sources: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class NewsCondensationResult:
    kept_items: tuple[CondensedNewsItem, ...]
    raw_news_item_count: int
    kept_news_item_count: int
    dropped_low_signal_count: int
    dropped_duplicate_count: int
    dropped_irrelevant_count: int


@dataclass(frozen=True)
class _CandidateNewsItem:
    title: str
    summary: str
    source: str | None
    url: str | None
    signal_type: str
    event_type: str
    sentiment: str | None
    importance: str
    published_at: datetime
    available_for_decision_at: datetime
    normalized_headline: str
    specificity_score: int
    duplicate_group_key: str
    source_identity: str


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _strip_templated_tail(value: str) -> str:
    cleaned = _collapse_whitespace(value)
    return re.sub(r"\s+[-|]\s+(business wire|globe newswire|pr newswire|reuters|dow jones)\s*$", "", cleaned, flags=re.IGNORECASE)


def _normalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _looks_low_signal(title: str) -> bool:
    normalized = _collapse_whitespace(title)
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
    clean_title = _strip_templated_tail(title or "")
    if not clean_title:
        return None
    clean_summary = _strip_templated_tail(summary or "")
    normalized_signal_type = signal_type or _infer_signal_type(clean_title, clean_summary, source=source)
    return {
        "title": clean_title,
        "summary": clean_summary,
        "published_at": published_at,
        "source": _collapse_whitespace(source or "") or None,
        "url": _normalize_url(url),
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


def parse_news_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(raw), time.min)
            except ValueError:
                return fallback
        return _ensure_aware(parsed)
    return fallback


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def infer_news_event_type(signal_type: str, title: str, summary: str) -> str:
    text = f"{title} {summary}".casefold()
    normalized_type = signal_type.strip().casefold()
    if "bankruptcy" in text or "chapter 11" in text or "insolvency" in text:
        return "bankruptcy"
    if "offering" in text or "convertible notes" in text or "secondary offering" in text:
        return "offering"
    if "litigation" in text or "lawsuit" in text or "sues" in text or "legal" in text:
        return "litigation"
    if "recall" in text:
        return "recall"
    if any(keyword in text for keyword in ("regulatory", "fda", "antitrust", "probe", "investigation", "doj", "sec investigates")):
        return "regulatory_action"
    if any(keyword in text for keyword in ("merger", "acquisition", "acquire", "buyout", "strategic transaction")):
        return "m&a"
    if normalized_type == "analyst_rating":
        if "downgrade" in text or "cuts to" in text:
            return "analyst_downgrade"
        if "upgrade" in text or "raises to overweight" in text or "raises to buy" in text:
            return "analyst_upgrade"
        if "price target" in text or "target to $" in text or "target price" in text or "pt raised" in text:
            return "price_target_revision"
        return "analyst_rating"
    if normalized_type == "earnings_guidance":
        if "preliminary" in text:
            return "preliminary_results"
        if ("beat" in text or "tops estimates" in text) and ("raise" in text or "raised guidance" in text):
            return "earnings_beat_raise"
        if any(keyword in text for keyword in ("cut guidance", "lowers guidance", "guidance cut", "cuts outlook")):
            return "guidance_cut"
        if any(keyword in text for keyword in ("raises guidance", "lifts guidance", "raises outlook", "boosts forecast")):
            return "guidance_raise"
        return "guidance_news"
    if normalized_type == "earnings":
        if ("beat" in text or "tops estimates" in text) and ("raise" in text or "raised guidance" in text):
            return "earnings_beat_raise"
        return "own_earnings_headline"
    if normalized_type == "sec_filing":
        if "form 8-k" in text or "8-k" in text:
            return "form_8k"
        if "form 10-q" in text or "10-q" in text:
            return "form_10q"
        if "form 10-k" in text or "10-k" in text:
            return "form_10k"
        if "form 4" in text:
            return "form_4"
        return "sec_filing"
    if any(keyword in text for keyword in ("customer order", "order commitment", "order expansion", "supply agreement", "contract award")):
        return "customer_order"
    if any(keyword in text for keyword in ("customer win", "wins contract", "selected by customer", "partnership")):
        return "customer_win"
    if any(keyword in text for keyword in ("product launch", "launches", "launch event", "unveils")):
        return "product_launch"
    return "general_news"


def infer_news_sentiment(title: str, summary: str, event_type: str) -> str | None:
    text = f"{title} {summary}".casefold()
    if event_type in _NEGATIVE_EVENT_TYPES:
        return "negative"
    if event_type in _POSITIVE_EVENT_TYPES:
        return "positive"
    negative_words = ("downgrade", "cut", "miss", "warning", "falls", "declines", "probe", "investigation")
    positive_words = ("upgrade", "raise", "beat", "stronger", "wins", "launch", "approval", "accelerates")
    if any(word in text for word in negative_words):
        return "negative"
    if any(word in text for word in positive_words):
        return "positive"
    return None


def news_importance(signal_type: str, event_type: str) -> str:
    normalized_signal_type = signal_type.strip().casefold()
    if event_type in {"bankruptcy", "offering"}:
        return "critical"
    if event_type in {
        "analyst_upgrade",
        "analyst_downgrade",
        "price_target_revision",
        "guidance_raise",
        "guidance_cut",
        "earnings_beat_raise",
        "preliminary_results",
        "form_8k",
        "form_10q",
        "form_10k",
        "form_4",
        "sec_filing",
        "regulatory_action",
        "customer_order",
        "customer_win",
        "product_launch",
        "litigation",
        "recall",
        "m&a",
    }:
        return "high"
    if normalized_signal_type in {"earnings_guidance", "analyst_rating", "earnings", "sec_filing"}:
        return "high"
    if normalized_signal_type == "company_update":
        return "medium"
    return "low"

def _core_company_name(company_name: str | None) -> str:
    if not company_name:
        return ""
    words = re.findall(r"[a-z0-9]+", company_name.casefold())
    while words and words[-1] in {
        "inc",
        "corp",
        "corporation",
        "co",
        "company",
        "holdings",
        "holding",
        "group",
        "plc",
        "ltd",
        "limited",
        "sa",
        "ag",
        "nv",
        "llc",
    }:
        words.pop()
    return " ".join(words)


def _mentions_ticker_or_company(text: str, ticker: str, company_name: str | None) -> bool:
    normalized_ticker = ticker.strip().casefold()
    if normalized_ticker and re.search(rf"\b{re.escape(normalized_ticker)}\b", text):
        return True
    core_name = _core_company_name(company_name)
    if not core_name:
        return False
    return core_name in text


def _is_irrelevant_general_news(
    title: str,
    summary: str,
    signal_type: str,
    event_type: str,
    *,
    ticker: str,
    company_name: str | None = None,
) -> bool:
    if signal_type != "general_news" or event_type != "general_news":
        return False
    text = f"{title} {summary}".casefold()
    if any(term in text for term in _COMPANY_CATALYST_TERMS):
        return False
    if not _mentions_ticker_or_company(text, ticker, company_name):
        return True
    return False


def _extract_money_values(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\$?\d+(?:\.\d+)?", text))


def _extract_broker(text: str) -> str | None:
    for broker in _BROKER_PATTERNS:
        if broker in text:
            return broker.replace(" ", "_")
    return None


def _text_signature(text: str) -> str:
    tokens = [token for token in re.findall(r"[a-z0-9]+", text) if token not in {"the", "and", "after", "with", "for", "from"}]
    return "-".join(tokens[:8])


def _time_bucket(published_at: datetime) -> str:
    bucket_hour = (published_at.hour // 6) * 6
    return published_at.replace(hour=bucket_hour, minute=0, second=0, microsecond=0).isoformat()


def _headline_signature(event_type: str, title: str, summary: str) -> str:
    text = f"{title} {summary}".casefold()
    pieces = [event_type]
    broker = _extract_broker(text)
    if broker:
        pieces.append(f"broker:{broker}")
    if event_type in {"analyst_upgrade", "analyst_downgrade", "price_target_revision"}:
        money_values = _extract_money_values(text)
        if money_values:
            pieces.extend(f"money:{value}" for value in money_values[:2])
    elif event_type.startswith("form_") or event_type == "sec_filing":
        pieces.append(event_type)
    elif event_type in {"guidance_raise", "guidance_cut", "earnings_beat_raise", "offering", "m&a"}:
        money_values = _extract_money_values(text)
        if money_values:
            pieces.extend(f"money:{value}" for value in money_values[:3])
    else:
        pieces.append(_text_signature(text))
    return "|".join(pieces)


def _specificity_score(title: str, summary: str, signal_type: str, event_type: str) -> int:
    text = f"{title} {summary}".casefold()
    score = _SIGNAL_TYPE_PRIORITY.get(signal_type, 0) // 10
    score += min(len(_extract_money_values(text)), 3)
    score += 2 if _extract_broker(text) else 0
    score += 2 if event_type != "general_news" else 0
    score += 1 if summary.strip() else 0
    score += 1 if any(keyword in text for keyword in ("guidance", "target", "form", "contract", "launch", "offering")) else 0
    return score


def condense_news_items(
    *,
    ticker: str,
    company_name: str | None = None,
    items: list[NewsItem] | tuple[NewsItem, ...],
    as_of: datetime,
) -> NewsCondensationResult:
    candidates: list[_CandidateNewsItem] = []
    dropped_low_signal_count = 0
    dropped_irrelevant_count = 0

    for raw_item in items:
        normalized = _normalize_provider_news_item(raw_item)
        if normalized is None:
            dropped_irrelevant_count += 1
            continue
        title = str(normalized["title"])
        summary = str(normalized.get("summary") or "")
        signal_type = str(normalized.get("signal_type") or "general_news")
        event_type = infer_news_event_type(signal_type, title, summary)
        if _looks_low_signal(title):
            dropped_low_signal_count += 1
            continue
        if _is_irrelevant_general_news(
            title,
            summary,
            signal_type,
            event_type,
            ticker=ticker,
            company_name=company_name,
        ):
            dropped_irrelevant_count += 1
            continue
        published_at = parse_news_datetime(normalized.get("published_at"), fallback=as_of)
        available_for_decision_at = max(published_at, _ensure_aware(as_of))
        normalized_headline = _collapse_whitespace(title).casefold()
        specificity_score = _specificity_score(title, summary, signal_type, event_type)
        duplicate_group_key = "|".join(
            (
                ticker.strip().upper(),
                event_type,
                _headline_signature(event_type, title, summary),
                _time_bucket(published_at),
            )
        )
        source_identity = str(normalized.get("source") or "").strip() or "unknown"
        candidates.append(
            _CandidateNewsItem(
                title=title,
                summary=summary,
                source=normalized.get("source"),
                url=normalized.get("url"),
                signal_type=signal_type,
                event_type=event_type,
                sentiment=infer_news_sentiment(title, summary, event_type),
                importance=news_importance(signal_type, event_type),
                published_at=published_at,
                available_for_decision_at=available_for_decision_at,
                normalized_headline=normalized_headline,
                specificity_score=specificity_score,
                duplicate_group_key=duplicate_group_key,
                source_identity=source_identity,
            )
        )

    grouped: dict[str, list[_CandidateNewsItem]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.duplicate_group_key, []).append(candidate)

    kept_items: list[CondensedNewsItem] = []
    dropped_duplicate_count = 0
    for duplicate_group_key, group in sorted(grouped.items()):
        ranked = sorted(
            group,
            key=lambda item: (
                item.available_for_decision_at,
                item.published_at,
                -item.specificity_score,
                -(len(item.title) + len(item.summary)),
                item.source_identity.casefold(),
                item.url or item.title,
            ),
        )
        representative = ranked[0]
        duplicates = ranked[1:]
        dropped_duplicate_count += len(duplicates)
        dropped_sources = tuple(dict.fromkeys(item.source_identity for item in duplicates))
        metadata = {
            "signal_type": representative.signal_type,
            "normalized_headline": representative.normalized_headline,
            "specificity_score": representative.specificity_score,
            "compression_status": "kept",
            "compression_reason": "deduped_representative" if duplicates else "unique_item",
            "duplicate_group_key": duplicate_group_key,
            "duplicate_count": len(group),
            "dropped_sources": list(dropped_sources),
            "retained_rank_reason": "earliest_available_then_specificity",
        }
        kept_items.append(
            CondensedNewsItem(
                title=representative.title,
                summary=representative.summary,
                source=representative.source,
                url=representative.url,
                signal_type=representative.signal_type,
                event_type=representative.event_type,
                sentiment=representative.sentiment,
                importance=representative.importance,
                published_at=representative.published_at,
                available_for_decision_at=representative.available_for_decision_at,
                normalized_headline=representative.normalized_headline,
                specificity_score=representative.specificity_score,
                duplicate_group_key=duplicate_group_key,
                duplicate_count=len(group),
                dropped_sources=dropped_sources,
                metadata=metadata,
            )
        )

    kept_items.sort(key=lambda item: (item.published_at, item.duplicate_group_key))
    return NewsCondensationResult(
        kept_items=tuple(kept_items),
        raw_news_item_count=len(items),
        kept_news_item_count=len(kept_items),
        dropped_low_signal_count=dropped_low_signal_count,
        dropped_duplicate_count=dropped_duplicate_count,
        dropped_irrelevant_count=dropped_irrelevant_count,
    )


def _rank_and_filter_news_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    condensed = condense_news_items(
        ticker="UNKNOWN",
        items=items,
        as_of=datetime.now(timezone.utc),
    )
    kept: list[NewsItem] = []
    for item in condensed.kept_items:
        kept.append(
            {
                "title": item.title,
                "summary": item.summary,
                "published_at": item.published_at.isoformat(),
                "source": item.source,
                "url": item.url,
                "signal_type": item.signal_type,
            }
        )
    kept.sort(
        key=lambda item: (
            _SIGNAL_TYPE_PRIORITY.get(item.get("signal_type") or "general_news", 0),
            item.get("published_at") or "",
        ),
        reverse=True,
    )
    return kept[:limit]
