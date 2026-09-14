"""Canonical XNYS horizon policy for persisted candidate maturity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class OutcomeSessionOffsets:
    """Approved interim and final session offsets after a decision session."""

    interim_session_offset: int
    final_session_offset: int


@dataclass(frozen=True)
class OutcomeCheckpoints:
    """Concrete XNYS sessions for an outcome's interim and final marks."""

    interim_session_offset: int
    final_session_offset: int
    interim_session: date
    final_session: date


class UnsupportedOutcomeHorizon(ValueError):
    """Raised when a stored horizon is not in the explicit outcome contract."""


_OFFSETS: dict[str, OutcomeSessionOffsets] = {
    "intraday-2d": OutcomeSessionOffsets(1, 2),
    "intraday-3d": OutcomeSessionOffsets(1, 3),
    "1d-2w": OutcomeSessionOffsets(1, 10),
    "2d-3w": OutcomeSessionOffsets(2, 15),
    "2d-4w": OutcomeSessionOffsets(2, 20),
    "3d-4w": OutcomeSessionOffsets(3, 20),
    "1-6w": OutcomeSessionOffsets(5, 30),
    "1-8w": OutcomeSessionOffsets(5, 40),
    "2-8w": OutcomeSessionOffsets(10, 40),
    "2w-8w": OutcomeSessionOffsets(10, 40),
    "2w-3m": OutcomeSessionOffsets(10, 63),
    "1-3m": OutcomeSessionOffsets(21, 63),
    "2-12w": OutcomeSessionOffsets(10, 60),
    "intraday-3m": OutcomeSessionOffsets(1, 63),
    "intraday-4w": OutcomeSessionOffsets(1, 20),
    "multi-month+": OutcomeSessionOffsets(63, 126),
}


class OutcomeHorizonPolicy:
    """Map only approved horizons to deterministic XNYS checkpoint sessions."""

    def __init__(self, calendar: Any | None = None) -> None:
        if calendar is None:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar("XNYS")
        self._calendar = calendar

    def offsets_for(self, typical_horizon: str) -> OutcomeSessionOffsets:
        try:
            return _OFFSETS[typical_horizon]
        except KeyError as exc:
            raise UnsupportedOutcomeHorizon(f"unsupported_horizon:{typical_horizon}") from exc

    def checkpoints_for(self, *, typical_horizon: str, decision_session: date) -> OutcomeCheckpoints:
        offsets = self.offsets_for(typical_horizon)
        sessions = self._calendar.sessions_in_range(
            decision_session,
            decision_session + timedelta(days=(offsets.final_session_offset + 20) * 2),
        )
        session_dates = tuple(session.date() for session in sessions)
        try:
            index = session_dates.index(decision_session)
        except ValueError as exc:
            raise ValueError(f"decision_session_not_xnys:{decision_session.isoformat()}") from exc
        return OutcomeCheckpoints(
            interim_session_offset=offsets.interim_session_offset,
            final_session_offset=offsets.final_session_offset,
            interim_session=session_dates[index + offsets.interim_session_offset],
            final_session=session_dates[index + offsets.final_session_offset],
        )

    def session_close(self, session_date: date) -> datetime:
        """Return the exchange-calendar close in UTC, including DST changes."""
        value = self._calendar.session_close(session_date)
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
