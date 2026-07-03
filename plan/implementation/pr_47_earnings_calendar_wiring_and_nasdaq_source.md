# Handoff — Fix earnings-calendar wiring bug + move earnings source to Nasdaq

**Investigation done → implementation handoff.** Root cause confirmed in code (file:line below).
Nothing applied. Line numbers approximate — reconfirm before editing.

## TL;DR

The earnings calendar is broken in TWO ways, and **the wiring bug must be fixed first — swapping the
data source alone will NOT clear the missing signals or restore earnings risk.**

1. **Wiring bug (source-independent):** earnings data is written to the `fundamental` family but the
   `events_news` builder is what *requires* it and reads it from the `events_news` family → so
   `events_news.earnings_in_days` and `events_news.known_event_date` are **structurally always
   missing**, and the earnings-proximity risk gate never fires.
2. **Data source:** the current source is Finnhub `/calendar/earnings` (free-tier-limited). Replace
   it with Nasdaq's free calendar API (owner's request; they cross-check against
   nasdaq.com/market-activity/earnings).

## Root cause (confirmed)

### The family mismatch

- Earnings is fetched inside `AlpacaMarketDataProvider.fetch_context` via Finnhub
  (`_fetch_earnings_in_days_from_finnhub`, `src/providers/market_data/alpaca_provider.py:417-454`)
  and returned in the context payload as `earnings_in_days` / `earnings_date` / `known_event_date`
  (:256-258).
- `_refresh_fundamental` copies those into the **fundamental** snapshot's `normalized_metrics_json`
  (`src/trading/signals/source_ingestion.py:340-342`), which becomes a `source_family="fundamental"`
  record (`src/trading/signals/sources.py:147,155`).
- BUT the fields are *required by* the **events_news** family:
  `REQUIRED_EVENT_NEWS_FIELDS` includes `earnings_in_days`, `known_event_date`
  (`src/trading/signals/event_news.py:22-24`), and `build_event_news_signals` only picks them up
  from **events_news** record payloads (`event_news.py:79-82`). Nothing ever writes earnings into an
  events_news record → both stay `None` → always listed missing (`event_news.py:122-125`).
- The **fundamental** builder doesn't rescue it either: it surfaces `earnings_date`/`known_event_date`
  (`src/trading/signals/fundamental.py:45-48`) but NOT `earnings_in_days`, and marks none required.
- `own_earnings_event_type` (`event_news.py:83`) is likewise never set, because no earnings *event*
  record with `event_type` starting `own_earnings` is ever emitted.

### Impact beyond the missing-signal UI noise (this is the important part)

- **Earnings-proximity risk gate is blind.** `preopen_risk.py:341` and `lookahead_risk.py:206`
  (`_earnings_in_days`) read `event_news.get("earnings_in_days")` — always `None` — so the
  "earnings within 0–5 days → hedge/avoid" logic (`lookahead_risk.py:64-71`) never triggers from
  calendar data.
- **Earnings date partially survives** via a fallback chain: `preopen_risk.py:356-358` falls back to
  `fundamental.known_event_date` / `fundamental.earnings_date`, so date display and the macro
  calendar still work off the fundamental copy. But "days until" has no such fallback.
- **Strategy matching** on `own_earnings_event_type` (`src/trading/strategies/matching.py:451,459`)
  never matches. Same field referenced in calibration/replay contracts
  (`strategies/calibration.py:73`, `replay/outcomes.py:159`).

## The Nasdaq API (verified)

- Endpoint: `GET https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`
- **Per-date** (returns ALL companies reporting that day), NOT per-symbol. JSON at
  `response["data"]["rows"]`; each row has `symbol`, `name`, `time` (e.g. time-before-open /
  after-hours), `epsForecast`, `marketCap`, etc. Column set is in `response["data"]["headers"]`.
- **Requires browser-like headers** or it returns 403/empty. Minimum viable set:
  ```python
  {
      "authority": "api.nasdaq.com",
      "accept": "application/json, text/plain, */*",
      "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "origin": "https://www.nasdaq.com",
      "referer": "https://www.nasdaq.com/",
      "accept-language": "en-US,en;q=0.9",
  }
  ```
- **Caveats:** unofficial/undocumented internal API, no SLA, can rate-limit or block a UA. Treat it
  as best-effort; degrade to `None` on any failure (never raise out of ingestion). Confirmed working
  pattern is the open-source `finance_calendars` wrapper.

