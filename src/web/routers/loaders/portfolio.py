"""Portfolio loader helpers for the today router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db.models.trading import PaperOptionPosition, PaperOrder, PaperPosition, PortfolioIntent, PortfolioSnapshot, RiskHedgeDecision
from src.web.presenters.today_copy import generic_status_label, intent_type_label, option_strategy_type_label, strategy_label, trade_identity_label
from src.web.presenters.today_portfolio_analytics import build_portfolio_analytics
from src.web.routers import today_loaders


def _build_portfolio_view(
    *,
    header: dict[str, Any],
    positions: tuple[dict[str, Any], ...],
    option_positions: tuple[dict[str, Any], ...],
    hedge_overlays: tuple[dict[str, Any], ...],
    overview: dict[str, Any],
    portfolio_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "positions": positions,
        "option_positions": option_positions,
        "hedge_overlays": hedge_overlays,
        "position_summary": {
            "count": len(positions),
            "market_value": today_loaders._safe_sum(positions, "market_value"),
            "unrealized_pnl": today_loaders._safe_sum(positions, "unrealized_pnl"),
        },
        "option_position_summary": {
            "count": len(option_positions),
            "market_value": today_loaders._safe_sum(option_positions, "market_value"),
            "max_loss": today_loaders._safe_sum(option_positions, "max_loss"),
        },
        "hedge_overlay_summary": {
            "count": len(hedge_overlays),
            "protected_notional": today_loaders._safe_sum(hedge_overlays, "protected_notional"),
        },
        "kpis": {
            "account_equity": header.get("account_equity"),
            "day_pnl": header.get("day_pnl"),
            "realized_pnl": header.get("realized_pnl"),
            "unrealized_pnl": header.get("unrealized_pnl"),
            "gross_exposure": header.get("gross_exposure"),
            "net_exposure": header.get("net_exposure"),
            "cash_balance": header.get("cash_balance"),
            "buying_power": header.get("buying_power"),
        },
        "analytics": build_portfolio_analytics(portfolio_history or []),
        "needs_attention": {
            "needs_review": tuple(overview.get("command_center", {}).get("needs_review") or ()),
            "live_alerts": tuple(overview.get("live_alerts") or ()),
            "material_changes": tuple(overview.get("material_changes") or ()),
        },
    }


def _load_positions(session: Any, *, as_of: datetime | None = None) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(PaperPosition)
        .filter(PaperPosition.status == "open")
        .order_by(PaperPosition.updated_at.desc())
        .all()
    )
    reference_time = as_of or datetime.now(timezone.utc)
    strategy_fallbacks = _load_position_strategy_fallbacks(session, tickers=tuple(row.ticker for row in rows))
    positions = []
    for row in rows:
        avg_cost = getattr(row, "average_cost", getattr(row, "avg_cost", None))
        unrealized_pnl = _position_unrealized_pnl(
            explicit_value=getattr(row, "unrealized_pnl", None),
            market_value=getattr(row, "market_value", None),
            avg_cost=avg_cost,
            quantity=getattr(row, "quantity", None),
        )
        strategy_id = getattr(row, "strategy_id", None) or strategy_fallbacks.get(str(row.ticker).upper())
        positions.append({
            "ticker": row.ticker,
            "trade_identity": row.trade_identity,
            "trade_identity_label": trade_identity_label(row.trade_identity),
            "strategy_id": strategy_id,
            "strategy_label": strategy_label(strategy_id),
            "quantity": row.quantity,
            "avg_cost": avg_cost,
            "entry_price": avg_cost,
            "avg_fill_price": avg_cost,
            "filled_qty": row.quantity,
            "current_price": getattr(row, "market_price", None),
            "held_days": _held_days(getattr(row, "opened_at", None), reference_time),
            "opened_at": getattr(row, "opened_at", None),
            "updated_at": getattr(row, "updated_at", None),
            "sleeve": trade_identity_label(row.trade_identity),
            "market_value": row.market_value,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl_pct": _total_pnl_pct(
                unrealized_pnl=unrealized_pnl,
                avg_cost=avg_cost,
                quantity=row.quantity,
            ),
        })
    return tuple(positions)


def _load_position_strategy_fallbacks(session: Any, *, tickers: tuple[str, ...]) -> dict[str, str]:
    normalized_tickers = tuple(sorted({str(ticker).upper() for ticker in tickers if ticker}))
    if not normalized_tickers:
        return {}
    rows = (
        session.query(PaperOrder)
        .filter(PaperOrder.ticker.in_(normalized_tickers))
        .filter(PaperOrder.action.in_(("enter_long", "enter_short")))
        .order_by(PaperOrder.created_at.desc())
        .all()
    )
    usable_rows = sorted(
        (
            row
            for row in rows
            if str(getattr(row, "ticker", "")).upper() in normalized_tickers
            and getattr(row, "strategy_id", None)
            and getattr(row, "action", None) in {"enter_long", "enter_short"}
            and str(getattr(row, "status", "")).lower() not in {"canceled", "cancelled", "expired", "rejected"}
        ),
        key=lambda row: getattr(row, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    fallbacks: dict[str, str] = {}
    for row in usable_rows:
        ticker = str(row.ticker).upper()
        if ticker not in fallbacks:
            fallbacks[ticker] = row.strategy_id
    return fallbacks


def _held_days(opened_at: Any, as_of: datetime) -> int | None:
    if not isinstance(opened_at, datetime):
        return None
    opened = opened_at
    reference = as_of
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max((reference - opened).days, 0)


def _total_pnl_pct(*, unrealized_pnl: Any, avg_cost: Any, quantity: Any) -> float | None:
    pnl = _safe_float(unrealized_pnl)
    entry = _safe_float(avg_cost)
    qty = _safe_float(quantity)
    if pnl is None or entry is None or qty is None:
        return None
    denominator = abs(entry * qty)
    if denominator <= 0:
        return None
    return pnl / denominator


def _position_unrealized_pnl(
    *,
    explicit_value: Any,
    market_value: Any,
    avg_cost: Any,
    quantity: Any,
) -> float | None:
    explicit = _safe_float(explicit_value)
    if explicit is not None:
        return explicit
    market = _safe_float(market_value)
    entry = _safe_float(avg_cost)
    qty = _safe_float(quantity)
    if market is None or entry is None or qty is None:
        return None
    return market - (entry * qty)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_recent_closed_positions(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(PaperPosition)
        .filter(PaperPosition.status == "closed")
        .order_by(PaperPosition.closed_at.desc(), PaperPosition.updated_at.desc())
        .limit(25)
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "trade_identity": row.trade_identity,
            "trade_identity_label": trade_identity_label(row.trade_identity),
            "strategy_id": row.strategy_id,
            "strategy_label": strategy_label(row.strategy_id),
            "quantity": row.quantity,
            "market_value": row.market_value,
            "opened_at": row.opened_at,
            "updated_at": row.updated_at,
            "closed_at": row.closed_at,
            "status": row.status,
        }
        for row in rows
    )


def _load_option_positions(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(PaperOptionPosition)
        .filter(PaperOptionPosition.status == "open")
        .order_by(PaperOptionPosition.updated_at.desc())
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "option_strategy_type": row.option_strategy_type,
            "option_strategy_type_label": option_strategy_type_label(row.option_strategy_type),
            "trade_identity": row.trade_identity,
            "trade_identity_label": trade_identity_label(row.trade_identity),
            "quantity": getattr(row, "quantity", None),
            "expiry_label": row.expiry.strftime("%Y-%m-%d") if getattr(row, "expiry", None) else None,
            "buying_power_effect": getattr(row, "buying_power_effect", None),
            "max_loss": row.max_loss,
        }
        for row in rows
    )


def _load_hedge_overlays(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(RiskHedgeDecision)
        .order_by(RiskHedgeDecision.created_at.desc())
        .limit(10)
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "option_strategy_type": row.option_strategy_type,
            "option_strategy_type_label": option_strategy_type_label(row.option_strategy_type),
            "action_label": row.action.replace("_", " ").title() if getattr(row, "action", None) else None,
            "hedge_cost": getattr(row, "hedge_cost", None),
            "protected_notional": row.protected_notional,
            "created_at": getattr(row, "created_at", None),
        }
        for row in rows
    )


def _load_portfolio_history(session: Any, *, limit: int = 180) -> list[dict[str, Any]]:
    rows = (
        session.query(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.snapshot_time.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "time": row.snapshot_time,
            "equity": row.account_equity,
            "day_pnl": row.day_pnl,
        }
        for row in reversed(rows)
    ]


def _load_portfolio_intents(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(PortfolioIntent).order_by(PortfolioIntent.created_at.desc()).limit(20).all()
    return tuple(
        {
            "ticker": row.ticker,
            "intent_type": row.intent_type,
            "lifecycle_status": row.lifecycle_status,
            "intent_type_label": intent_type_label(row.intent_type),
            "lifecycle_status_label": generic_status_label(row.lifecycle_status),
        }
        for row in rows
    )
