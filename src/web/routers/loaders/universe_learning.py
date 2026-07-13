"""Universe and learning loader helpers for the today router."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.db.models.trading import (
    CandidateOutcomeEvaluation,
    DailyReflection,
    LearningFactor,
    PeerBasket,
    StrategyDefinition,
    StrategyEvaluationResult,
    StrategyProposal,
    ThemeTaxonomy,
    TickerRelationship,
)
from src.web.presenters.today_copy import generic_status_label, scope_label

_STRATEGY_PROPOSAL_LOOKBACK_DAYS = 10


def _strategy_proposal_recent_cutoff(*, today: date | None = None) -> date:
    anchor = today or date.today()
    return anchor - timedelta(days=_STRATEGY_PROPOSAL_LOOKBACK_DAYS - 1)


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
    payload = reflection.reflection_json or {}
    return {
        "status": reflection.status,
        "status_label": generic_status_label(reflection.status),
        "what_worked": tuple(payload.get("what_worked") or []),
        "what_failed": tuple(payload.get("what_failed") or []),
        "attribution": tuple(payload.get("attribution") or []),
    }


def _load_learning_factors(session: Any) -> tuple[dict[str, Any], ...]:
    rows = session.query(LearningFactor).order_by(LearningFactor.created_at.desc()).limit(20).all()
    return tuple(
        {
            "factor_key": row.factor_key,
            "title": row.title,
            "status": row.status,
            "scope": row.scope,
            "effect_tags": tuple(row.effect_tags_json or ()),
            "status_label": generic_status_label(row.status),
            "scope_label": scope_label(row.scope),
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
        winning_alpha_values = [alpha for alpha in alpha_values if alpha > 0]
        win_rate = (
            (Decimal(len(winning_alpha_values)) / Decimal(len(alpha_values)) * Decimal("100")).quantize(Decimal("0.1"))
            if alpha_values
            else None
        )
        performance.append(
            {
                "strategy_id": strategy_id,
                "lifecycle_status": "observed",
                "lifecycle_status_label": generic_status_label("observed"),
                "win_rate": win_rate,
                "total_pnl": sum(alpha_values, Decimal("0")) if alpha_values else None,
            }
        )
    return tuple(performance[:20])


def _load_strategy_proposals(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(StrategyProposal)
        .filter(StrategyProposal.trade_date >= _strategy_proposal_recent_cutoff())
        .order_by(StrategyProposal.trade_date.desc(), StrategyProposal.created_at.desc())
        .limit(100)
        .all()
    )
    return tuple(
        _serialize_strategy_proposal(row)
        for row in rows
    )


def _serialize_strategy_proposal(row: StrategyProposal) -> dict[str, Any]:
    proposal_json = row.proposal_json or {}
    return {
        "trade_date": row.trade_date,
        "proposed_strategy_id": row.proposed_strategy_id,
        "display_name": row.display_name,
        "proposal_status": row.proposal_status,
        "proposal_status_label": generic_status_label(row.proposal_status),
        "proposed_lifecycle_status": row.proposed_lifecycle_status,
        "proposed_lifecycle_status_label": generic_status_label(row.proposed_lifecycle_status),
        "duplicate_of_strategy_id": row.duplicate_of_strategy_id,
        "rejection_reason": row.rejection_reason,
        "core_thesis": str(proposal_json.get("core_thesis") or "").strip(),
        "typical_horizon": str(proposal_json.get("typical_horizon") or "").strip(),
        "required_signals": tuple(proposal_json.get("required_signals") or ()),
        "optional_signals": tuple(proposal_json.get("optional_signals") or ()),
        "risk_tags": tuple(proposal_json.get("risk_tags") or ()),
        "macro_blocked_regimes": tuple(proposal_json.get("macro_blocked_regimes") or ()),
        "invalidators": tuple(proposal_json.get("invalidators") or ()),
        "evidence_summary": row.evidence_summary,
    }


def _load_strategy_definitions(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(StrategyDefinition)
        .filter(StrategyDefinition.source == "reflection_learning")
        .order_by(StrategyDefinition.created_at.desc())
        .limit(20)
        .all()
    )
    return tuple(
        {
            "strategy_id": row.strategy_id,
            "lifecycle_status": row.lifecycle_status,
            "lifecycle_status_label": generic_status_label(row.lifecycle_status),
            "source": row.source,
        }
        for row in rows
    )


def _load_strategy_evaluation_results(session: Any) -> tuple[dict[str, Any], ...]:
    rows = (
        session.query(StrategyEvaluationResult)
        .order_by(StrategyEvaluationResult.created_at.desc())
        .limit(20)
        .all()
    )
    return tuple(
        {
            "evaluation_status": row.evaluation_status,
            "evaluation_status_label": generic_status_label(row.evaluation_status),
            "new_lifecycle_status": row.new_lifecycle_status,
            "new_lifecycle_status_label": generic_status_label(row.new_lifecycle_status),
            "strategy_id": row.strategy_id,
        }
        for row in rows
    )