Because it's per-date, get a ticker's next earnings by fetching the calendar for the next N days
**once per run** and building a `{symbol: nearest_future_date}` map — same per-run memo pattern as
the benchmark returns in `pr_45`. Do NOT fetch per-ticker per-day (that's N×days requests and will
get you blocked).

## Solution — three parts (do Part 2 regardless; it's the actual bug)

### Part 1 — Nasdaq earnings provider (data source)

New module `src/providers/market_data/nasdaq_earnings.py` (or under a calendar package):

```python
class NasdaqEarningsCalendar:
    """Free Nasdaq earnings calendar, per-run cached by date-range.

    Fetches api.nasdaq.com/api/calendar/earnings?date=... for each of the next
    `horizon_days` sessions once, builds {symbol: nearest_future_earnings_date},
    and answers next_earnings_date(ticker) from that map. Degrades to None on
    any HTTP/parse failure.
    """
    _HEADERS = { ... browser headers above ... }

    def __init__(self, *, horizon_days: int = 45, client=None, row_fetcher=None):
        self._horizon_days = horizon_days
        self._client = client            # httpx.Client, injectable for tests
        self._row_fetcher = row_fetcher  # inject fake rows in tests, skip network
        self._map: dict[str, date] | None = None
        self._built_for: date | None = None

    def next_earnings_date(self, ticker: str, as_of: date) -> date | None:
        self._ensure_map(as_of)
        return (self._map or {}).get(ticker.upper())

    def _ensure_map(self, as_of: date) -> None:
        if self._map is not None and self._built_for == as_of:
            return
        mapping: dict[str, date] = {}
        for offset in range(self._horizon_days + 1):
            day = as_of + timedelta(days=offset)
            for row in self._fetch_rows(day):   # data.rows for that date
                sym = str(row.get("symbol") or "").upper()
                if sym and sym not in mapping:   # first hit = nearest future date
                    mapping[sym] = day
        self._map, self._built_for = mapping, as_of
```

Notes:
- Skip weekends to cut requests (Nasdaq returns empty rows Sat/Sun anyway; optional).
- Wrap the per-day fetch in try/except → empty list on failure so one bad day doesn't kill the map.
- 45 sessions ≈ covers a quarter's worth of "next earnings" for most names. Tune `horizon_days`.
- Keep it independent of the resilience policy or wrap the whole map-build in one policy call — but
  since it's one-per-run and market-wide, a simple internal try/except is fine.

### Part 2 — Fix the wiring: emit an events_news earnings record (THE BUG FIX)

The `events_news` family must actually receive an earnings event so
`build_event_news_signals` (`event_news.py:79-84`) can populate `earnings_in_days`,
`known_event_date`, and `own_earnings_event_type`.

In `SourceIngestionService` (`source_ingestion.py`), add an earnings event to the events_news
refresh. Inject the calendar provider (default-on, like other providers):

- Constructor: add `earnings_calendar: NasdaqEarningsCalendar | None = None` and store it (default
  to a `NasdaqEarningsCalendar()` instance; `None`-safe).
- In `_refresh_events_news` (`source_ingestion.py:394…`), after building news items, if a next
  earnings date is known, append a synthetic events_news `SourceRecord`:

```python
    earnings_date = None
    if self.earnings_calendar is not None:
        earnings_date = self.earnings_calendar.next_earnings_date(ticker, as_of.date())
    if earnings_date is not None:
        earnings_in_days = (earnings_date - as_of.date()).days
        if earnings_in_days >= 0:
            records.append(SourceRecord(
                ticker=ticker,
                source_family="events_news",
                source=self.provider_name,
                source_table="earnings_calendar",
                source_record_id=f"earnings:{ticker}:{earnings_date.isoformat()}",
                event_time=as_of,
                published_at=as_of,
                ingested_at=as_of,
                available_for_decision_at=as_of,
                payload={
                    "event_type": "own_earnings_upcoming",  # satisfies event_news.py:83
                    "earnings_in_days": earnings_in_days,
                    "known_event_date": earnings_date.isoformat(),
                    "importance": "high",
                },
            ))
```

