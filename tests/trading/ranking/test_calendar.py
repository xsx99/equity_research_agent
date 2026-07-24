from datetime import datetime, timezone

from src.trading.ranking.calendar import RankingSessionCalendar


def test_xnys_latest_completed_session_handles_weekends_and_holidays():
    calendar = RankingSessionCalendar()

    weekend = calendar.latest_completed_session(datetime(2026, 7, 5, 15, tzinfo=timezone.utc))
    holiday = calendar.latest_completed_session(datetime(2026, 7, 6, 13, tzinfo=timezone.utc))

    assert weekend.session_date.isoformat() == "2026-07-02"
    assert holiday.session_date.isoformat() == "2026-07-02"


def test_xnys_latest_completed_session_excludes_today_before_close_and_includes_it_after():
    calendar = RankingSessionCalendar()

    before_close = calendar.latest_completed_session(datetime(2026, 7, 21, 19, 59, tzinfo=timezone.utc))
    after_close = calendar.latest_completed_session(datetime(2026, 7, 21, 20, 1, tzinfo=timezone.utc))

    assert before_close.session_date.isoformat() == "2026-07-20"
    assert after_close.session_date.isoformat() == "2026-07-21"
    assert after_close.scheduled_close == datetime(2026, 7, 21, 20, tzinfo=timezone.utc)


def test_xnys_early_close_is_exposed_in_utc():
    calendar = RankingSessionCalendar()

    session = calendar.latest_completed_session(datetime(2026, 11, 27, 18, 1, tzinfo=timezone.utc))

    assert session.session_date.isoformat() == "2026-11-27"
    assert session.scheduled_close == datetime(2026, 11, 27, 18, tzinfo=timezone.utc)
