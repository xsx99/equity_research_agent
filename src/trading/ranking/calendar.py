"""Exchange-calendar boundary adapter for decision-time ranking inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class RankingSession:
    """A completed XNYS session and its scheduled UTC close."""

    session_date: date
    scheduled_close: datetime


class RankingSessionCalendar:
    """Small XNYS wrapper so loaders and replay can inject deterministic calendars."""

    def __init__(self, calendar: Any | None = None) -> None:
        if calendar is None:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar("XNYS")
        self._calendar = calendar

    def latest_completed_session(self, decision_time: datetime) -> RankingSession:
        timestamp = _utc(decision_time)
        sessions = self._calendar.sessions_in_range(
            timestamp.date() - timedelta(days=14),
            timestamp.date(),
        )
        completed = [
            session
            for session in sessions
            if _utc(self._calendar.session_close(session)) <= timestamp
        ]
        if not completed:
            raise RuntimeError("no_completed_xnys_session")
        session = completed[-1]
        return RankingSession(
            session_date=session.date(),
            scheduled_close=_utc(self._calendar.session_close(session)),
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