This single record clears `events_news.earnings_in_days`, `events_news.known_event_date`,
`events_news.own_earnings_event_type` from the missing list AND restores the earnings-proximity risk
gate (`preopen_risk`/`lookahead_risk` read this exact field).

Confirm the exact list/return shape of `_refresh_events_news` before appending (it returns an
`_EventsNewsRefreshResult` with `items`; make sure the synthetic record is persisted the same way
the news records are — via the source repository, and counted in the summary if needed).

### Part 3 — Keep the fundamental earnings_date consistent + retire Finnhub earnings

- The macro calendar and `preopen_risk` date fallback still read the **fundamental** earnings_date
  (`preopen_risk.py:357-358`). Route the **same Nasdaq date** into the fundamental payload so both
  families agree. Cleanest: in `_refresh_fundamental`, overwrite/patch `earnings_date` /
  `known_event_date` / `earnings_in_days` from `self.earnings_calendar.next_earnings_date(...)` when
  available, instead of relying on the Finnhub value in `fetch_context`.
- Once Nasdaq is the source of truth, `_fetch_earnings_in_days_from_finnhub`
  (`alpaca_provider.py:417-454`) and its call at :243 can be removed (or left as a fallback). Confirm
  nothing else depends on the Finnhub earnings path before deleting.

## Reconcile with pr_44 (yfinance)

`pr_44_yfinance_fundamentals_backfill.md` also proposed pulling earnings dates from
`yfinance.Ticker.calendar`. **Nasdaq is now the earnings source of truth — drop the earnings piece
from the pr_44 yfinance work** (yfinance still owns the fundamental *ratios*: EV/Sales, FCF margin,
short interest, P/E, P/S). Avoid building two overlapping earnings paths. A cross-reference note has
been added to pr_44.

## Watch out for (don't regress the existing dedup bug)

`today_realdata_bugs_handoff.md` documents an "Upcoming Earnings listed twice / OTHER RISK ACTIONS
repeated 15×" dedup problem in the macro calendar presenter. Emitting a new per-run earnings event
each preopen/intraday run could feed that same append-only store. Use a **stable
`source_record_id`** keyed by `(ticker, earnings_date)` (as above) so re-runs upsert rather than
accumulate, and verify the macro-calendar dedup fix (that handoff) is in place or coordinate with it.

## Tests

- `NasdaqEarningsCalendar`: inject a fake `row_fetcher` returning known rows across several dates;
  assert `next_earnings_date` returns the nearest future date, is `None` for unknown symbols, caches
  per `as_of` (fetcher called once per run), and degrades to `None` when the fetcher raises.
- Ingestion: inject a fake calendar into `SourceIngestionService`; assert `_refresh_events_news`
  emits an events_news record with `earnings_in_days`/`known_event_date`/`event_type=own_earnings_*`,
  and that `build_event_news_signals` over the resulting records yields non-None
  `earnings_in_days`/`known_event_date`/`own_earnings_event_type` with `missing` excluding them.
- Risk: with the earnings event present and `earnings_in_days <= 5`, assert the preopen/lookahead
  earnings gate fires (it currently can't).
- Manual (needs network): hit the Nasdaq endpoint with the headers for a couple of dates, confirm
  200 + `data.rows`, and that MRVL/AMAT/CRDO get a next-earnings date; confirm the two
  `events_news.*` missing bullets disappear in the UI.

## Definition of done

- `events_news.earnings_in_days`, `events_news.known_event_date`, `events_news.own_earnings_event_type`
  populate for tickers with an upcoming earnings date → drop off the missing-signal list.
- Earnings-proximity risk gate (`preopen_risk`/`lookahead_risk`) fires from calendar data again.
- Earnings dates come from Nasdaq (per-run map, browser headers, graceful degradation); Finnhub
  earnings path retired or demoted to fallback.
- Fundamental and events_news families report the same earnings date; no new macro-calendar dup.
- pr_44's yfinance earnings piece removed (Nasdaq owns earnings).

## Relationship to the other handoffs

- `pr_44_yfinance_fundamentals_backfill.md` — fundamental ratios (earnings piece superseded here).
- `pr_45_technical_relative_strength_gap.md` — technical RS / premarket gap.
- `pr_46_insider_no_activity_vs_unfetched.md` — insider sparse-vs-unfetched.
- Capability markers (`option_chain_availability`, etc.) remain intentional always-missing.
