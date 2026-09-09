"""Persisted decision-time context for candidate outcome maturation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from src.trading.outcomes.finalization import resolve_finalization
from src.trading.outcomes.horizons import OutcomeHorizonPolicy, UnsupportedOutcomeHorizon


@dataclass(frozen=True)
class PersistedCandidateOutcomeContext:
    """Original candidate, comparators, selection, and fill lineage."""

    candidate: Any
    snapshot_type: str
    trade_classification: Any | None
    peer_basket_id: str | None
    sector_theme_symbols: tuple[str, ...]
    peer_symbols: tuple[str, ...]
    opportunity_symbols: tuple[str, ...]
    has_complete_close: bool
    complete_close_at: datetime | None
    watch_candidate: Any | None = None
    primary_comparator_key: str = "QQQ"
    comparator_members: dict[str, tuple[str, ...]] | None = None
    comparator_weights: dict[str, dict[str, float]] | None = None
    selected_orders: tuple[Any, ...] = ()
    selected_fills: tuple[Any, ...] = ()
    due_evaluation_statuses: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparator_members", dict(self.comparator_members or {}))
        object.__setattr__(self, "comparator_weights", dict(self.comparator_weights or {}))


def comparator_context(
    benchmark_context: dict[str, Any],
    *,
    peer_basket_id: str | None = None,
    peer_members: Iterable[Any] = (),
) -> dict[str, Any]:
    """Read only explicit comparator identities/members persisted at decision time."""
    context = dict(benchmark_context or {})
    primary = _symbol(context.get("primary_benchmark")) or "QQQ"
    sector_symbols = _symbols(context.get("sector_theme_symbols") or context.get("sector_theme_etfs") or ())

    persisted_peer_id = str(context.get("peer_basket_id") or peer_basket_id or "") or None
    raw_peer_members = context.get("peer_basket_members") or context.get("peer_symbols") or tuple(peer_members)
    peer_symbols, peer_weights = _members_and_weights(raw_peer_members)

    opportunity_key = str(context.get("opportunity_set_key") or "") or None
    raw_opportunity_members = context.get("opportunity_set_members") or context.get("opportunity_symbols") or ()
    opportunity_symbols, opportunity_weights = _members_and_weights(raw_opportunity_members)

    members: dict[str, tuple[str, ...]] = {}
    weights: dict[str, dict[str, float]] = {}
    if persisted_peer_id and peer_symbols:
        key = f"peer:{persisted_peer_id}"
        members[key] = peer_symbols
        if peer_weights:
            weights[key] = peer_weights
    if opportunity_key and opportunity_symbols:
        members[opportunity_key] = opportunity_symbols
        if opportunity_weights:
            weights[opportunity_key] = opportunity_weights
    return {
        "primary_comparator_key": primary,
        "peer_basket_id": persisted_peer_id,
        "sector_theme_symbols": sector_symbols,
        "peer_symbols": peer_symbols,
        "opportunity_symbols": opportunity_symbols,
        "comparator_members": members,
        "comparator_weights": weights,
    }


def complete_close_from_lineage(
    orders: Iterable[Any],
    fills: Iterable[Any],
    *,
    trade_identity: str | None = None,
) -> tuple[bool, datetime | None]:
    """Return the first fill timestamp that fully closes entered quantity."""
    if trade_identity == "tactical_option_trade":
        return False, None
    action_by_order = {str(order.paper_order_id): str(order.action) for order in orders}
    open_quantity = 0.0
    entered = False
    for fill in sorted(fills, key=lambda item: (item.executed_at, str(item.paper_execution_id))):
        action = action_by_order.get(str(fill.paper_order_id))
        quantity = abs(float(fill.quantity))
        if action in {"enter_long", "enter_short"}:
            open_quantity += quantity
            entered = True
        elif action in {"reduce", "exit"} and entered:
            open_quantity = max(0.0, open_quantity - quantity)
            if open_quantity <= 1e-9:
                return True, fill.executed_at
    return False, None


def due_evaluation_statuses(
    context: PersistedCandidateOutcomeContext,
    *,
    evaluation_as_of_session: date,
    existing_outcomes: Iterable[Any],
    horizon_policy: OutcomeHorizonPolicy | None = None,
) -> tuple[str, ...]:
    """Return matured checkpoints absent from persisted production outcomes."""
    policy = horizon_policy or OutcomeHorizonPolicy()
    candidate = context.candidate
    try:
        checkpoints = policy.checkpoints_for(
            typical_horizon=candidate.typical_horizon,
            decision_session=candidate.decision_time.date(),
        )
    except UnsupportedOutcomeHorizon:
        return ("unsupported_horizon",)

    finalization = resolve_finalization(
        trade_identity=str(getattr(context.trade_classification, "trade_identity", "watch_only")),
        has_complete_close=context.has_complete_close,
        complete_close_at=context.complete_close_at,
        horizon_end_at=policy.session_close(checkpoints.final_session),
    )
    expected = {
        "interim": policy.session_close(checkpoints.interim_session),
        "final": finalization.horizon_end_at,
    }
    due: list[str] = []
    for status in ("interim", "final"):
        checkpoint = expected[status]
        if checkpoint.date() > evaluation_as_of_session:
            continue
        if any(
            str(getattr(row, "candidate_score_id", "")) == str(candidate.candidate_score_id)
            and getattr(row, "evaluation_status", None) == status
            and _same_checkpoint(getattr(row, "horizon_end_at", None), checkpoint)
            for row in existing_outcomes
        ):
            continue
        due.append(status)
    return tuple(due)


def _members_and_weights(values: Iterable[Any]) -> tuple[tuple[str, ...], dict[str, float]]:
    symbols: set[str] = set()
    weights: dict[str, float] = {}
    for value in values:
        if isinstance(value, dict):
            symbol = _symbol(value.get("symbol") or value.get("ticker"))
            weight = value.get("weight")
        else:
            symbol = _symbol(value)
            weight = None
        if not symbol:
            continue
        symbols.add(symbol)
        if isinstance(weight, (int, float)):
            weights[symbol] = float(weight)
    ordered = tuple(sorted(symbols))
    return ordered, {symbol: weights[symbol] for symbol in ordered if symbol in weights}


def _symbols(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({symbol for value in values if (symbol := _symbol(value))}))


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _same_checkpoint(actual: datetime | None, expected: datetime) -> bool:
    if actual is None:
        return False
    return actual == expected

