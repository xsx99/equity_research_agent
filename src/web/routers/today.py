"""Today trading workstation routes."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as SQLAlchemySession

from src.db.connection import get_session
from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    CandidateScore,
    DailyReflection,
    EventNewsItem,
    IntradayRebalanceDecision,
    IntradaySignalSnapshot,
    LearningFactor,
    LlmUsageEvent,
    ManualTickerRequest,
    NewsAlert,
    OptionStrategyDecision,
    PaperOrder,
    PaperOptionOrder,
    PaperOptionPosition,
    PaperPosition,
    PeerBasket,
    PortfolioIntent,
    PortfolioRiskSnapshot,
    PortfolioSnapshot,
    RiskDecision,
    RiskFactorExposure,
    RiskHedgeDecision,
    SignalSnapshot,
    StrategyDefinition,
    StrategyEvaluationResult,
    StrategyProposal,
    ThemeTaxonomy,
    TickerRelationship,
    TradingDecision,
    UniverseFilterConfig,
)
from src.trading.manual_review.sqlalchemy import SQLAlchemyManualTickerRequestService
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.web.flash import flash, get_flash
from src.web.presenters.today_copy import (
    cache_status_label,
    candidate_result_label,
    generic_status_label,
    intent_type_label,
    live_status_label,
    macro_regime_label,
    manual_request_mode_label,
    manual_request_status_label,
    option_strategy_type_label,
    order_status_label,
    risk_appetite_label,
    runtime_mode_label,
    scope_label,
    strategy_label,
    trade_identity_label,
)
from src.web.presenters.today_candidates import build_today_candidates_view
from src.web.presenters.today_learning_strategies import build_today_learning_strategies
from src.web.presenters.today_overview import build_today_overview
from src.web.presenters.today_portfolio_analytics import build_portfolio_analytics
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload
from src.web.presenters.today_workspace import build_ticker_workspace
from src.web.presenters.signal_evidence import signal_groups
import src.web.routers.today_loaders as _today_loaders
from src.web.routers.today_loaders import (
    _TAB_LABELS,
    _attach_candidate_summary,
    _build_header,
    _build_job_timeline,
    _build_portfolio_view,
    _build_system_view,
    _ensure_trade_rows_include_ticker,
    _group_latest_by_ticker,
    _latest_trade_decision_id_for_ticker,
    _load_candidate_rows,
    _load_fundamentals_by_ticker,
    _load_hedge_overlays,
    _load_latest_macro_snapshot_for_today,
    _load_latest_preopen_runtime_run_for_today,
    _load_learning_factors,
    _load_live_alerts,
    _load_llm_usage,
    _load_manual_requests,
    _load_material_changes,
    _load_news_by_ticker,
    _load_option_positions,
    _load_peer_baskets,
    _load_portfolio_history,
    _load_portfolio_intents,
    _load_positions,
    _load_recent_closed_positions,
    _load_relationships,
    _load_risk_exposures,
    _load_risk_by_ticker,
    _load_signal_history_by_ticker,
    _load_strategy_definitions,
    _load_strategy_evaluation_results,
    _load_strategy_performance,
    _load_strategy_proposals,
    _load_themes,
    _load_today_risk_macro,
    _load_trade_detail,
    _load_trade_rows,
    _merge_audit_detail_into_workspace_detail,
    _normalize_detail_item_index,
    _normalize_detail_tab,
    _normalize_tab,
    _select_detail_item,
    _serialize_reflection,
    _serialize_universe_filter,
    _split_csv,
    _to_decimal,
)


def _router_loader_proxy(name: str):
    def _proxy(*args, **kwargs):
        return getattr(sys.modules[__name__], name)(*args, **kwargs)

    return _proxy


for _loader_name in (
    "_attach_candidate_summary",
    "_build_header",
    "_build_job_timeline",
    "_build_portfolio_view",
    "_build_system_view",
    "_ensure_trade_rows_include_ticker",
    "_group_latest_by_ticker",
    "_latest_trade_decision_id_for_ticker",
    "_load_candidate_rows",
    "_load_fundamentals_by_ticker",
    "_load_hedge_overlays",
    "_load_latest_macro_snapshot_for_today",
    "_load_latest_preopen_runtime_run_for_today",
    "_load_learning_factors",
    "_load_live_alerts",
    "_load_llm_usage",
    "_load_manual_requests",
    "_load_material_changes",
    "_load_news_by_ticker",
    "_load_option_positions",
    "_load_peer_baskets",
    "_load_portfolio_history",
    "_load_portfolio_intents",
    "_load_positions",
    "_load_recent_closed_positions",
    "_load_relationships",
    "_load_risk_exposures",
    "_load_risk_by_ticker",
    "_load_signal_history_by_ticker",
    "_load_strategy_definitions",
    "_load_strategy_evaluation_results",
    "_load_strategy_performance",
    "_load_strategy_proposals",
    "_load_themes",
    "_load_today_risk_macro",
    "_load_trade_detail",
    "_load_trade_rows",
    "_merge_audit_detail_into_workspace_detail",
    "_normalize_detail_item_index",
    "_normalize_detail_tab",
    "_normalize_tab",
    "_select_detail_item",
    "_serialize_reflection",
    "_serialize_universe_filter",
    "_split_csv",
    "_to_decimal",
):
    setattr(_today_loaders, _loader_name, _router_loader_proxy(_loader_name))

_today_loaders.SqlAlchemyTradingRepository = _router_loader_proxy("SqlAlchemyTradingRepository")

router = APIRouter()
_templates: Jinja2Templates | None = None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@router.get("/today", response_class=HTMLResponse)
def today_dashboard(
    request: Request,
    tab: str = "overview",
    decision_id: str | None = None,
    ticker: str | None = None,
    detail_tab: str = "timeline",
    detail_item_index: int | None = None,
):
    with get_session() as session:
        dashboard = load_today_dashboard(
            session,
            selected_tab=tab,
            decision_id=decision_id,
            selected_ticker=ticker,
            selected_detail_tab=detail_tab,
            selected_detail_item_index=detail_item_index,
        )
    return _templates.TemplateResponse(
        request,
        "today.html",
        {
            "flash": get_flash(request),
            **dashboard,
        },
    )


@router.post("/today/manual-requests")
def today_add_manual_request(
    request: Request,
    ticker: str = Form(...),
    reason: str = Form(...),
    mode: str = Form(...),
):
    try:
        with get_session() as session:
            create_manual_request(session, ticker=ticker, reason=reason, mode=mode)
    except Exception as exc:
        flash(request, f"Error creating manual request: {exc}", "error")
    return RedirectResponse("/today?tab=candidates", status_code=303)


@router.post("/today/manual-requests/{request_id}/dismiss")
def today_dismiss_manual_request(request_id: str, request: Request):
    try:
        with get_session() as session:
            dismiss_manual_request(session, request_id)
    except Exception as exc:
        flash(request, f"Error dismissing manual request: {exc}", "error")
    return RedirectResponse("/today?tab=candidates", status_code=303)


@router.post("/today/universe-filter")
def today_update_universe_filter(
    request: Request,
    profile_name: str = Form(...),
    min_price: str = Form(...),
    min_avg_dollar_volume: str = Form(...),
    included_sectors: str = Form(""),
    excluded_sectors: str = Form(""),
    included_industries: str = Form(""),
    excluded_industries: str = Form(""),
    exchanges: str = Form(""),
    asset_types: str = Form(""),
    manual_include: str = Form(""),
    manual_exclude: str = Form(""),
):
    try:
        with get_session() as session:
            update_universe_filter(
                session,
                profile_name=profile_name,
                min_price=min_price,
                min_avg_dollar_volume=min_avg_dollar_volume,
                included_sectors=included_sectors,
                excluded_sectors=excluded_sectors,
                included_industries=included_industries,
                excluded_industries=excluded_industries,
                exchanges=exchanges,
                asset_types=asset_types,
                manual_include=manual_include,
                manual_exclude=manual_exclude,
            )
    except Exception as exc:
        flash(request, f"Error updating universe filter: {exc}", "error")
    return RedirectResponse("/today?tab=candidates", status_code=303)


def load_today_dashboard(
    session: Any,
    *,
    selected_tab: str,
    decision_id: str | None,
    selected_ticker: str | None,
    selected_detail_tab: str = "timeline",
    selected_detail_item_index: int | None = None,
) -> dict[str, Any]:
    selected_tab = _normalize_tab(selected_tab)
    latest_portfolio = session.query(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_time.desc()).first()
    latest_risk = session.query(PortfolioRiskSnapshot).order_by(PortfolioRiskSnapshot.decision_time.desc()).first()
    latest_reflection = session.query(DailyReflection).order_by(DailyReflection.trade_date.desc()).first()
    active_universe_filter = (
        session.query(UniverseFilterConfig)
        .filter(UniverseFilterConfig.is_active == True)
        .order_by(UniverseFilterConfig.version.desc(), UniverseFilterConfig.created_at.desc())
        .first()
    )

    trade_rows = _load_trade_rows(session)
    positions = _load_positions(session)
    option_positions = _load_option_positions(session)
    closed_positions = _load_recent_closed_positions(session)
    positions_by_ticker = _group_latest_by_ticker(positions)
    option_positions_by_ticker = _group_latest_by_ticker(option_positions)
    closed_positions_by_ticker = _group_latest_by_ticker(closed_positions)
    risk_by_ticker = _load_risk_by_ticker(session)
    signal_history_by_ticker = _load_signal_history_by_ticker(session)
    news_by_ticker = _load_news_by_ticker(session)
    fundamentals_by_ticker = _load_fundamentals_by_ticker(session)
    candidate_rows = _load_candidate_rows(session)
    manual_requests = _load_manual_requests(session)
    trade_rows = _filter_trade_rows_for_display(trade_rows, manual_requests)
    candidate_surface_rows, trade_surface_candidate_rows = _split_candidate_rows_by_display_owner(
        candidate_rows,
        manual_requests=manual_requests,
        trade_rows=trade_rows,
        traded_tickers=set(positions_by_ticker) | set(option_positions_by_ticker),
    )
    trade_workspace_rows = _trade_workspace_rows(
        trade_rows,
        trade_surface_candidate_rows,
    )
    trade_workspace_rows = _ensure_trade_rows_include_ticker(
        session,
        trade_workspace_rows,
        selected_ticker,
    )
    portfolio_intents = _load_portfolio_intents(session)
    relationships = _load_relationships(session)
    peer_baskets = _load_peer_baskets(session)
    themes = _load_themes(session)
    ticker_workspace = build_ticker_workspace(
        trade_rows=trade_workspace_rows,
        selected_ticker=selected_ticker,
        positions_by_ticker=positions_by_ticker,
        option_positions_by_ticker=option_positions_by_ticker,
        closed_positions_by_ticker=closed_positions_by_ticker,
        risk_by_ticker=risk_by_ticker,
        signal_history_by_ticker=signal_history_by_ticker,
        news_by_ticker=news_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
    )
    trade_workspace_rows = _ensure_trade_rows_include_ticker(
        session,
        trade_workspace_rows,
        ticker_workspace.get("selected_ticker"),
    )
    ticker_workspace = build_ticker_workspace(
        trade_rows=trade_workspace_rows,
        selected_ticker=ticker_workspace.get("selected_ticker"),
        positions_by_ticker=positions_by_ticker,
        option_positions_by_ticker=option_positions_by_ticker,
        closed_positions_by_ticker=closed_positions_by_ticker,
        risk_by_ticker=risk_by_ticker,
        signal_history_by_ticker=signal_history_by_ticker,
        news_by_ticker=news_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
    )

    audit_detail = _load_trade_detail(session, decision_id) if decision_id else None
    if audit_detail is None:
        selected_decision_id = _latest_trade_decision_id_for_ticker(
            trade_workspace_rows,
            ticker_workspace.get("selected_ticker"),
        )
        if selected_decision_id:
            audit_detail = _load_trade_detail(session, selected_decision_id)

    merged_detail = _merge_audit_detail_into_workspace_detail(
        ticker_workspace.get("detail"),
        audit_detail,
    )

    normalized_detail_tab = _normalize_detail_tab(selected_detail_tab)
    normalized_detail_item_index = _normalize_detail_item_index(
        detail=merged_detail,
        detail_tab=normalized_detail_tab,
        detail_item_index=selected_detail_item_index,
    )
    ticker_workspace = {
        **ticker_workspace,
        "detail": merged_detail,
        "audit_detail": audit_detail,
        "selected_detail_tab": normalized_detail_tab,
        "selected_detail_item_index": normalized_detail_item_index,
        "selected_detail_item": _select_detail_item(
            detail=merged_detail,
            detail_tab=normalized_detail_tab,
            detail_item_index=normalized_detail_item_index,
        ),
    }
    latest_macro_snapshot = _load_latest_macro_snapshot_for_today(
        session,
        latest_portfolio=latest_portfolio,
        latest_risk=latest_risk,
        latest_reflection=latest_reflection,
    )
    header = _build_header(
        latest_portfolio,
        latest_risk,
        trade_rows,
        latest_reflection,
        latest_macro_snapshot=latest_macro_snapshot,
        positions=positions,
    )
    risk_macro = _load_today_risk_macro(
        session,
        latest_risk=latest_risk,
        latest_macro_snapshot=latest_macro_snapshot,
    )
    latest_preopen_run = _load_latest_preopen_runtime_run_for_today(
        session,
        latest_portfolio=latest_portfolio,
        latest_risk=latest_risk,
        latest_reflection=latest_reflection,
    )
    job_timeline = _build_job_timeline(latest_reflection)
    overview = build_today_overview(
        header=header,
        job_timeline=job_timeline,
        risk_macro=risk_macro,
        live_alerts=_load_live_alerts(session),
        material_changes=_load_material_changes(session),
        positions=positions,
        option_positions=option_positions,
        closed_positions=closed_positions,
        latest_preopen_run=latest_preopen_run,
    )
    # Map ticker -> [(decision_time, agent thesis)] (newest-first) from the trading
    # decisions so candidates can surface the LLM thesis instead of rule-based reasons.
    thesis_history_by_ticker: dict[str, list[tuple[Any, str]]] = {}
    for row in trade_rows:
        ticker_symbol = str(row.get("ticker") or "").strip().upper()
        thesis_text = row.get("thesis")
        if not ticker_symbol or not thesis_text:
            continue
        thesis_history_by_ticker.setdefault(ticker_symbol, []).append(
            (row.get("decision_time"), thesis_text)
        )
    candidates = build_today_candidates_view(
        rows=candidate_surface_rows,
        manual_requests=manual_requests,
        themes=themes,
        active_universe_filter=_serialize_universe_filter(active_universe_filter),
        portfolio_intents=portfolio_intents,
        relationships=relationships,
        peer_baskets=peer_baskets,
        thesis_history_by_ticker=thesis_history_by_ticker,
        news_by_ticker=news_by_ticker,
    )
    portfolio_history = _load_portfolio_history(session)
    portfolio = _build_portfolio_view(
        header=header,
        positions=positions,
        option_positions=option_positions,
        hedge_overlays=_load_hedge_overlays(session),
        overview=overview,
        portfolio_history=portfolio_history,
    )
    # Surface the account-level total return on the header's Unrealized P&L card
    # (computed in the portfolio analytics from the equity history).
    if isinstance(header, dict) and header.get("total_return") is None:
        _analytics = portfolio.get("analytics") if isinstance(portfolio, dict) else None
        _metrics = _analytics.get("metrics") if isinstance(_analytics, dict) else None
        if isinstance(_metrics, dict):
            header["total_return"] = _metrics.get("total_return")
    # Most / least effective strategy for the Portfolio analytics cards
    # (ranked by cumulative alpha = total_pnl in strategy performance).
    strategy_perf = _load_strategy_performance(session)
    _ranked = [p for p in strategy_perf if p.get("total_pnl") is not None]
    if isinstance(portfolio, dict):
        portfolio["strategy_effectiveness"] = {
            "most": max(_ranked, key=lambda p: p["total_pnl"]) if _ranked else None,
            "least": min(_ranked, key=lambda p: p["total_pnl"]) if len(_ranked) > 1 else None,
        }
    learning_strategies = build_today_learning_strategies(
        reflection=_serialize_reflection(latest_reflection),
        learning_factors=_load_learning_factors(session),
        strategy_performance=strategy_perf,
        strategy_proposals=_load_strategy_proposals(session),
        strategy_definitions=_load_strategy_definitions(session),
        strategy_evaluation_results=_load_strategy_evaluation_results(session),
    )
    ops_cost = {
        "llm_usage": _load_llm_usage(session),
        "provider_usage": (),
    }
    system = _build_system_view(
        overview=overview,
        learning_strategies=learning_strategies,
        ops_cost=ops_cost,
        risk_macro=risk_macro,
    )
    candidates = _attach_candidate_summary(candidates)

    return {
        "selected_tab": selected_tab,
        "tabs": tuple({"id": tab_id, "label": label} for tab_id, label in _TAB_LABELS),
        "header": header,
        "job_timeline": job_timeline,
        "overview": overview,
        "portfolio": portfolio,
        "trades": {
            "rows": trade_workspace_rows,
            "selected_detail": audit_detail,
        },
        "ticker_workspace": ticker_workspace,
        "risk_macro": risk_macro,
        "candidates": candidates,
        "learning_strategies": learning_strategies,
        "ops_cost": ops_cost,
        "system": system,
    }


def _filter_trade_rows_for_display(
    trade_rows: list[dict[str, Any]],
    manual_requests: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    review_only_tickers = {
        ticker
        for ticker, mode in _manual_request_modes_by_ticker(manual_requests).items()
        if mode == "review_only"
    }
    if not review_only_tickers:
        return trade_rows
    return [
        row
        for row in trade_rows
        if _normalize_ticker_value(row.get("ticker")) not in review_only_tickers
    ]


def _split_candidate_rows_by_display_owner(
    rows: tuple[dict[str, Any], ...],
    *,
    manual_requests: tuple[dict[str, Any], ...],
    trade_rows: list[dict[str, Any]],
    traded_tickers: set[str] | None = None,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    manual_modes = _manual_request_modes_by_ticker(manual_requests)
    trade_tickers = {
        ticker
        for row in trade_rows
        if (ticker := _normalize_ticker_value(row.get("ticker")))
    }
    trade_tickers.update(_normalize_ticker_value(ticker) for ticker in (traded_tickers or set()) if ticker)
    candidate_surface: list[dict[str, Any]] = []
    trade_surface: list[dict[str, Any]] = []
    for row in rows:
        if _candidate_belongs_to_trade_surface(row, manual_modes=manual_modes, trade_tickers=trade_tickers):
            trade_surface.append(row)
        else:
            candidate_surface.append(row)
    return tuple(candidate_surface), tuple(trade_surface)


def _candidate_belongs_to_trade_surface(
    row: dict[str, Any],
    *,
    manual_modes: dict[str, str],
    trade_tickers: set[str],
) -> bool:
    ticker = _normalize_ticker_value(row.get("ticker"))
    mode = str(row.get("mode") or manual_modes.get(ticker, "")).strip().lower()
    if mode == "review_only":
        return False
    if ticker in trade_tickers:
        return True

    result_status = str(row.get("result_status") or "").strip().lower()
    if result_status in {"actionable_trade", "no_trade"}:
        return True
    if bool(row.get("action_required")):
        return True

    trade_identity = str(row.get("trade_identity") or "").strip().lower()
    return bool(trade_identity and trade_identity not in {"watch_only", "none"})


def _trade_workspace_rows(
    trade_rows: list[dict[str, Any]],
    trade_surface_candidate_rows: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    existing_tickers = {
        ticker
        for row in trade_rows
        if (ticker := _normalize_ticker_value(row.get("ticker")))
    }
    seed_rows = [
        _candidate_row_to_trade_workspace_seed(row)
        for row in trade_surface_candidate_rows
        if _normalize_ticker_value(row.get("ticker")) not in existing_tickers
    ]
    return [*trade_rows, *seed_rows]


def _candidate_row_to_trade_workspace_seed(row: dict[str, Any]) -> dict[str, Any]:
    result_status = str(row.get("result_status") or "").strip().lower()
    decision = "no_trade" if result_status == "no_trade" else "trade_candidate"
    return {
        "ticker": row.get("ticker"),
        "decision": decision,
        "selected_strategy_id": row.get("strategy_match") or row.get("strategy_id"),
        "confidence": row.get("confidence", row.get("candidate_score")),
        "created_at": row.get("decision_time"),
        "decision_time": row.get("decision_time"),
        "trade_identity": row.get("trade_identity"),
        "material_signal_change": True,
        "core_signal_evidence": row.get("core_signal_evidence") or {},
        "selection_reason": row.get("selection_reason"),
    }


def _manual_request_modes_by_ticker(manual_requests: tuple[dict[str, Any], ...]) -> dict[str, str]:
    modes: dict[str, str] = {}
    for item in manual_requests:
        ticker = _normalize_ticker_value(item.get("ticker"))
        if not ticker:
            continue
        modes[ticker] = str(item.get("mode") or "").strip().lower()
    return modes


def _normalize_ticker_value(value: Any) -> str:
    return str(value or "").strip().upper()


def create_manual_request(session: Any, *, ticker: str, reason: str, mode: str) -> uuid.UUID:
    service = SQLAlchemyManualTickerRequestService(session)
    request = service.create(ticker, reason, mode)
    return uuid.UUID(request.request_id)


def dismiss_manual_request(session: Any, request_id: str) -> None:
    service = SQLAlchemyManualTickerRequestService(session)
    service.dismiss(str(request_id))


def update_universe_filter(session: Any, **raw_form: str) -> uuid.UUID:
    profile_name = raw_form["profile_name"].strip() or "default"
    active_rows = (
        session.query(UniverseFilterConfig)
        .filter(
            UniverseFilterConfig.profile_name == profile_name,
            UniverseFilterConfig.is_active == True,
        )
        .all()
    )
    next_version = max((row.version for row in active_rows), default=0) + 1
    for row in active_rows:
        row.is_active = False
    config = UniverseFilterConfig(
        profile_name=profile_name,
        version=next_version,
        is_active=True,
        min_price=_to_decimal(raw_form["min_price"]),
        min_avg_dollar_volume=_to_decimal(raw_form["min_avg_dollar_volume"]),
        included_sectors_json=_split_csv(raw_form["included_sectors"]),
        excluded_sectors_json=_split_csv(raw_form["excluded_sectors"]),
        included_industries_json=_split_csv(raw_form["included_industries"]),
        excluded_industries_json=_split_csv(raw_form["excluded_industries"]),
        exchanges_json=_split_csv(raw_form["exchanges"]),
        asset_types_json=_split_csv(raw_form["asset_types"]),
        manual_include_json=_split_csv(raw_form["manual_include"], uppercase=True),
        manual_exclude_json=_split_csv(raw_form["manual_exclude"], uppercase=True),
    )
    session.add(config)
    session.flush()
    return config.universe_filter_config_id
