# Prompt 05 — Fix the AAPL earnings date (Risk & Macro → Event Risk)

You are editing the equity_research_agent repo. Make ONLY the changes described. Run
the matching tests.

## Problem
The Event Risk section shows "AAPL earnings — 2026-06-17 05:47:11.773858+00:00",
which is wrong. There are TWO separate root causes; fix both.

## Root cause A — the on-screen data is synthetic smoke data
- `scripts/run_trading_macro_event_db_smoke.py:112` sets
  `event_time = smoke_time + timedelta(hours=6)` where
  `smoke_time = datetime.now(timezone.utc)` (line 33). That is why the date is always
  "today + a few hours" with microseconds, never a real earnings date.

## Root cause B — even the real pipeline discards the true earnings date
- `src/trading/events/calendar.py:86-89` reconstructs earnings time as
  `decision_time.date() + timedelta(days=earnings_in_days)` at `time(20, 0)` UTC — it
  only has an integer day-count, not the real date.
- `src/providers/market_data/alpaca_provider.py`
  (`_fetch_earnings_in_days_from_finnhub`, ~line 630) fetches the real Finnhub
  earnings calendar but throws away the actual date and returns only
  `earnings_in_days` (an int). The true date is lost.

## Changes
1. **Real pipeline (primary fix):** thread the ACTUAL earnings date through instead
   of an integer day-count.
   - In `alpaca_provider._fetch_earnings_in_days_from_finnhub`, return the real
     earnings date/datetime from the Finnhub `earningsCalendar` payload (you may keep
     `earnings_in_days` too if other callers need it, but expose the date).
   - In `src/trading/events/calendar.py:86-104`, set `event_time` from that real date
     when available; only fall back to `decision_time + timedelta(days=earnings_in_days)`
     when the real date is missing. Keep `event_key` aligned with the actual date.
2. **Smoke seed:** in `scripts/run_trading_macro_event_db_smoke.py`, stop using
   `now() + timedelta(hours=6)` for AAPL earnings. Use a fixed, realistic future
   earnings date (date-only) so the demo doesn't show a bogus "today+6h" timestamp.
3. **Display formatting:** in the Event Risk template
   (`src/templates/today.html:735`, `<p>{{ row.scheduled_at }}</p>`) and/or in
   `_event_row` (`src/web/presenters/today_risk_macro.py:150-161`), format the
   timestamp as a clean date (e.g. `2026-07-31` or `Jul 31, 2026`), never the raw
   `2026-06-17 05:47:11.773858+00:00` microsecond string.

## Acceptance criteria
- When a real Finnhub earnings date is available, the Event Risk row shows that exact
  date.
- The UI never displays a microsecond-precision raw timestamp.
- Smoke data shows a plausible fixed earnings date, not "now + 6h".
- `pytest tests/trading/test_event_calendar.py tests/web/test_today_risk_macro.py -q`
  passes (update fixtures to assert the real date flows through).
