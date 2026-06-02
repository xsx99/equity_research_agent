"""Pure helpers for structured ticker relationships and peer baskets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


@dataclass(frozen=True)
class TickerRelationship:
    """Directed source-to-target relationship with explicit allowed uses."""

    source_ticker: str
    target_ticker: str
    relationship_type: str
    confidence: float
    strength_score: float
    allowed_uses: tuple[str, ...]
    theme_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ticker", _normalize_ticker(self.source_ticker))
        object.__setattr__(self, "target_ticker", _normalize_ticker(self.target_ticker))
        object.__setattr__(self, "allowed_uses", tuple(self.allowed_uses))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        _validate_unit_interval("confidence", self.confidence)
        _validate_unit_interval("strength_score", self.strength_score)


@dataclass(frozen=True)
class PeerBasketDefinition:
    """Versioned decision-time peer basket built from explicit relationships."""

    basket_key: str
    version: str
    trade_date: date
    members: tuple[str, ...]
    construction_method: str
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(_normalize_ticker(member) for member in self.members))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))


@dataclass(frozen=True)
class ThemeTaxonomyNode:
    """User-maintained theme taxonomy node for grouping and read-through."""

    theme_id: str
    display_name: str
    parent_theme_id: str | None = None
    description: str | None = None
    lifecycle_status: str = "active"


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _validate_unit_interval(field_name: str, value: float) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")


def relationship_can_be_used_for(relationship: TickerRelationship, allowed_use: str) -> bool:
    """Return whether a relationship explicitly permits a use."""
    return allowed_use in relationship.allowed_uses


def build_peer_basket_members(
    source_ticker: str,
    relationships: Iterable[TickerRelationship],
    allowed_use: str = "peer_basket",
) -> list[str]:
    """Return sorted unique target tickers explicitly allowed in a peer basket."""
    normalized_source = _normalize_ticker(source_ticker)
    members = {
        relationship.target_ticker
        for relationship in relationships
        if relationship.source_ticker == normalized_source
        and relationship_can_be_used_for(relationship, allowed_use)
    }
    return sorted(members)


def build_peer_basket_definition(
    basket_key: str,
    version: str,
    trade_date: date,
    source_ticker: str,
    relationships: Iterable[TickerRelationship],
    source_refs: Iterable[str] = (),
    construction_method: str = "relationship_graph_v1",
) -> PeerBasketDefinition:
    """Build a versioned peer basket from explicit source relationships."""
    return PeerBasketDefinition(
        basket_key=basket_key,
        version=version,
        trade_date=trade_date,
        members=tuple(build_peer_basket_members(source_ticker, relationships)),
        construction_method=construction_method,
        source_refs=tuple(source_refs),
    )
