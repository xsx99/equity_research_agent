"""Payload and request assembly helpers for the live intraday runtime."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from src.trading.intraday.rebalance import IntradayRebalanceRequest
from src.trading.signals.sources import EventNewsItemRecord, SourceRecord


def _build_intraday_refresh_payload(
    *,
    baseline: Any,
    technical_rows: tuple[SourceRecord, ...],
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
    source_repository: Any,
    tickers: tuple[str, ...],
    decision_time: datetime,
) -> tuple[EventNewsItemRecord, ...]:
    items: list[EventNewsItemRecord] = []
    for ticker in tickers:
        rows = source_repository.latest_available_by_family(ticker, "events_news", decision_time)
        for row in rows:
            items.append(_event_item_from_source_record(ticker=ticker, record=row))
    return tuple(items)


def _event_item_from_source_record(*, ticker: str, record: SourceRecord) -> EventNewsItemRecord:
    payload = dict(record.payload or {})
    return EventNewsItemRecord(
        event_news_item_id=str(payload.get("event_news_item_id") or record.source_record_id),
        ticker=str(payload.get("ticker") or ticker),
        source_ticker=payload.get("source_ticker"),
        event_type=str(payload.get("event_type") or "news"),
        direction=payload.get("direction"),
        sentiment=payload.get("sentiment"),
        importance=payload.get("importance"),
        headline=payload.get("headline"),
        summary=payload.get("summary"),
        provider=str(payload.get("provider") or record.source),
        source_refs_json=list(payload.get("source_refs_json") or []),
        dedupe_key=str(payload.get("dedupe_key") or record.source_record_id),
        event_time=record.event_time,
        published_at=record.published_at,
        ingested_at=record.ingested_at,
        available_for_decision_at=record.available_for_decision_at,
        raw_payload_ref=None,
        metadata_json=dict(payload.get("metadata_json") or {}),
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
        direct_company_negative_evidence=any(alert.get("sentiment") == "negative" for alert in alerts),
        bearish_signal_sources=tuple(
            "events_news"
            for alert in alerts
            if alert.get("sentiment") == "negative"
        ),
        manual_request_id=getattr(context, "manual_request_id", None),
        manual_request_mode=getattr(context, "manual_request_mode", None),
        metadata_json={
            **dict(getattr(context, "metadata_json", {}) or {}),
            "sector": _sector_from_baseline(baseline),
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
