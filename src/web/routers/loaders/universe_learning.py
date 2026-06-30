"""Universe and learning loader helpers for the today router."""
from __future__ import annotations

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
    rows = session.query(StrategyProposal).order_by(StrategyProposal.created_at.desc()).limit(20).all()
    return tuple(
        {
            "proposed_strategy_id": row.proposed_strategy_id,
            "proposal_status": row.proposal_status,
            "proposal_status_label": generic_status_label(row.proposal_status),
        }
        for row in rows
    )


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
