"""Ticker detail loader helpers for the today router."""
from __future__ import annotations

from typing import Any

from src.db.models.trading import EventNewsItem, IntradaySignalSnapshot, NewsAlert, SignalSnapshot
from src.web.routers import today_loaders


def _load_signal_history_by_ticker(
    session: Any,
    *,
    tickers: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    ticker_scope = _normalize_ticker_scope(tickers)
    signal_query = session.query(SignalSnapshot)
    intraday_query = session.query(IntradaySignalSnapshot)
    if ticker_scope is not None:
        signal_query = signal_query.filter(SignalSnapshot.ticker.in_(ticker_scope))
        intraday_query = intraday_query.filter(IntradaySignalSnapshot.ticker.in_(ticker_scope))
    signal_rows = (
        signal_query
        .order_by(SignalSnapshot.decision_time.desc(), SignalSnapshot.created_at.desc())
        .limit(100)
        .all()
    )
    intraday_rows = (
        intraday_query
        .order_by(IntradaySignalSnapshot.decision_time.desc(), IntradaySignalSnapshot.created_at.desc())
        .limit(100)
        .all()
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in signal_rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        entry = grouped.setdefault(ticker, {"technical": [], "summary": [], "timeline": []})
        signal_json = row.signal_json if isinstance(row.signal_json, dict) else {}

        technical_items = signal_json.get("technical")
        if isinstance(technical_items, list):
            for item in technical_items:
                if isinstance(item, dict):
                    entry["technical"].append(item)
        elif isinstance(technical_items, dict):
            entry["technical"].extend(_technical_history_items(technical_items))

        summary_items = signal_json.get("summary")
        if isinstance(summary_items, list):
            for item in summary_items:
                if str(item).strip():
                    entry["summary"].append(str(item).strip())
        else:
            entry["summary"].extend(_signal_summary_items(signal_json))

        entry["timeline"].append(
            {
                "time": row.decision_time,
                "event_type": row.snapshot_type or "signal_snapshot",
                "summary": _timeline_summary_from_signal(signal_json),
            }
        )

    for row in intraday_rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        entry = grouped.setdefault(ticker, {"technical": [], "summary": [], "timeline": []})
        delta = row.delta_vs_baseline_json if isinstance(row.delta_vs_baseline_json, dict) else {}
        if delta:
            entry["summary"].append(", ".join(sorted(delta.keys())))
        entry["timeline"].append(
            {
                "time": row.decision_time,
                "event_type": "intraday",
                "summary": ", ".join(sorted(delta.keys())) if delta else "Intraday refresh",
            }
        )

    return grouped


def _load_news_by_ticker(
    session: Any,
    *,
    tickers: tuple[str, ...] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    ticker_scope = _normalize_ticker_scope(tickers)
    alert_query = session.query(NewsAlert)
    event_query = session.query(EventNewsItem)
    if ticker_scope is not None:
        alert_query = alert_query.filter(NewsAlert.ticker.in_(ticker_scope))
        event_query = event_query.filter(EventNewsItem.ticker.in_(ticker_scope))
    alert_rows = (
        alert_query
        .order_by(NewsAlert.published_at.desc(), NewsAlert.created_at.desc())
        .limit(100)
        .all()
    )
    event_rows = (
        event_query
        .order_by(EventNewsItem.published_at.desc(), EventNewsItem.available_for_decision_at.desc())
        .limit(100)
        .all()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str, str | None]] = set()
    for row in alert_rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        _append_news_snippet(
            grouped,
            seen,
            ticker=ticker,
            title=row.headline,
            summary=row.summary,
            published_at=row.published_at,
            source=getattr(row, "source", None),
            sentiment=getattr(row, "sentiment", None),
            source_ticker=getattr(row, "source_ticker", None),
            readthrough_source_ticker=getattr(row, "readthrough_source_ticker", None),
        )
    for row in event_rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        _append_news_snippet(
            grouped,
            seen,
            ticker=ticker,
            title=row.headline,
            summary=row.summary,
            published_at=row.published_at,
            event_type=getattr(row, "event_type", None),
            importance=getattr(row, "importance", None),
            source=getattr(row, "provider", None),
            sentiment=getattr(row, "sentiment", None),
            source_ticker=getattr(row, "source_ticker", None),
            explicit_ticker_mention=getattr(row, "explicit_ticker_mention_flag", None),
        )
    return grouped


def _load_fundamentals_by_ticker(
    session: Any,
    *,
    tickers: tuple[str, ...] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    ticker_scope = _normalize_ticker_scope(tickers)
    query = session.query(SignalSnapshot)
    if ticker_scope is not None:
        query = query.filter(SignalSnapshot.ticker.in_(ticker_scope))
    rows = (
        query
        .order_by(SignalSnapshot.decision_time.desc(), SignalSnapshot.created_at.desc())
        .limit(100)
        .all()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        signal_json = row.signal_json if isinstance(row.signal_json, dict) else {}
        items = grouped.setdefault(ticker, [])
        fundamentals = signal_json.get("fundamentals")
        if isinstance(fundamentals, list):
            for item in fundamentals:
                if not isinstance(item, dict):
                    continue
                items.append(
                    {
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "as_of": row.decision_time,
                    }
                )
            continue

        fundamental_metrics = signal_json.get("fundamental")
        if isinstance(fundamental_metrics, dict):
            items.extend(_fundamental_snippets_from_metrics(fundamental_metrics, row.decision_time))
    return grouped


def _normalize_ticker_scope(tickers: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if tickers is None:
        return None
    normalized = tuple(
        dict.fromkeys(
            ticker
            for raw_ticker in tickers
            if (ticker := str(raw_ticker or "").strip().upper())
        )
    )
    return normalized or None


def _timeline_summary_from_signal(signal_json: dict[str, Any]) -> str:
    summary_items = signal_json.get("summary")
    if isinstance(summary_items, list):
        for item in summary_items:
            text = str(item).strip()
            if text:
                return text
    derived_items = _signal_summary_items(signal_json)
    if derived_items:
        return derived_items[0]
    return "Signal snapshot updated"


def _technical_history_items(technical: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "label": "price",
            "points": [
                value
                for value in (
                    technical.get("price_vs_sma_200"),
                    technical.get("price_vs_sma_50"),
                    technical.get("price_vs_sma_20"),
                    technical.get("return_20d"),
                )
                if today_loaders._is_number(value)
            ],
            "summary": _price_technical_summary(technical),
        },
        {
            "label": "relative_strength",
            "points": [
                value
                for value in (
                    technical.get("rs_vs_spy_1d"),
                    technical.get("rs_vs_qqq_1d"),
                    technical.get("relative_volume"),
                )
                if today_loaders._is_number(value)
            ],
            "summary": _relative_strength_summary(technical),
        },
    ]


def _signal_summary_items(signal_json: dict[str, Any]) -> list[str]:
    items: list[str] = []
    events_news = signal_json.get("events_news")
    technical = signal_json.get("technical")
    fundamental = signal_json.get("fundamental")

    if isinstance(events_news, dict):
        negative_catalyst = str(events_news.get("direct_negative_catalyst_type") or "").strip()
        sentiment = str(events_news.get("sentiment_direction") or "").strip()
        catalyst_quality = events_news.get("catalyst_quality_score")
        if negative_catalyst:
            items.append(
                f"Events/news sentiment {sentiment or 'negative'}; direct negative catalyst: {negative_catalyst}."
            )
        elif sentiment:
            quality_text = (
                f"; catalyst quality {today_loaders._format_decimal(catalyst_quality)}"
                if today_loaders._is_number(catalyst_quality)
                else ""
            )
            items.append(f"Events/news sentiment {sentiment}{quality_text}.")

    if isinstance(technical, dict):
        technical_bits: list[str] = []
        if today_loaders._is_number(technical.get("return_20d")):
            technical_bits.append(f"20d return {today_loaders._format_pct(technical['return_20d'])}")
        if today_loaders._is_number(technical.get("relative_volume")):
            technical_bits.append(f"relative volume {today_loaders._format_decimal(technical['relative_volume'])}")
        if technical_bits:
            items.append(f"Technical: {', '.join(technical_bits)}.")

    if isinstance(fundamental, dict):
        fundamental_bits: list[str] = []
        if today_loaders._is_number(fundamental.get("quality_score")):
            fundamental_bits.append(f"quality {today_loaders._format_decimal(fundamental['quality_score'])}")
        if today_loaders._is_number(fundamental.get("revenue_growth_score")):
            fundamental_bits.append(f"revenue growth {today_loaders._format_decimal(fundamental['revenue_growth_score'])}")
        if today_loaders._is_number(fundamental.get("margin_trend_score")):
            fundamental_bits.append(f"margin trend {today_loaders._format_decimal(fundamental['margin_trend_score'])}")
        if today_loaders._is_number(fundamental.get("valuation_percentile")):
            fundamental_bits.append(f"valuation percentile {today_loaders._format_decimal(fundamental['valuation_percentile'])}")
        if fundamental_bits:
            items.append(f"Fundamental: {', '.join(fundamental_bits)}.")

    return items


def _price_technical_summary(technical: dict[str, Any]) -> str:
    parts: list[str] = []
    if today_loaders._is_number(technical.get("return_20d")):
        parts.append(f"20d return {today_loaders._format_pct(technical['return_20d'])}")
    below_levels = [
        label
        for key, label in (
            ("price_vs_sma_20", "SMA20"),
            ("price_vs_sma_50", "SMA50"),
            ("price_vs_sma_200", "SMA200"),
        )
        if today_loaders._is_number(technical.get(key)) and float(technical[key]) < 0
    ]
    if below_levels:
        if len(below_levels) == 1:
            parts.append(f"below {below_levels[0]}")
        elif len(below_levels) == 2:
            parts.append(f"below {below_levels[0]} and {below_levels[1]}")
        else:
            parts.append(f"below {', '.join(below_levels[:-1])}, and {below_levels[-1]}")
    return "; ".join(parts) if parts else "Price trend unavailable"


def _relative_strength_summary(technical: dict[str, Any]) -> str:
    parts: list[str] = []
    if today_loaders._is_number(technical.get("rs_vs_spy_1d")):
        parts.append(f"RS vs SPY {today_loaders._format_pct(technical['rs_vs_spy_1d'])}")
    else:
        parts.append("RS vs SPY unavailable")
    if today_loaders._is_number(technical.get("relative_volume")):
        parts.append(f"relative volume {today_loaders._format_decimal(technical['relative_volume'])}")
    return "; ".join(parts)


def _fundamental_snippets_from_metrics(
    metrics: dict[str, Any],
    as_of: Any,
) -> list[dict[str, Any]]:
    mapping = (
        ("quality_score", "Quality"),
        ("margin_trend_score", "Margin Trend"),
        ("revenue_growth_score", "Revenue Growth"),
        ("valuation_percentile", "Valuation Percentile"),
    )
    items: list[dict[str, Any]] = []
    for key, title in mapping:
        value = metrics.get(key)
        if not today_loaders._is_number(value):
            continue
        items.append(
            {
                "title": title,
                "summary": today_loaders._format_decimal(value),
                "as_of": as_of,
            }
        )
    return items


def _append_news_snippet(
    grouped: dict[str, list[dict[str, Any]]],
    seen: set[tuple[str, str, str, str | None]],
    *,
    ticker: str,
    title: Any,
    summary: Any,
    published_at: Any,
    event_type: Any = None,
    importance: Any = None,
    source: Any = None,
    sentiment: Any = None,
    source_ticker: Any = None,
    readthrough_source_ticker: Any = None,
    explicit_ticker_mention: Any = None,
) -> None:
    normalized_title = str(title or "").strip()
    if not normalized_title:
        return
    normalized_summary = str(summary or "").strip()
    time_key = published_at.isoformat() if hasattr(published_at, "isoformat") else str(published_at or "") or None
    dedupe_key = (ticker, normalized_title, normalized_summary, time_key)
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    normalized_source_ticker = str(source_ticker or "").strip().upper() or None
    normalized_readthrough_source = str(readthrough_source_ticker or "").strip().upper() or None
    if normalized_readthrough_source is None and normalized_source_ticker and normalized_source_ticker != ticker:
        normalized_readthrough_source = normalized_source_ticker
    grouped.setdefault(ticker, []).append(
        {
            "title": normalized_title,
            "summary": normalized_summary,
            "published_at": published_at,
            "event_type": str(event_type or "").strip() or None,
            "importance": str(importance or "").strip() or None,
            "source": str(source or "").strip() or None,
            "sentiment": str(sentiment or "").strip() or None,
            "source_ticker": normalized_source_ticker,
            "readthrough_source_ticker": normalized_readthrough_source,
            "readthrough_label": f"Readthrough from {normalized_readthrough_source}" if normalized_readthrough_source else None,
            "explicit_ticker_mention": explicit_ticker_mention,
        }
    )
