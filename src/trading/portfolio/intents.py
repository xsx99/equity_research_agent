"""Pure portfolio-intent helpers for core-holding eligibility."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PortfolioIntentConfig:
    """User-approved core holding configuration independent of DB sessions."""

    ticker: str
    intent_type: str
    target_weight: float
    max_weight: float
    lifecycle_status: str
    add_rules: tuple[str, ...] = ()
    trim_rules: tuple[str, ...] = ()
    thesis_invalidators: tuple[str, ...] = ()
    allowed_tactical_interactions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", _normalize_ticker(self.ticker))
        object.__setattr__(self, "add_rules", tuple(self.add_rules))
        object.__setattr__(self, "trim_rules", tuple(self.trim_rules))
        object.__setattr__(self, "thesis_invalidators", tuple(self.thesis_invalidators))
        object.__setattr__(
            self,
            "allowed_tactical_interactions",
            tuple(self.allowed_tactical_interactions),
        )


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def find_active_portfolio_intent(
    ticker: str,
    intents: Iterable[PortfolioIntentConfig],
) -> PortfolioIntentConfig | None:
    """Return the active intent for a ticker, if one exists."""
    normalized_ticker = _normalize_ticker(ticker)
    for intent in intents:
        if intent.ticker == normalized_ticker and intent.lifecycle_status == "active":
            return intent
    return None


def is_core_holding_approved(ticker: str, intents: Iterable[PortfolioIntentConfig]) -> bool:
    """Return whether a ticker has an active core-holding intent."""
    return find_active_portfolio_intent(ticker, intents) is not None


def max_weight_for_ticker(
    ticker: str,
    intents: Iterable[PortfolioIntentConfig],
) -> float | None:
    """Return the active core-intent max weight for a ticker."""
    intent = find_active_portfolio_intent(ticker, intents)
    if intent is None:
        return None
    return intent.max_weight


def allowed_tactical_interactions_for_ticker(
    ticker: str,
    intents: Iterable[PortfolioIntentConfig],
) -> tuple[str, ...]:
    """Return active core-intent tactical interactions for a ticker."""
    intent = find_active_portfolio_intent(ticker, intents)
    if intent is None:
        return ()
    return intent.allowed_tactical_interactions


def tactical_interaction_allowed(
    ticker: str,
    intents: Iterable[PortfolioIntentConfig],
    interaction: str,
) -> bool:
    """Return whether an active core intent permits a tactical interaction."""
    return interaction in allowed_tactical_interactions_for_ticker(ticker, intents)
