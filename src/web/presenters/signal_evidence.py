"""Shared helpers for rendering candidate/trade signal evidence."""
from __future__ import annotations

from typing import Any

from src.web.presenters.today_copy import operator_text

_EMPTY_MARKER = "No signal snapshot recorded for this candidate."

_TECHNICAL_KEYS = (
    "technical.return_20d",
    "technical.relative_volume",
    "technical.rs_vs_spy_1d",
    "technical.rs_vs_qqq_1d",
    "technical.rsi_3",
    "technical.drawdown_from_recent_high",
)
_FUNDAMENTAL_KEYS = (
    "fundamental.quality_score",
    "fundamental.revenue_growth_score",
    "fundamental.margin_trend_score",
    "fundamental.valuation_percentile",
)
_NEWS_EVENT_KEYS = (
    "events_news.sentiment_direction",
    "events_news.high_signal_news_count_24h",
    "events_news.catalyst_quality_score",
    "events_news.own_earnings_event_type",
    "events_news.guidance_news_flag",
    "events_news.analyst_upgrade_count",
    "news.sentiment_direction",
    "news.high_signal_news_count_24h",
    "news.catalyst_quality_score",
)
_INSIDER_KEYS = (
    "insider.insider_net_buy_value_30d",
    "insider.insider_cluster_buy_count_90d",
    "insider.officer_buy_flag",
    "insider.director_buy_flag",
)


def signal_bullets(evidence: dict[str, Any] | Any) -> tuple[str, ...]:
    flattened = _flatten_evidence(evidence)
    if not flattened:
        return (_EMPTY_MARKER,)

    bullets: list[str] = []
    technical = _signal_group_parts(flattened, _TECHNICAL_KEYS)
    fundamental = _signal_group_parts(flattened, _FUNDAMENTAL_KEYS)
    news = _signal_group_parts(flattened, _NEWS_EVENT_KEYS + _INSIDER_KEYS)

    if technical:
        bullets.append(f"Technical: {', '.join(technical)}.")
    if fundamental:
        bullets.append(f"Fundamental: {', '.join(fundamental)}.")
    if news:
        bullets.append(f"News: {', '.join(news)}.")
    return tuple(bullets) if bullets else (_EMPTY_MARKER,)


def signal_groups(evidence: dict[str, Any] | Any) -> tuple[dict[str, Any], ...]:
    flattened = _flatten_evidence(evidence)
    if not flattened:
        return ()

    groups: list[dict[str, Any]] = []
    for key, label, keys in (
        ("technical", "Technical", _TECHNICAL_KEYS),
        ("fundamental", "Fundamental", _FUNDAMENTAL_KEYS),
        ("news_events", "News & Events", _NEWS_EVENT_KEYS),
        ("insider", "Insider", _INSIDER_KEYS),
    ):
        bullets = _signal_group_parts(flattened, keys)
        if bullets:
            groups.append({"key": key, "label": label, "bullets": tuple(bullets)})
    return tuple(groups)


def clean_copy(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return operator_text(text)


def clean_fragment(value: Any) -> str | None:
    text = clean_copy(value)
    if not text:
        return None
    return text.rstrip(".")


def _signal_group_parts(flattened: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    for key in keys:
        part = _signal_part(key, flattened.get(key))
        if part:
            parts.append(part)
    return parts


def _signal_part(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        if not value:
            return None
        mapping = {
            "events_news.guidance_news_flag": "guidance news",
            "insider.officer_buy_flag": "officer buying",
            "insider.director_buy_flag": "director buying",
        }
        return mapping.get(key)

    number = _as_float(value)
    if key == "technical.return_20d" and number is not None:
        return f"20d return {number * 100:.2f}%"
    if key == "technical.relative_volume" and number is not None:
        return f"relative volume {number:.2f}"
    if key == "technical.rs_vs_spy_1d" and number is not None:
        return f"RS vs SPY {number * 100:.2f}%"
    if key == "technical.rs_vs_qqq_1d" and number is not None:
        return f"RS vs QQQ {number * 100:.2f}%"
    if key == "technical.rsi_3" and number is not None:
        return f"3d RSI {number:.2f}"
    if key == "technical.drawdown_from_recent_high" and number is not None:
        return f"drawdown from recent high {number * 100:.2f}%"
    if key == "fundamental.quality_score" and number is not None:
        return f"quality {number:.2f}"
    if key == "fundamental.revenue_growth_score" and number is not None:
        return f"revenue growth {number:.2f}"
    if key == "fundamental.margin_trend_score" and number is not None:
        return f"margin trend {number:.2f}"
    if key == "fundamental.valuation_percentile" and number is not None:
        return f"valuation percentile {number:.2f}"
    if key in {"events_news.sentiment_direction", "news.sentiment_direction"}:
        text = clean_fragment(value)
        return f"sentiment {text}" if text else None
    if key in {"events_news.high_signal_news_count_24h", "news.high_signal_news_count_24h"} and number is not None:
        count = int(number) if float(number).is_integer() else number
        return f"{count} high-signal items / 24h"
    if key in {"events_news.catalyst_quality_score", "news.catalyst_quality_score"} and number is not None:
        return f"catalyst quality {number:.2f}"
    if key == "events_news.own_earnings_event_type":
        text = clean_fragment(value)
        return f"earnings event {text}" if text else None
    if key == "events_news.analyst_upgrade_count" and number is not None:
        count = int(number) if float(number).is_integer() else number
        noun = "upgrade" if count == 1 else "upgrades"
        return f"{count} analyst {noun}"
    if key == "insider.insider_net_buy_value_30d" and number is not None:
        return f"insider net buy ${number:,.0f} / 30d"
    if key == "insider.insider_cluster_buy_count_90d" and number is not None:
        count = int(number) if float(number).is_integer() else number
        noun = "cluster buy" if count == 1 else "cluster buys"
        return f"{count} insider {noun} / 90d"

    text = clean_fragment(value)
    return text or None


def _flatten_evidence(evidence: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    flattened: dict[str, Any] = {}
    for raw_key, raw_value in evidence.items():
        key = str(raw_key).strip()
        if not key:
            continue
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(raw_value, dict):
            flattened.update(_flatten_evidence(raw_value, full_key))
            continue
        flattened[full_key] = raw_value
    return flattened


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
