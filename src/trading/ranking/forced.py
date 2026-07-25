"""Pure aggregation of independent forced-ranking reasons."""
from __future__ import annotations

from collections.abc import Iterable


_REASON_INPUTS = (
    "manual_request",
    "watchlist_pin",
    "open_position",
    "manual_include",
)


def resolve_forced_tickers(
    *,
    manual_requests: Iterable[str] = (),
    watchlist_pins: Iterable[str] = (),
    open_positions: Iterable[str] = (),
    manual_includes: Iterable[str] = (),
    manual_excludes: Iterable[str] = (),
) -> dict[str, tuple[str, ...]]:
    """Return deterministic, deduplicated reasons after hard exclusions."""
    inputs = (manual_requests, watchlist_pins, open_positions, manual_includes)
    excluded = {_ticker(ticker) for ticker in manual_excludes}
    reasons_by_ticker: dict[str, list[str]] = {}
    for reason, tickers in zip(_REASON_INPUTS, inputs):
        for ticker_value in tickers:
            ticker = _ticker(ticker_value)
            if not ticker or ticker in excluded:
                continue
            reasons = reasons_by_ticker.setdefault(ticker, [])
            if reason not in reasons:
                reasons.append(reason)
    return {
        ticker: tuple(reasons_by_ticker[ticker])
        for ticker in sorted(reasons_by_ticker)
    }


def _ticker(value: str) -> str:
    return str(value).strip().upper()
