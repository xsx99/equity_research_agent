"""Today trading workstation routes."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
    StrategyProposal,
    ThemeTaxonomy,
    TickerRelationship,
    TradingDecision,
    UniverseFilterConfig,
)
from src.web.flash import flash, get_flash
from src.web.presenters.today_copy import (
    candidate_result_label,
    strategy_label,
    trade_identity_label,
)
from src.web.presenters.today_workspace import build_ticker_workspace

router = APIRouter()
_templates: Jinja2Templates | None = None

_TAB_LABELS = (
    ("overview", "Overview"),
    ("portfolio", "Portfolio"),
    ("trades", "Trades"),
    ("risk-macro", "Risk & Macro"),
    ("candidates", "Candidates"),
    ("learning-strategies", "Learning & Strategies"),
    ("ops-cost", "Ops & Cost"),
)


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
    closed_positions = _load_recent_closed_positions(session)
    positions_by_ticker = _group_latest_by_ticker(positions)
    closed_positions_by_ticker = _group_latest_by_ticker(closed_positions)
    risk_by_ticker = _load_risk_by_ticker(session)
    signal_history_by_ticker = _load_signal_history_by_ticker(session)
    news_by_ticker = _load_news_by_ticker(session)
    fundamentals_by_ticker = _load_fundamentals_by_ticker(session)
    ticker_workspace = build_ticker_workspace(
        trade_rows=trade_rows,
        selected_ticker=selected_ticker,
        positions_by_ticker=positions_by_ticker,
        closed_positions_by_ticker=closed_positions_by_ticker,
        risk_by_ticker=risk_by_ticker,
        signal_history_by_ticker=signal_history_by_ticker,
        news_by_ticker=news_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
    )
    trade_rows = _ensure_trade_rows_include_ticker(
        session,
        trade_rows,
        ticker_workspace.get("selected_ticker"),
    )
    ticker_workspace = build_ticker_workspace(
        trade_rows=trade_rows,
        selected_ticker=ticker_workspace.get("selected_ticker"),
        positions_by_ticker=positions_by_ticker,
        closed_positions_by_ticker=closed_positions_by_ticker,
        risk_by_ticker=risk_by_ticker,
        signal_history_by_ticker=signal_history_by_ticker,
        news_by_ticker=news_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
    )

    audit_detail = _load_trade_detail(session, decision_id) if decision_id else None
    if audit_detail is None:
        selected_decision_id = _latest_trade_decision_id_for_ticker(
            trade_rows,
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

    return {
        "selected_tab": selected_tab,
        "tabs": tuple({"id": tab_id, "label": label} for tab_id, label in _TAB_LABELS),
        "header": _build_header(latest_portfolio, latest_risk, trade_rows, latest_reflection),
        "job_timeline": _build_job_timeline(latest_reflection),
        "overview": {
            "command_center": _build_overview_command_center(
                header=_build_header(latest_portfolio, latest_risk, trade_rows, latest_reflection),
                positions=positions,
                closed_positions=closed_positions,
                ticker_workspace=ticker_workspace,
            ),
            "live_alerts": _load_live_alerts(session),
            "material_changes": _load_material_changes(session),
        },
        "portfolio": {
            "positions": positions,
            "option_positions": _load_option_positions(session),
            "hedge_overlays": _load_hedge_overlays(session),
        },
        "trades": {
            "rows": trade_rows,
            "selected_detail": audit_detail,
        },
        "ticker_workspace": ticker_workspace,
        "risk_macro": {
            "risk_config_version": latest_risk.resolver_version if latest_risk else None,
            "binding_constraints": tuple((latest_risk.concentration_flags_json or [])) if latest_risk else (),
            "events": (),
            "exposures": _load_risk_exposures(session),
        },
        "candidates": {
            "active_universe_filter": _serialize_universe_filter(active_universe_filter),
            "rows": _load_candidate_rows(session),
            "manual_requests": _load_manual_requests(session),
            "portfolio_intents": _load_portfolio_intents(session),
            "relationships": _load_relationships(session),
            "peer_baskets": _load_peer_baskets(session),
            "themes": _load_themes(session),
        },
        "learning_strategies": {
            "reflection": _serialize_reflection(latest_reflection),
            "learning_factors": _load_learning_factors(session),
            "strategy_performance": _load_strategy_performance(session),
            "strategy_proposals": _load_strategy_proposals(session),
        },
        "ops_cost": {
            "llm_usage": _load_llm_usage(session),
            "provider_usage": (),
        },
    }


def create_manual_request(session: Any, *, ticker: str, reason: str, mode: str) -> uuid.UUID:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required.")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("Reason is required.")
    if mode not in {"review_only", "paper_trade_eligible"}:
        raise ValueError("Unsupported manual request mode.")
    row = ManualTickerRequest(
        ticker=normalized_ticker,
        reason=normalized_reason,
        mode=mode,
        status="active",
        metadata_json={},
    )
    session.add(row)
    session.flush()
    return row.manual_ticker_request_id


def dismiss_manual_request(session: Any, request_id: str) -> None:
    rid = uuid.UUID(str(request_id))
    row = session.query(ManualTickerRequest).filter_by(manual_ticker_request_id=rid).first()
    if row is None:
        raise ValueError("Manual request not found.")
    row.status = "dismissed"


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


def _build_header(
    latest_portfolio: PortfolioSnapshot | None,
    latest_risk: PortfolioRiskSnapshot | None,
    trade_rows: list[dict[str, Any]],
    latest_reflection: DailyReflection | None,
) -> dict[str, Any]:
    trade_date = None
    if latest_portfolio:
        trade_date = latest_portfolio.snapshot_time.date()
    elif latest_risk:
        trade_date = latest_risk.decision_time.date()
    elif latest_reflection:
        trade_date = latest_reflection.trade_date

    macro_regime = None
    if latest_risk and isinstance(latest_risk.metadata_json, dict):
        macro_regime = latest_risk.metadata_json.get("macro_regime")

    return {
        "trade_date": trade_date,
        "macro_regime": macro_regime or "unavailable",
        "risk_appetite": latest_risk.risk_appetite if latest_risk else "unavailable",
        "nav": latest_portfolio.net_liquidation_value if latest_portfolio else None,
        "day_pnl": latest_portfolio.day_pnl if latest_portfolio else None,
        "buying_power": latest_portfolio.buying_power if latest_portfolio else None,
        "gross_exposure": latest_risk.gross_exposure if latest_risk else None,
        "open_alert_count": len([row for row in trade_rows if row.get("order_status") in {"rejected", "pending_new"}]),
        "material_signal_change_count": 0,
        "llm_cost_estimate": None,
    }


def _build_job_timeline(latest_reflection: DailyReflection | None) -> tuple[dict[str, Any], ...]:
    rows = [{"label": "Workstation", "status": "available"}]
    if latest_reflection:
        rows.append({"label": "Reflection", "status": latest_reflection.status})
    return tuple(rows)


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
            "summary": row.get("summary") or "Closed today and ready for review",
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


def _load_live_alerts(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(NewsAlert)
        .order_by(NewsAlert.published_at.desc())
        .limit(10)
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "severity": row.severity,
            "headline": row.headline,
            "summary": row.summary,
        }
        for row in rows
    )


def _load_material_changes(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(IntradaySignalSnapshot)
        .order_by(IntradaySignalSnapshot.decision_time.desc())
        .limit(10)
        .all()
    )
    changes: list[dict[str, Any]] = []
    for row in rows:
        delta = row.delta_vs_baseline_json or {}
        if not delta:
            continue
        changes.append({"ticker": row.ticker, "summary": ", ".join(delta.keys())})
    return tuple(changes)


def _load_positions(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(PaperPosition)
        .filter(PaperPosition.status == "open")
        .order_by(PaperPosition.updated_at.desc())
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "trade_identity": row.trade_identity,
            "strategy_id": row.strategy_id,
            "quantity": row.quantity,
            "market_value": row.market_value,
        }
        for row in rows
    )


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
            "strategy_id": row.strategy_id,
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
            "trade_identity": row.trade_identity,
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
            "protected_notional": row.protected_notional,
        }
        for row in rows
    )


def _load_trade_rows(session: Any) -> list[dict[str, Any]]:
    material_change_tickers = _load_material_signal_change_tickers(session)
    rows = (
        session.query(TradingDecision)
        .order_by(TradingDecision.decision_time.desc())
        .limit(25)
        .all()
    )
    return [_serialize_trade_row(session, row, material_change_tickers) for row in rows]


def _serialize_trade_row(
    session: Any,
    row: TradingDecision,
    material_change_tickers: set[str],
) -> dict[str, Any]:
    return {
        "trading_decision_id": str(row.trading_decision_id),
        "decision_time": row.decision_time,
        "created_at": row.created_at or row.decision_time,
        "ticker": row.ticker,
        "decision": row.decision,
        "instrument_type": row.instrument_type,
        "trade_identity": row.trade_identity,
        "selected_strategy_id": row.strategy_id,
        "expression_bucket_id": row.expression_bucket_id,
        "approved_weight": row.approved_weight,
        "confidence": row.confidence,
        "risk_status": row.risk_decision.status if row.risk_decision else None,
        "order_status": _load_order_status(session, row.trading_decision_id),
        "material_signal_change": str(row.ticker).upper() in material_change_tickers,
        "thesis": row.thesis,
        "invalidators": list(row.invalidators_json or []),
        "metadata_json": dict(row.metadata_json or {}),
    }


def _ensure_trade_rows_include_ticker(
    session: Any,
    trade_rows: list[dict[str, Any]],
    ticker: str | None,
) -> list[dict[str, Any]]:
    normalized_ticker = str(ticker or "").strip().upper()
    if not normalized_ticker:
        return trade_rows
    if any(str(row.get("ticker") or "").strip().upper() == normalized_ticker for row in trade_rows):
        return trade_rows

    material_change_tickers = _load_material_signal_change_tickers(session)
    latest_row = (
        session.query(TradingDecision)
        .filter(TradingDecision.ticker == normalized_ticker)
        .order_by(TradingDecision.decision_time.desc())
        .first()
    )
    if latest_row is None:
        return trade_rows

    return [*trade_rows, _serialize_trade_row(session, latest_row, material_change_tickers)]


def _load_order_status(session: Any, trading_decision_id: uuid.UUID) -> str | None:
    paper_order = session.query(PaperOrder).filter(PaperOrder.trading_decision_id == trading_decision_id).first()
    if paper_order is not None:
        return _normalize_order_status(paper_order.status)
    option_order = (
        session.query(PaperOptionOrder)
        .filter(PaperOptionOrder.trading_decision_id == trading_decision_id)
        .first()
    )
    if option_order is not None:
        return _normalize_order_status(option_order.status)
    return None


def _normalize_order_status(status: str | None) -> str | None:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    mapping = {
        "pending_new": "pending",
        "partially_filled": "partial_fill",
    }
    return mapping.get(normalized, normalized)


def _load_trade_detail(session: Any, decision_id: str) -> dict[str, Any] | None:
    try:
        rid = uuid.UUID(str(decision_id))
    except ValueError:
        return None
    row = session.query(TradingDecision).filter_by(trading_decision_id=rid).first()
    if row is None:
        return None
    signal_snapshot = row.candidate_score.signal_snapshot if row.candidate_score else None
    score_rows = []
    if row.candidate_score:
        related_scores = (
            session.query(CandidateScore)
            .filter(CandidateScore.signal_snapshot_id == row.candidate_score.signal_snapshot_id)
            .order_by(CandidateScore.candidate_score.desc())
            .all()
        )
        score_rows = [
            {"strategy_id": score.strategy_id, "candidate_score": score.candidate_score}
            for score in related_scores
        ]
    outcomes = (
        session.query(CandidateOutcomeEvaluation)
        .filter(CandidateOutcomeEvaluation.candidate_score_id == row.candidate_score_id)
        .order_by(CandidateOutcomeEvaluation.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "trading_decision_id": str(row.trading_decision_id),
        "ticker": row.ticker,
        "decision": row.decision,
        "decision_time": row.decision_time,
        "strategy_id": row.strategy_id,
        "expression_bucket_id": row.expression_bucket_id,
        "trade_identity": row.trade_identity,
        "confidence": row.confidence,
        "thesis": row.thesis,
        "invalidators": list(row.invalidators_json or []),
        "metadata_json": dict(row.metadata_json or {}),
        "llm_decision_json": row.prompt_run.parsed_output_json if row.prompt_run else {},
        "validation_status": row.prompt_run.parse_status if row.prompt_run else "unavailable",
        "signal_snapshot": signal_snapshot.signal_json if signal_snapshot else {},
        "strategy_scores": tuple(score_rows),
        "risk_decision": {
            "status": row.risk_decision.status,
            "reason_code": row.risk_decision.reason_code,
        }
        if row.risk_decision
        else None,
        "outcomes": tuple(
            {
                "evaluation_status": outcome.evaluation_status,
                "alpha": outcome.alpha,
            }
            for outcome in outcomes
        ),
    }


def _load_risk_exposures(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(RiskFactorExposure)
        .order_by(RiskFactorExposure.created_at.desc())
        .limit(20)
        .all()
    )
    return tuple(
        {
            "factor_type": row.factor_type,
            "factor_name": row.factor_value,
            "exposure": row.gross_exposure,
        }
        for row in rows
    )


def _load_candidate_rows(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(CandidateScore)
        .order_by(CandidateScore.decision_time.desc(), CandidateScore.candidate_score.desc())
        .limit(25)
        .all()
    )
    return tuple(
        {
            "ticker": row.ticker,
            "selection_source": row.selection_source,
            "selection_source_label": strategy_label(row.selection_source),
            "result_status": row.rejection_reason or "candidate",
            "result_status_label": candidate_result_label(row.rejection_reason or "candidate"),
            "trade_identity": row.trade_classifications[0].trade_identity if row.trade_classifications else None,
            "trade_identity_label": trade_identity_label(
                row.trade_classifications[0].trade_identity if row.trade_classifications else None
            ),
            "strategy_match": row.strategy_id,
            "strategy_match_label": strategy_label(row.strategy_id),
        }
        for row in rows
    )


def _load_manual_requests(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(ManualTickerRequest)
        .filter(ManualTickerRequest.status == "active")
        .order_by(ManualTickerRequest.created_at.desc())
        .all()
    )
    return tuple(
        {
            "manual_ticker_request_id": str(row.manual_ticker_request_id),
            "ticker": row.ticker,
            "reason": row.reason,
            "mode": row.mode,
            "status": row.status,
            "latest_result_status": row.latest_result_status,
        }
        for row in rows
    )


def _load_portfolio_intents(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(PortfolioIntent).order_by(PortfolioIntent.created_at.desc()).limit(20).all()
    return tuple(
        {
            "ticker": row.ticker,
            "intent_type": row.intent_type,
            "lifecycle_status": row.lifecycle_status,
        }
        for row in rows
    )


def _load_relationships(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(TickerRelationship).order_by(TickerRelationship.created_at.desc()).limit(20).all()
    return tuple(
        {
            "source_ticker": row.source_ticker,
            "target_ticker": row.target_ticker,
            "relationship_type": row.relationship_type,
        }
        for row in rows
    )


def _load_peer_baskets(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(PeerBasket).order_by(PeerBasket.created_at.desc()).limit(10).all()
    return tuple(
        {
            "basket_key": row.basket_key,
            "version": row.version,
            "member_count": len(row.members_json or []),
        }
        for row in rows
    )


def _load_themes(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(ThemeTaxonomy).order_by(ThemeTaxonomy.created_at.desc()).limit(20).all()
    return tuple(
        {
            "theme_id": row.theme_id,
            "display_name": row.display_name,
        }
        for row in rows
    )


def _serialize_reflection(reflection: DailyReflection | None) -> dict[str, Any] | None:
    if reflection is None:
        return None
    return {
        "status": reflection.status,
        "what_worked": tuple((reflection.reflection_json or {}).get("what_worked") or []),
    }


def _load_learning_factors(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(LearningFactor).order_by(LearningFactor.created_at.desc()).limit(20).all()
    return tuple(
        {
            "title": row.title,
            "status": row.status,
            "scope": row.scope,
        }
        for row in rows
    )


def _load_strategy_performance(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(CandidateOutcomeEvaluation).order_by(CandidateOutcomeEvaluation.created_at.desc()).all()
    grouped: dict[str, list[CandidateOutcomeEvaluation]] = {}
    for row in rows:
        grouped.setdefault(row.strategy_id, []).append(row)
    performance = []
    for strategy_id, items in grouped.items():
        alpha_values = [item.alpha for item in items if item.alpha is not None]
        performance.append(
            {
                "strategy_id": strategy_id,
                "lifecycle_status": "observed",
                "win_rate": None,
                "total_pnl": sum(alpha_values, Decimal("0")) if alpha_values else None,
            }
        )
    return tuple(performance[:20])


def _load_strategy_proposals(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(StrategyProposal).order_by(StrategyProposal.created_at.desc()).limit(20).all()
    return tuple(
        {
            "proposed_strategy_id": row.proposed_strategy_id,
            "proposal_status": row.proposal_status,
        }
        for row in rows
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
    allowed = {"timeline", "trend", "decisions", "risk"}
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


def _merge_audit_detail_into_workspace_detail(
    detail: dict[str, Any] | None,
    audit_detail: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if detail is None:
        return None
    if audit_detail is None:
        return detail
    if "latest_conclusion" in audit_detail and "tabs" in audit_detail:
        return audit_detail

    latest_conclusion = dict(detail.get("latest_conclusion") or {})
    trade_decision = dict(latest_conclusion.get("trade_decision") or {})
    risk_summary = dict(latest_conclusion.get("risk_summary") or {})
    tabs = dict(detail.get("tabs") or {})
    risk_tab = dict(tabs.get("risk") or {})

    trade_decision["summary"] = (
        trade_decision.get("summary")
        if str(trade_decision.get("summary") or "").strip() and trade_decision.get("summary") != "No material update"
        else _audit_trade_summary(audit_detail)
    )
    if not trade_decision.get("invalidators"):
        trade_decision["invalidators"] = list(audit_detail.get("invalidators") or [])
    if not trade_decision.get("strategy_id") or trade_decision.get("strategy_id") == "No material update":
        trade_decision["strategy_id"] = audit_detail.get("strategy_id") or trade_decision.get("strategy_id")
    if (
        not trade_decision.get("expression_bucket_id")
        or trade_decision.get("expression_bucket_id") == "No material update"
    ):
        trade_decision["expression_bucket_id"] = (
            audit_detail.get("expression_bucket_id") or trade_decision.get("expression_bucket_id")
        )
    if trade_decision.get("confidence") is None:
        trade_decision["confidence"] = audit_detail.get("confidence")

    if (
        not risk_summary.get("reason")
        or risk_summary.get("reason") == "No material update"
    ) and isinstance(audit_detail.get("risk_decision"), dict):
        risk_summary["reason"] = audit_detail["risk_decision"].get("reason_code") or risk_summary.get("reason")

    latest_conclusion["trade_decision"] = trade_decision
    latest_conclusion["risk_summary"] = risk_summary

    tabs["raw_json"] = audit_detail
    risk_tab["raw_json"] = audit_detail.get("risk_decision")
    tabs["risk"] = risk_tab

    return {
        **detail,
        "latest_conclusion": latest_conclusion,
        "tabs": tabs,
    }


def _audit_trade_summary(audit_detail: dict[str, Any]) -> str:
    thesis = str(audit_detail.get("thesis") or "").strip()
    if thesis:
        return thesis
    metadata = audit_detail.get("metadata_json")
    if isinstance(metadata, dict):
        selection_reason = str(metadata.get("selection_reason") or "").strip()
        if selection_reason:
            return selection_reason
    return "No material update"


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc


def _split_csv(raw: str, *, uppercase: bool = False) -> list[str]:
    parts = []
    for value in raw.split(","):
        normalized = value.strip()
        if not normalized:
            continue
        parts.append(normalized.upper() if uppercase else normalized)
    return parts


def _group_latest_by_ticker(rows: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if ticker not in grouped:
            grouped[ticker] = dict(row)
    return grouped


def _latest_trade_decision_id_for_ticker(
    trade_rows: list[dict[str, Any]],
    ticker: str | None,
) -> str | None:
    normalized_ticker = str(ticker or "").strip().upper()
    if not normalized_ticker:
        return None

    matching_rows = [row for row in trade_rows if str(row.get("ticker") or "").strip().upper() == normalized_ticker]
    if not matching_rows:
        return None

    latest_row = max(
        matching_rows,
        key=lambda row: row.get("decision_time") or row.get("created_at") or "",
    )
    return str(latest_row.get("trading_decision_id") or "") or None


def _load_material_signal_change_tickers(session: Any) -> set[str]:
    rows = (
        session.query(IntradaySignalSnapshot)
        .order_by(IntradaySignalSnapshot.decision_time.desc())
        .limit(100)
        .all()
    )
    tickers: set[str] = set()
    for row in rows:
        if row.delta_vs_baseline_json:
            tickers.add(str(row.ticker).upper())
    return tickers


def _load_risk_by_ticker(session: Any) -> dict[str, dict[str, Any]]:
    rows = (
        session.query(RiskDecision)
        .order_by(RiskDecision.decision_time.desc(), RiskDecision.created_at.desc())
        .limit(100)
        .all()
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.ticker or "").strip().upper()
        if not ticker or ticker in grouped:
            continue
        grouped[ticker] = {
            "status": row.status,
            "reason": row.reason_code,
            "history": [
                {
                    "time": row.decision_time or row.created_at,
                    "status": row.status,
                    "summary": row.reason_code,
                }
            ],
        }
    return grouped


def _load_signal_history_by_ticker(session: Any) -> dict[str, dict[str, Any]]:
    signal_rows = (
        session.query(SignalSnapshot)
        .order_by(SignalSnapshot.decision_time.desc(), SignalSnapshot.created_at.desc())
        .limit(100)
        .all()
    )
    intraday_rows = (
        session.query(IntradaySignalSnapshot)
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


def _load_news_by_ticker(session: Any) -> dict[str, list[dict[str, Any]]]:
    alert_rows = (
        session.query(NewsAlert)
        .order_by(NewsAlert.published_at.desc(), NewsAlert.created_at.desc())
        .limit(100)
        .all()
    )
    event_rows = (
        session.query(EventNewsItem)
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
        )
    return grouped


def _load_fundamentals_by_ticker(session: Any) -> dict[str, list[dict[str, Any]]]:
    rows = (
        session.query(SignalSnapshot)
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
                if _is_number(value)
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
                if _is_number(value)
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
                f"; catalyst quality {_format_decimal(catalyst_quality)}"
                if _is_number(catalyst_quality)
                else ""
            )
            items.append(f"Events/news sentiment {sentiment}{quality_text}.")

    if isinstance(technical, dict):
        technical_bits: list[str] = []
        if _is_number(technical.get("return_20d")):
            technical_bits.append(f"20d return {_format_pct(technical['return_20d'])}")
        if _is_number(technical.get("relative_volume")):
            technical_bits.append(f"relative volume {_format_decimal(technical['relative_volume'])}")
        if technical_bits:
            items.append(f"Technical: {', '.join(technical_bits)}.")

    if isinstance(fundamental, dict):
        fundamental_bits: list[str] = []
        if _is_number(fundamental.get("quality_score")):
            fundamental_bits.append(f"quality {_format_decimal(fundamental['quality_score'])}")
        if _is_number(fundamental.get("revenue_growth_score")):
            fundamental_bits.append(f"revenue growth {_format_decimal(fundamental['revenue_growth_score'])}")
        if _is_number(fundamental.get("margin_trend_score")):
            fundamental_bits.append(f"margin trend {_format_decimal(fundamental['margin_trend_score'])}")
        if _is_number(fundamental.get("valuation_percentile")):
            fundamental_bits.append(f"valuation percentile {_format_decimal(fundamental['valuation_percentile'])}")
        if fundamental_bits:
            items.append(f"Fundamental: {', '.join(fundamental_bits)}.")

    return items


def _price_technical_summary(technical: dict[str, Any]) -> str:
    parts: list[str] = []
    if _is_number(technical.get("return_20d")):
        parts.append(f"20d return {_format_pct(technical['return_20d'])}")
    below_levels = [
        label
        for key, label in (
            ("price_vs_sma_20", "SMA20"),
            ("price_vs_sma_50", "SMA50"),
            ("price_vs_sma_200", "SMA200"),
        )
        if _is_number(technical.get(key)) and float(technical[key]) < 0
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
    if _is_number(technical.get("rs_vs_spy_1d")):
        parts.append(f"RS vs SPY {_format_pct(technical['rs_vs_spy_1d'])}")
    else:
        parts.append("RS vs SPY unavailable")
    if _is_number(technical.get("relative_volume")):
        parts.append(f"relative volume {_format_decimal(technical['relative_volume'])}")
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
        if not _is_number(value):
            continue
        items.append(
            {
                "title": title,
                "summary": _format_decimal(value),
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
    grouped.setdefault(ticker, []).append(
        {
            "title": normalized_title,
            "summary": normalized_summary,
            "published_at": published_at,
        }
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def _format_decimal(value: Any) -> str:
    return f"{float(value):.2f}"
