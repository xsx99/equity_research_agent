"""Header and system loader helpers for the today router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as SQLAlchemySession

from src.db.models.trading import DailyReflection, LlmUsageEvent, PortfolioRiskSnapshot, PortfolioSnapshot, UniverseFilterConfig
from src.web.presenters.today_copy import (
    generic_status_label,
    live_status_label,
    macro_regime_label,
    risk_appetite_label,
    runtime_mode_label,
)
from src.web.routers import today_loaders

_TAB_LABELS = (
    ("overview", "Overview"),
    ("trades", "Trades"),
    ("portfolio", "Portfolio"),
    ("risk-macro", "Risk & Macro"),
    ("candidates", "Candidates"),
    ("system", "System"),
)


def _build_header(
    latest_portfolio: PortfolioSnapshot | None,
    latest_risk: PortfolioRiskSnapshot | None,
    trade_rows: list[dict[str, Any]],
    latest_reflection: DailyReflection | None,
    latest_macro_snapshot: object | None = None,
) -> dict[str, Any]:
    trade_date = None
    if latest_portfolio:
        trade_date = latest_portfolio.snapshot_time.date()
    elif latest_risk:
        trade_date = latest_risk.decision_time.date()
    elif latest_reflection:
        trade_date = latest_reflection.trade_date

    return {
        "trade_date": trade_date,
        "macro_regime": getattr(latest_macro_snapshot, "regime", None) or "unavailable",
        "macro_regime_label": macro_regime_label(getattr(latest_macro_snapshot, "regime", None) or "unavailable"),
        "risk_appetite": latest_risk.risk_appetite if latest_risk else "unavailable",
        "risk_appetite_label": risk_appetite_label(latest_risk.risk_appetite if latest_risk else "unavailable"),
        "market_phase": "Pre-open" if trade_date else "Unavailable",
        "runtime_mode": "live" if latest_risk else "dry_run",
        "runtime_mode_label": runtime_mode_label("live" if latest_risk else "dry_run"),
        "live_status": "degraded" if getattr(latest_macro_snapshot, "regime", None) is None else "live",
        "live_status_label": live_status_label(
            "degraded" if getattr(latest_macro_snapshot, "regime", None) is None else "live"
        ),
        "nav": latest_portfolio.net_liquidation_value if latest_portfolio else None,
        "account_equity": latest_portfolio.account_equity if latest_portfolio else None,
        "cash_balance": latest_portfolio.cash_balance if latest_portfolio else None,
        "day_pnl": latest_portfolio.day_pnl if latest_portfolio else None,
        "day_pnl_pct": today_loaders._safe_pct(
            latest_portfolio.day_pnl if latest_portfolio else None,
            today_loaders._safe_diff(
                latest_portfolio.account_equity if latest_portfolio else None,
                latest_portfolio.day_pnl if latest_portfolio else None,
            ),
        ),
        "realized_pnl": latest_portfolio.realized_pnl if latest_portfolio else None,
        "unrealized_pnl": latest_portfolio.unrealized_pnl if latest_portfolio else None,
        "buying_power": latest_portfolio.buying_power if latest_portfolio else None,
        "stock_market_value": latest_portfolio.stock_market_value if latest_portfolio else None,
        "option_market_value": latest_portfolio.option_market_value if latest_portfolio else None,
        "gross_exposure": today_loaders._exposure_ratio(
            getattr(latest_risk, "gross_exposure", None),
            getattr(latest_risk, "account_equity", None),
        ),
        "net_exposure": today_loaders._exposure_ratio(
            getattr(latest_risk, "net_exposure", None),
            getattr(latest_risk, "account_equity", None),
        ),
        "margin_util_pct": today_loaders._safe_pct(
            latest_portfolio.total_margin_requirement if latest_portfolio else None,
            latest_portfolio.account_equity if latest_portfolio else None,
        ),
        "open_alert_count": len([row for row in trade_rows if row.get("order_status") in {"rejected", "pending_new"}]),
        "material_signal_change_count": 0,
        "llm_cost_estimate": None,
    }


def _build_job_timeline(latest_reflection: DailyReflection | None) -> tuple[dict[str, Any], ...]:
    rows = [{"label": "Workstation", "status": "available", "status_label": generic_status_label("available")}]
    if latest_reflection:
        rows.append(
            {
                "label": "Reflection",
                "status": latest_reflection.status,
                "status_label": generic_status_label(latest_reflection.status),
            }
        )
    return tuple(rows)


def _build_system_view(
    *,
    overview: dict[str, Any],
    learning_strategies: dict[str, Any],
    ops_cost: dict[str, Any],
    risk_macro: dict[str, Any],
) -> dict[str, Any]:
    exposures = tuple(risk_macro.get("exposures") or ())
    llm_usage = tuple(ops_cost.get("llm_usage") or ())
    provider_usage = tuple(ops_cost.get("provider_usage") or ())
    events = tuple(risk_macro.get("events") or ())
    return {
        "system_issues": tuple(overview.get("command_center", {}).get("system_issues") or ()),
        "learning_strategies": learning_strategies,
        "ops_cost": ops_cost,
        "risk_macro": risk_macro,
        "exposure_summary": {
            "count": len(exposures),
            "total_exposure": today_loaders._safe_sum(exposures, "exposure"),
        },
        "event_summary": {
            "count": len(events),
        },
        "llm_usage_summary": {
            "count": len(llm_usage),
            "estimated_cost": today_loaders._safe_sum(llm_usage, "estimated_cost"),
        },
        "provider_usage_summary": {
            "count": len(provider_usage),
        },
    }


def _build_overview_command_center(
    *,
    header: dict[str, Any],
    positions: tuple[dict[str, Any], ...],
    closed_positions: tuple[dict[str, Any], ...],
    ticker_workspace: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], ...]]:
    needs_review = tuple(
        {
            "ticker": str(row.get("ticker") or "").strip().upper(),
            "summary": row.get("summary") or "Closed recently and ready for review",
        }
        for row in closed_positions
        if str(row.get("ticker") or "").strip()
    )

    open_positions = tuple(
        {
            "ticker": str(row.get("ticker") or "").strip().upper(),
            "summary": row.get("summary") or "Open position, risk within limits",
        }
        for row in positions
        if str(row.get("ticker") or "").strip()
    )

    system_issues: list[dict[str, Any]] = []
    if str(header.get("macro_regime") or "").strip().lower() == "unavailable":
        system_issues.append(
            {
                "label": "Macro regime unavailable",
                "summary": "Global macro regime data is unavailable.",
            }
        )

    if not system_issues and not needs_review and not open_positions:
        system_issues.append(
            {
                "label": "No active issues",
                "summary": "No command-center issues are currently active.",
            }
        )

    return {
        "needs_review": needs_review,
        "open_positions": open_positions,
        "system_issues": tuple(system_issues),
    }


def _load_latest_macro_snapshot_for_today(
    session: Any,
    *,
    latest_portfolio: PortfolioSnapshot | None,
    latest_risk: PortfolioRiskSnapshot | None,
    latest_reflection: DailyReflection | None,
) -> object | None:
    if not isinstance(session, SQLAlchemySession):
        return None
    trade_date = (
        latest_risk.decision_time.date()
        if latest_risk is not None
        else latest_portfolio.snapshot_time.date()
        if latest_portfolio is not None
        else latest_reflection.trade_date
        if latest_reflection is not None
        else None
    )
    if trade_date is None:
        return None
    decision_time = (
        latest_risk.decision_time
        if latest_risk is not None
        else latest_portfolio.snapshot_time
        if latest_portfolio is not None
        else None
    )
    return today_loaders.SqlAlchemyTradingRepository(session).load_latest_macro_snapshot(
        trade_date=trade_date,
        decision_time=decision_time,
    )


def _load_latest_preopen_runtime_run_for_today(
    session: Any,
    *,
    latest_portfolio: PortfolioSnapshot | None,
    latest_risk: PortfolioRiskSnapshot | None,
    latest_reflection: DailyReflection | None,
) -> dict[str, Any] | None:
    if not isinstance(session, SQLAlchemySession):
        return None
    trade_date = (
        latest_risk.decision_time.date()
        if latest_risk is not None
        else latest_portfolio.snapshot_time.date()
        if latest_portfolio is not None
        else latest_reflection.trade_date
        if latest_reflection is not None
        else datetime.now(timezone.utc).date()
    )
    return today_loaders.SqlAlchemyTradingRepository(session).load_latest_runtime_run(
        phase="preopen",
        trade_date=trade_date,
    )


def _load_llm_usage(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(LlmUsageEvent).order_by(LlmUsageEvent.created_at.desc()).limit(25).all()
    return tuple(
        {
            "pipeline_name": getattr(row.prompt_run, "pipeline_name", None),
            "provider": row.provider,
            "model": row.model,
            "estimated_cost": row.estimated_cost,
        }
        for row in rows
    )


def _serialize_universe_filter(config: UniverseFilterConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "universe_filter_config_id": str(config.universe_filter_config_id),
        "min_price": config.min_price,
        "min_avg_dollar_volume": config.min_avg_dollar_volume,
        "included_sectors": tuple(config.included_sectors_json or []),
        "excluded_sectors": tuple(config.excluded_sectors_json or []),
        "included_industries": tuple(config.included_industries_json or []),
        "excluded_industries": tuple(config.excluded_industries_json or []),
        "exchanges": tuple(config.exchanges_json or []),
        "asset_types": tuple(config.asset_types_json or []),
        "manual_include": tuple(config.manual_include_json or []),
        "manual_exclude": tuple(config.manual_exclude_json or []),
    }


def _normalize_tab(tab: str) -> str:
    allowed = {tab_id for tab_id, _ in _TAB_LABELS}
    return tab if tab in allowed else "overview"


def _normalize_detail_tab(detail_tab: str) -> str:
    allowed = {"timeline"}
    return detail_tab if detail_tab in allowed else "timeline"


def _normalize_detail_item_index(
    *,
    detail: dict[str, Any] | None,
    detail_tab: str,
    detail_item_index: int | None,
) -> int | None:
    items = _detail_tab_items(detail=detail, detail_tab=detail_tab)
    if not items:
        return None
    if detail_item_index is None:
        return 0
    if 0 <= detail_item_index < len(items):
        return detail_item_index
    return 0


def _select_detail_item(
    *,
    detail: dict[str, Any] | None,
    detail_tab: str,
    detail_item_index: int | None,
) -> dict[str, Any] | None:
    items = _detail_tab_items(detail=detail, detail_tab=detail_tab)
    if not items or detail_item_index is None:
        return None
    return items[detail_item_index]


def _detail_tab_items(
    *,
    detail: dict[str, Any] | None,
    detail_tab: str,
) -> list[dict[str, Any]]:
    if not detail:
        return []
    tabs = detail.get("tabs") or {}
    value = tabs.get(detail_tab)
    if isinstance(value, tuple):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []
