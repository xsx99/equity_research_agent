# Handoff — Add a forward-looking macro/economic event calendar (FMP) into preopen risk

**Investigation done → implementation handoff.** Current state confirmed in code (file:line below).
Nothing applied. Line numbers approximate — reconfirm before editing.

## TL;DR

The system has **no forward-looking economic calendar** (CPI / FOMC / nonfarm payrolls / PPI / GDP).
The consumer plumbing already exists — `CalendarEventPipeline.build_events(macro_events=...)` — but
nothing feeds it a scheduled calendar, and **preopen feeds zero macro events**. Add a **Financial
Modeling Prep (FMP) economic-calendar provider** (owner decision) and wire its events into the
preopen calendar build.

**Source decision:** MarketWatch (`marketwatch.com/economy-politics/calendar`) was requested but is
NOT viable programmatically — no public JSON API, HTML behind Akamai bot protection (not even
fetchable from this environment, worse from a datacenter IP), and scraping violates Dow Jones ToS.
Owner chose **FMP economic calendar** instead. Do not scrape MarketWatch.

## Current state (confirmed)

- `CalendarEventPipeline.build_events` already accepts and normalizes macro events: a `macro_events`
  tuple of dicts → `event_type="macro"` `CalendarEventRecord`s
  (`src/trading/events/calendar.py:111-129`). Expected dict shape (from that loop):
  - `event_time` (datetime, **required**), `event_code` (**required**), `title` (**required**),
    `severity_hint` (optional, default "medium"), `source` (optional, default "macro_calendar").
  - `event_key = f"macro:{event_code}:{event_time.date()}"` (:114) — stable, used for dedup (:147).
- **Preopen feeds NO macro events** — `_build_preopen_calendar_events`
  (`src/trading/runtime/preopen_risk.py:286-306`) calls `build_events` with earnings only (:299-304).
- The only macro events today are **reactive intraday news items**: `intraday_refresh_helpers.py:388-397`
  turns non-ticker `social_macro` news into macro events with `event_time = news published_at`. That
  is "a macro headline was published", NOT a scheduled "CPI releases on the 10th". No release
  schedule exists anywhere.
- `macro_sector_readthrough` remains an unrelated always-missing capability marker
  (`src/trading/signals/snapshots.py:74`); out of scope.

So this is a **missing data source + one wiring point**, not a broken pipeline.

## The FMP economic calendar (source spec)

- Endpoint (legacy v3, widely used): `GET https://financialmodelingprep.com/api/v3/economic_calendar?from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=<KEY>`
  (stable equivalent: `.../stable/economics-calendar`). Returns a flat JSON list.
- Per-event fields: `date`, `country`, `event`, `currency`, `previous`, `estimate`, `actual`,
  `change`, `changePercentage`, `impact`.
- `impact` values: `"Low"` / `"Medium"` / `"High"` (also `"None"`/holidays). Map to `severity_hint`:
  `High→high`, `Medium→medium`, `Low→low` (default `medium` if absent).
- **`date` is UTC** (e.g. `"2026-07-10 12:30:00"`) — parse as UTC → tz-aware datetime for `event_time`.
- Calendar refreshes ~every 15 min upstream.
- **Free tier: VERIFY.** FMP has been tightening free-tier access. Confirm `economic_calendar`
  returns data with a free key before building on it; if it's gated, fall back to the FRED
  release-dates route (owner's #2 choice) — note this in the PR if you hit a 402/403.

Filter to US macro: keep rows where `country in {"US", "United States"}` OR `currency == "USD"`
(FMP's `country` labeling has varied — verify against a live response and pick the robust predicate).

## Implementation

### 1. Config — FMP API key

Add `FMP_API_KEY` env resolution (mirror how `FINNHUB_API_KEY` is read in
`src/providers/market_data/alpaca_provider.py:46` / config). Document it alongside other provider
keys. Provider must no-op (empty calendar) when the key is unset.

### 2. New provider — `src/providers/market_data/fmp_economic_calendar.py`

Per-run window fetch + memo (same pattern as the benchmark memo in `pr_45` and the Nasdaq map in
`pr_47`): fetch the next `horizon_days` once, return normalized macro-event dicts ready for
`build_events`.

```python
class FMPEconomicCalendar:
    """Free FMP economic calendar → forward macro events for CalendarEventPipeline.

    Fetches api/v3/economic_calendar?from=&to= once per run, filters to US
    high-signal events, and returns dicts shaped for build_events(macro_events=...).
    Degrades to [] on missing key / HTTP / parse failure (never raises).
    """
    def __init__(self, *, api_key=None, horizon_days=14, client=None, row_fetcher=None):
        self._api_key = api_key or os.getenv("FMP_API_KEY")
        self._horizon_days = horizon_days
        self._client = client
        self._row_fetcher = row_fetcher     # inject fake rows in tests, skip network
        self._events: list[dict] | None = None
        self._built_for: date | None = None

    def macro_events(self, as_of: date) -> tuple[dict, ...]:
        if self._events is not None and self._built_for == as_of:
            return tuple(self._events)
        events: list[dict] = []
        if self._api_key or self._row_fetcher is not None:
            rows = self._fetch_rows(as_of, as_of + timedelta(days=self._horizon_days))
            for row in rows:
                if not self._is_us(row):
                    continue
                impact = str(row.get("impact") or "").lower()
                if impact not in ("high", "medium"):   # drop Low/None noise; tune as desired
                    continue
                event_time = self._parse_utc(row.get("date"))
                name = str(row.get("event") or "").strip()
                if event_time is None or not name:
                    continue
                events.append({
                    "event_code": self._slug(name),           # e.g. "cpi", "fomc_rate_decision"
                    "event_time": event_time,                 # tz-aware UTC
                    "title": name,
                    "severity_hint": {"high": "high", "medium": "medium"}[impact],
                    "source": "fmp_economic_calendar",
                })
        self._events, self._built_for = events, as_of
        return tuple(events)
    # _fetch_rows (httpx GET, apikey), _is_us, _parse_utc, _slug helpers; all try/except → safe defaults
```

- `_slug(name)`: lowercase, non-alnum→`_`, collapse — gives a stable `event_code` so
  `event_key = macro:{code}:{date}` is stable across runs (important for dedup/upsert). Keep raw
  name in `title`.
- Drop `Low`/`None`/holiday impact to avoid flooding the risk view; keep High+Medium. Tunable.

### 3. Wire into preopen — `src/trading/runtime/preopen_risk.py`

Macro events are **market-wide (ticker-agnostic)** — do NOT append them per-candidate or they
multiply by the candidate count. Build them **once per run** and add to the events list once.

In `_build_preopen_calendar_events` (:286-306): after the per-candidate loop, if an economic-calendar
provider is available, make a single `build_events` call for the macro events and extend once:

```python
    if economic_calendar is not None:
        macro_events = economic_calendar.macro_events(decision_time.date())
        if macro_events:
            events.extend(
                calendar_event_pipeline.build_events(
                    ticker="MARKET",                 # macro records carry ticker=None regardless
                    decision_time=decision_time,
                    macro_events=macro_events,
                )
            )
```

(`build_events` with only `macro_events` set runs just the macro loop; the `"MARKET"` ticker is
ignored for macro records — verify: macro branch sets `ticker=None` at calendar.py:120.)

Thread the provider in: construct `FMPEconomicCalendar()` in the runtime deps
(`src/trading/runtime/preopen_dependencies.py`, near the other providers ~:140) and pass it down to
whatever invokes `_build_preopen_calendar_events`. Confirm the exact call chain / signature before
wiring.

### 4. (Optional) intraday reuse

The intraday path (`intraday_refresh_helpers.py:408-417`) already builds `macro_events` from news.
You can also feed the scheduled `economic_calendar.macro_events(...)` there so intraday sees upcoming
releases too — additive, same dedup keys prevent collisions. Not required for the core fix.

## Dedup / don't regress the known macro-calendar bug

`today_realdata_bugs_handoff.md` documents an append-only macro-calendar store that duplicates rows
(earnings listed twice, risk actions repeated 15×). Because `event_key = macro:{code}:{date}` is
stable (calendar.py:114) and `save_calendar_events` should upsert by `event_key`, re-running preopen
must NOT create duplicate macro rows — verify `save_calendar_events`
(`src/trading/repositories/mixins/macro_calendar.py:64`) upserts on `event_key`, and coordinate with
that dedup handoff. A stable `event_code` slug is what makes this work — don't derive it from
timestamps.

## Tests

- `FMPEconomicCalendar`: inject `row_fetcher` with fixed rows spanning several dates/impacts/countries;
  assert US High+Medium kept, Low/None and non-US dropped, `event_time` parsed as tz-aware UTC,
  `event_code` slug stable, memo built once per `as_of`, and `[]` (no raise) when key unset or fetch
  throws.
- `CalendarEventPipeline.build_events` with those macro dicts → `event_type="macro"`, `ticker=None`,
  stable `event_key`, correct `severity_hint`.
- Preopen: with a fake calendar returning 2 events and 3 candidates, assert macro events appear
  **once each** (not ×3) in the assembled events.
- Manual (needs FMP key): hit `economic_calendar?from=&to=&apikey=`, confirm 200 + US CPI/FOMC/NFP
  rows for the window, and that they surface in the Risk & Macro view with correct severity.

## Definition of done

- A free-tier FMP economic calendar provider returns forward US macro events (High/Medium),
  degrading to `[]` when the key is missing or the request fails.
- Preopen risk assembles scheduled macro events **once per run** (no per-candidate duplication),
  feeding the existing `build_events(macro_events=...)` path.
- Macro rows upsert by stable `event_key` (no regression of the macro-calendar duplication bug).
- MarketWatch is NOT scraped. If FMP's free tier turns out to gate the endpoint, fall back to the
  FRED release-dates route and note it.

## Relationship to the other handoffs

- `pr_44` fundamental ratios (yfinance) · `pr_45` technical RS/gap · `pr_46` insider sparse-vs-unfetched
  · `pr_47` earnings calendar (Nasdaq) + earnings wiring fix.
- This doc adds the **macro/economic** calendar — distinct from `pr_47`'s **company earnings**
  calendar. `pr_47`'s macro-calendar dedup caveat and this one are the same store; coordinate.
- Note the growing key surface: `FINNHUB_API_KEY` (existing), `FMP_API_KEY` (this), plus Nasdaq
  (headers, keyless, pr_47). Document all provider credentials in one place.
