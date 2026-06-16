"""Payload and request assembly helpers for the live intraday runtime."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from src.trading.intraday.news_alerts import AlertSourceItem
from src.trading.intraday.rebalance import IntradayRebalanceRequest
from src.trading.signals.event_news import build_event_news_signals
from src.trading.signals.insider import build_insider_signals
from src.trading.signals.social_macro import build_social_macro_signals
from src.trading.signals.sources import SourceRecord


def _build_intraday_refresh_payload(
    *,
    baseline: Any,
    decision_time: datetime,
    technical_rows: tuple[SourceRecord, ...],
    event_news_rows: tuple[SourceRecord, ...] = (),
    social_macro_rows: tuple[SourceRecord, ...] = (),
    insider_rows: tuple[SourceRecord, ...] = (),
    option_chain_rows: tuple[SourceRecord, ...] = (),
    instrument_type: str = "stock",
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    bars = list((technical_rows[-1].payload or {}).get("bars") or []) if technical_rows else []
    last_bar = bars[-1] if bars else {}
    refreshed = {
        "technical": {
            "last_price": float(
                last_bar.get("close") or baseline.signal_json.get("technical", {}).get("last_price") or 0.0
            ),
            "atr_pct": float(baseline.signal_json.get("technical", {}).get("atr_pct") or 0.0),
            "dollar_volume": float(baseline.signal_json.get("technical", {}).get("dollar_volume") or 0.0),
        }
    }
    freshness = {"technical": "fresh" if technical_rows else "missing"}
    if event_news_rows:
        refreshed["events_news"] = build_event_news_signals(
            event_news_rows,
            decision_time=decision_time,
        ).values
        freshness["events_news"] = "fresh"
    if social_macro_rows:
        refreshed["social_macro"] = build_social_macro_signals(
            social_macro_rows,
            decision_time=decision_time,
        ).values
        freshness["social_macro"] = "fresh"
    if _has_newer_insider_rows(baseline=baseline, insider_rows=insider_rows):
        refreshed["insider"] = build_insider_signals(
            insider_rows,
            decision_time=decision_time,
        ).values
        freshness["insider"] = "fresh"
    elif dict(getattr(baseline, "signal_json", {}) or {}).get("insider"):
        freshness["insider"] = "carried_forward_from_baseline"
    option_contract = _option_contract_snapshot(option_chain_rows)
    if instrument_type == "option" or option_contract is not None:
        if option_contract is None:
            freshness["option_chain"] = "missing"
        else:
            refreshed["option"] = {
                "mark_price": _option_mark_price(option_contract),
                "delta": float(option_contract.get("delta") or 0.0),
                "gamma": float(option_contract.get("gamma") or 0.0),
                "theta": float(option_contract.get("theta") or 0.0),
                "vega": float(option_contract.get("vega") or 0.0),
                "strike": float(option_contract.get("strike") or 0.0),
                "option_type": str(option_contract.get("option_type") or ""),
                "expiry": str(option_contract.get("expiry") or ""),
            }
            freshness["option_chain"] = "fresh"
    return refreshed, freshness


def _load_event_items(
    *,
    ticker: str,
    event_news_rows: tuple[SourceRecord, ...],
) -> tuple[AlertSourceItem, ...]:
    items: list[AlertSourceItem] = []
    for row in event_news_rows:
        items.append(_event_item_from_source_record(ticker=ticker, record=row))
    return tuple(items)


def _load_social_macro_items(
    *,
    ticker: str,
    social_macro_rows: tuple[SourceRecord, ...],
) -> tuple[AlertSourceItem, ...]:
    items: list[AlertSourceItem] = []
    for row in social_macro_rows:
        if _social_macro_alertworthy(row):
            items.append(_social_macro_item_from_source_record(ticker=ticker, record=row))
    return tuple(items)


def _event_item_from_source_record(*, ticker: str, record: SourceRecord) -> AlertSourceItem:
    payload = dict(record.payload or {})
    return AlertSourceItem(
        alert_item_id=str(payload.get("event_news_item_id") or record.source_record_id),
        ticker=str(payload.get("ticker") or ticker),
        source_ticker=payload.get("source_ticker"),
        source_family="events_news",
        alert_type=str(payload.get("event_type") or "news"),
        direction=payload.get("direction"),
        sentiment=payload.get("sentiment"),
        importance=payload.get("importance"),
        importance_score=None,
        headline=payload.get("headline"),
        summary=payload.get("summary"),
        provider=str(payload.get("provider") or record.source),
        dedupe_key=str(payload.get("dedupe_key") or record.source_record_id),
        published_at=record.published_at,
        available_for_decision_at=record.available_for_decision_at,
        metadata_json=dict(payload.get("metadata_json") or {}),
    )


def _social_macro_item_from_source_record(*, ticker: str, record: SourceRecord) -> AlertSourceItem:
    payload = dict(record.payload or {})
    return AlertSourceItem(
        alert_item_id=str(record.source_record_id),
        ticker=ticker,
        source_ticker=ticker if bool(payload.get("explicit_ticker_mention_flag")) else None,
        source_family="social_macro",
        alert_type=str(payload.get("category") or "social_macro"),
        direction=payload.get("direction"),
        sentiment=payload.get("sentiment_direction"),
        importance=str(payload.get("importance_label") or ""),
        importance_score=_float_or_none(payload.get("importance_score")),
        headline=payload.get("title"),
        summary=payload.get("summary"),
        provider=str(record.source),
        dedupe_key=str(payload.get("dedupe_key") or record.source_record_id),
        published_at=record.published_at,
        available_for_decision_at=record.available_for_decision_at,
        metadata_json={
            **dict(payload.get("metadata_json") or {}),
            "theme_tags": list(payload.get("theme_tags") or []),
            "explicit_ticker_mention_flag": bool(payload.get("explicit_ticker_mention_flag")),
            "explicit_theme_mention_flag": bool(payload.get("explicit_theme_mention_flag")),
        },
    )


def _build_alert_map(alerts: tuple[object, ...]) -> dict[str, list[dict[str, Any]]]:
    alert_map: dict[str, list[dict[str, Any]]] = {}
    for alert in alerts:
        alert_map.setdefault(alert.ticker, []).append(
            {
                "alert_type": alert.alert_type if hasattr(alert, "alert_type") else None,
                "severity": getattr(alert, "severity", None),
                "sentiment": getattr(alert, "sentiment", None),
                "headline": getattr(alert, "headline", None),
                "summary": getattr(alert, "summary", None),
                "source_ticker": getattr(alert, "source_ticker", None),
                "readthrough_source_ticker": getattr(alert, "readthrough_source_ticker", None),
                "affected_themes": list(getattr(alert, "affected_themes", ())),
                "source_family": dict(getattr(alert, "metadata_json", {}) or {}).get("source_family", "events_news"),
            }
        )
    return alert_map


def _build_rebalance_request(
    *,
    ticker: str,
    baseline: Any,
    snapshot: Any,
    context: Any,
    position: Any | None,
    alerts: tuple[dict[str, Any], ...],
) -> IntradayRebalanceRequest:
    context = context or SimpleNamespace(
        selection_source=baseline.selection_source,
        strategy_id="intraday_refresh_unknown",
        strategy_version="v1",
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        instrument_type="stock",
        candidate_score=0.0,
        target_weight=0.0,
        allow_open_new=False,
        manual_request_id=None,
        manual_request_mode=None,
    )
    position_trade_identity = str(getattr(position, "trade_identity", "") or "")
    instrument_type = str(getattr(context, "instrument_type", "stock"))
    trade_identity = str(getattr(context, "trade_identity", "tactical_stock_trade"))
    if position_trade_identity in {"tactical_option_trade", "risk_hedge_overlay"}:
        instrument_type = "option"
        trade_identity = position_trade_identity
    technical = dict(snapshot.refreshed_signals_json.get("technical", {}))
    option_signals = dict(snapshot.refreshed_signals_json.get("option", {}))
    event_signals = list(alerts)
    current_price = float(technical.get("last_price") or 0.0)
    if instrument_type == "option":
        option_mark_price = float(option_signals.get("mark_price") or 0.0)
        if option_mark_price > 0:
            current_price = option_mark_price
    negative_event_alerts = [
        alert
        for alert in alerts
        if alert.get("sentiment") == "negative" and alert.get("source_family") == "events_news"
    ]
    social_policy_alerts = [
        alert
        for alert in alerts
        if alert.get("source_family") == "social_macro"
    ]
    return IntradayRebalanceRequest(
        ticker=ticker,
        baseline_signal_snapshot_id=baseline.signal_snapshot_id,
        intraday_signal_snapshot_id=snapshot.intraday_signal_snapshot_id,
        previous_intraday_snapshot_id=snapshot.previous_intraday_snapshot_id,
        selection_source=str(getattr(context, "selection_source", baseline.selection_source)),
        strategy_id=str(getattr(context, "strategy_id", "intraday_refresh_unknown")),
        strategy_version=str(getattr(context, "strategy_version", "v1")),
        expression_bucket_id=str(getattr(context, "expression_bucket_id", "long_stock")),
        expression_bucket_version=str(getattr(context, "expression_bucket_version", "v1")),
        trade_identity=trade_identity,
        instrument_type=instrument_type,
        decision_time=snapshot.decision_time,
        available_for_decision_at=snapshot.decision_time,
        current_price=current_price,
        atr_pct=float(technical.get("atr_pct") or 0.0),
        average_daily_dollar_volume=float(technical.get("dollar_volume") or 0.0),
        existing_position=position is not None,
        current_position_quantity=float(getattr(position, "quantity", 0.0) or 0.0),
        current_position_market_value=float(getattr(position, "market_value", 0.0) or 0.0),
        candidate_score=float(getattr(context, "candidate_score", 0.0) or 0.0),
        target_weight=float(getattr(context, "target_weight", 0.0) or 0.0),
        signal_freshness=dict(snapshot.source_freshness_json),
        delta_vs_baseline_json=dict(snapshot.delta_vs_baseline_json),
        delta_vs_previous_json=dict(snapshot.delta_vs_previous_json),
        alerts=event_signals,
        allow_open_new=bool(getattr(context, "allow_open_new", False)),
        direct_company_negative_evidence=bool(negative_event_alerts),
        bearish_signal_sources=("events_news",) if negative_event_alerts else (),
        manual_request_id=getattr(context, "manual_request_id", None),
        manual_request_mode=getattr(context, "manual_request_mode", None),
        metadata_json={
            **dict(getattr(context, "metadata_json", {}) or {}),
            "sector": _sector_from_baseline(baseline),
            "social_policy_alert_count": len(social_policy_alerts),
            "social_policy_risk_context": [
                {
                    "alert_type": alert.get("alert_type"),
                    "severity": alert.get("severity"),
                    "sentiment": alert.get("sentiment"),
                }
                for alert in social_policy_alerts
            ],
            **(
                {
                    "option_mark_price": float(option_signals.get("mark_price") or 0.0),
                    "option_delta": float(option_signals.get("delta") or 0.0),
                    "option_gamma": float(option_signals.get("gamma") or 0.0),
                    "option_theta": float(option_signals.get("theta") or 0.0),
                    "option_vega": float(option_signals.get("vega") or 0.0),
                }
                if instrument_type == "option"
                else {}
            ),
        },
    )


def _position_by_ticker(positions: tuple[object, ...]) -> dict[str, object]:
    return {getattr(position, "ticker"): position for position in positions}


def _sector_from_baseline(baseline: object | None) -> str | None:
    if baseline is None:
        return None
    signal_json = dict(getattr(baseline, "signal_json", {}) or {})
    for key in ("fundamental", "company"):
        payload = dict(signal_json.get(key, {}) or {})
        sector = payload.get("sector")
        if isinstance(sector, str) and sector.strip():
            return sector.strip()
    return None


def _option_contract_snapshot(option_chain_rows: tuple[SourceRecord, ...]) -> dict[str, Any] | None:
    if not option_chain_rows:
        return None
    contracts = list((option_chain_rows[-1].payload or {}).get("contracts") or [])
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if _option_mark_price(contract) > 0:
            return dict(contract)
    return None


def _option_mark_price(contract: dict[str, Any]) -> float:
    for key in ("chosen_price", "mid", "ask", "bid"):
        value = contract.get(key)
        if isinstance(value, (int, float)) and float(value) > 0:
            return float(value) * 100.0
    return 0.0


def _has_newer_insider_rows(*, baseline: object, insider_rows: tuple[SourceRecord, ...]) -> bool:
    if not insider_rows:
        return False
    baseline_signal = dict(getattr(baseline, "signal_json", {}) or {}).get("insider", {})
    if not baseline_signal:
        return True
    baseline_available_at = _parse_iso_datetime(
        dict(getattr(baseline, "source_available_times_json", {}) or {}).get("insider")
    )
    if baseline_available_at is None:
        return True
    latest_available_at = max(row.available_for_decision_at for row in insider_rows)
    return latest_available_at > baseline_available_at


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _social_macro_alertworthy(record: SourceRecord) -> bool:
    payload = dict(record.payload or {})
    importance = str(payload.get("importance_label") or "").lower()
    importance_score = _float_or_none(payload.get("importance_score"))
    return importance in {"high", "critical"} or (importance_score is not None and importance_score >= 0.85)


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
