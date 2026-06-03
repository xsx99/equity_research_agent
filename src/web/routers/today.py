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
):
    with get_session() as session:
        dashboard = load_today_dashboard(session, selected_tab=tab, decision_id=decision_id)
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


def load_today_dashboard(session: Any, *, selected_tab: str, decision_id: str | None) -> dict[str, Any]:
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
    selected_detail = _load_trade_detail(session, decision_id) if decision_id else None
    if selected_detail is None and trade_rows:
        selected_detail = _load_trade_detail(session, trade_rows[0]["trading_decision_id"])

    return {
        "selected_tab": selected_tab,
        "tabs": tuple({"id": tab_id, "label": label} for tab_id, label in _TAB_LABELS),
        "header": _build_header(latest_portfolio, latest_risk, trade_rows, latest_reflection),
        "job_timeline": _build_job_timeline(latest_reflection),
        "overview": {
            "live_alerts": _load_live_alerts(session),
            "material_changes": _load_material_changes(session),
        },
        "portfolio": {
            "positions": _load_positions(session),
            "option_positions": _load_option_positions(session),
            "hedge_overlays": _load_hedge_overlays(session),
        },
        "trades": {
            "rows": trade_rows,
            "selected_detail": selected_detail,
        },
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
    rows = (
        session.query(TradingDecision)
        .order_by(TradingDecision.decision_time.desc())
        .limit(25)
        .all()
    )
    return [
        {
            "trading_decision_id": str(row.trading_decision_id),
            "decision_time": row.decision_time,
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
        }
        for row in rows
    ]


def _load_order_status(session: Any, trading_decision_id: uuid.UUID) -> str | None:
    paper_order = session.query(PaperOrder).filter(PaperOrder.trading_decision_id == trading_decision_id).first()
    if paper_order is not None:
        return paper_order.status
    option_order = (
        session.query(PaperOptionOrder)
        .filter(PaperOptionOrder.trading_decision_id == trading_decision_id)
        .first()
    )
    if option_order is not None:
        return option_order.status
    return None


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
            "result_status": row.rejection_reason or "candidate",
            "trade_identity": row.trade_classifications[0].trade_identity if row.trade_classifications else None,
            "strategy_match": row.strategy_id,
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
