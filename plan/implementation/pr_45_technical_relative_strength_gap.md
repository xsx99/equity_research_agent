# Handoff — Populate technical `rs_vs_spy_1d` / `rs_vs_qqq_1d` / `premarket_gap_pct`

**Investigation done → implementation handoff.** Root cause confirmed in code (file:line below).
Nothing applied. Line numbers approximate — reconfirm before editing.

## Context / problem

The Today dashboard shows these three technical signals as "Missing signal:" on essentially every
ticker (AMAT, CRDO screenshots):

- `technical.rs_vs_spy_1d`
- `technical.rs_vs_qqq_1d`
- `technical.premarket_gap_pct`

**Confirmed root cause:** the *builder* already knows how to produce all three, but the *collector*
never puts the required inputs into the source record payload.

- Builder `src/trading/signals/technical.py:89-93`:
  - `premarket_gap_pct` = `record.payload.get("premarket_gap_pct")` — read straight from payload.
  - `rs_vs_spy_1d` / `rs_vs_qqq_1d` = `compute_relative_strength(return_1d, benchmark_returns.get("SPY"|"QQQ"))`
    where `benchmark_returns = record.payload.get("benchmark_returns") or {}` (:91).
  - `compute_relative_strength` (technical.py:44-50) already exists and just needs both returns.
- Collector `src/trading/signals/source_ingestion.py:300-311` (`_refresh_technical`) writes
  **only** `payload={"bars": normalized_bars}`. It never sets `benchmark_returns` or
  `premarket_gap_pct`. So both `.get(...)` calls return `None` → all three land in
  `REQUIRED_TECHNICAL_FIELDS` missing (`technical.py:11-34, 94`).

These are all computed off the same `technical` source family fetched in the pre-open pipeline
(`src/trading/workflows/signal_snapshot.py:73` requests `technical`). The provider is
`AlpacaMarketDataProvider` (`src/trading/runtime/preopen_dependencies.py:140,147`).

This splits into two tasks of very different difficulty. **Do Task A first — it's the easy,
high-confidence win.** Task B needs a premarket data source and is lower confidence.

---

## Task A — benchmark relative strength (`rs_vs_spy_1d`, `rs_vs_qqq_1d`) — EASY

The builder wiring already exists (technical.py:91-93). All that's missing is
`payload["benchmark_returns"] = {"SPY": <1d>, "QQQ": <1d>}`.

**Unit consistency (critical):** the ticker's `return_1d` is `_return_over(closes, 1)` =
`(closes[-1] - closes[-2]) / closes[-2]` (technical.py:63,104-110). Benchmark 1d returns MUST be
computed the **same way** off daily closes so the subtraction in `compute_relative_strength` is
apples-to-apples. Do NOT mix in an intraday/percent value here.

### Implementation (`src/trading/signals/source_ingestion.py`)

Benchmark bars are identical for every ticker in a run, so fetch once and memoize — don't refetch
SPY/QQQ per ticker (that would be N× wasted calls).

1. Add a small memo on the service. In `__init__` (around :98-108):

```python
        self._benchmark_returns_cache: dict[str, dict[str, float]] = {}
```

2. Add a helper that computes SPY/QQQ 1d returns once per `as_of`, through the resilience policy:

```python
    _BENCHMARK_SYMBOLS = ("SPY", "QQQ")

    def _benchmark_returns_1d(
        self, as_of: datetime, policy: ProviderResiliencePolicy
    ) -> dict[str, float]:
        cache_key = as_of.date().isoformat()
        cached = self._benchmark_returns_cache.get(cache_key)
        if cached is not None:
            return cached
        returns: dict[str, float] = {}
        for symbol in self._BENCHMARK_SYMBOLS:
            bars = policy.execute(
                symbol,
                lambda symbol=symbol: self.market_provider.fetch_daily_bars(
                    symbol, lookback_days=5
                ),
            )
            if not isinstance(bars, list):
                continue
            closes = [
                float(bar["close"])
                for bar in bars
                if isinstance(bar, dict) and isinstance(bar.get("close"), (int, float))
            ]
            if len(closes) >= 2 and closes[-2] != 0:
                returns[symbol] = (closes[-1] - closes[-2]) / closes[-2]
        self._benchmark_returns_cache[cache_key] = returns
        return returns
```

3. In `_refresh_technical` (:284-311), attach the benchmark returns to the payload:

```python
        benchmark_returns = self._benchmark_returns_1d(as_of, policy)
        return SourceRecord(
            ...
            payload={"bars": normalized_bars, "benchmark_returns": benchmark_returns},
        )
```

Reuse the same `policy` passed into `_refresh_technical` (endpoint/telemetry already scoped to the
technical family). Confirm the exact policy variable name at the call site before wiring.

### Caveats for Task A

- **Point-in-time / replay:** `fetch_daily_bars` fetches up to "now". Fine for the live pre-open
  pipeline (`as_of ≈ now`). If this ever runs under historical replay, benchmark returns would be
  as-of-now, not as-of the replay date. Out of scope here; note it if replay gets wired
  (see memory: replay is a later A3-ii task). The `as_of.date()` cache key at least keys correctly.
- The memo persists on the long-lived service instance; keying by date is enough for a daily run.
  If the service outlives a day, the date key still refreshes correctly.

Task A alone clears two of the three missing signals for every ticker.

---

## Task B — `premarket_gap_pct` — HARDER, LOWER CONFIDENCE (verify with real Alpaca data)

`premarket_gap_pct` = how far the pre-market price has gapped from the prior regular-session close:
`(premarket_price - prior_close) / prior_close`.

**Why it's harder:** daily bars alone cannot express it — you need an intraday/pre-market price.
The existing `fetch_price_at_or_before` (`alpaca_provider.py:184-222`) deliberately starts its 1Min
window at **regular** session open (`REGULAR_MARKET_OPEN` 09:30, :187-191), so it EXCLUDES the
pre-market session and can't be reused as-is.

**Data source:** Alpaca `/v2/stocks/bars` with `timeframe=1Min` over the pre-market window
(04:00–09:30 ET today) returns extended-hours bars. Caveats to verify against the live account:
- The free **IEX** feed (`feed=iex`, as used at :201) has sparse/patchy pre-market coverage; some
  symbols will have no pre-market bar → gap legitimately `None`. Confirm coverage on real tickers.
- `premarket_gap_pct` is only meaningful **during the pre-open window**. Intraday/post-close it is
  stale or undefined — see "missing-flag nuance" below.

### Recommended implementation

1. **New provider method** on `AlpacaMarketDataProvider` (near `fetch_price_at_or_before`,
   :184). Returns the latest pre-market trade/bar price for today, or `None`:

```python
    def fetch_premarket_price(self, ticker: str, as_of: datetime) -> Optional[float]:
        symbol = ticker.upper()
        cutoff = _normalized_now(as_of)
        session_day = cutoff.astimezone(MARKET_TIMEZONE).date()
        premarket_open = datetime.combine(
            session_day, time(4, 0), tzinfo=MARKET_TIMEZONE
        ).astimezone(timezone.utc)
        response = self._client.get(
            f"{self.data_base_url}/v2/stocks/bars",
            params={
                "symbols": symbol,
                "timeframe": "1Min",
                "start": premarket_open.isoformat(),
                "end": cutoff.isoformat(),
                "sort": "asc",
                "adjustment": "split",
                "feed": "iex",
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        bars_payload = payload.get("bars", {})
        bars = bars_payload.get(symbol, []) if isinstance(bars_payload, dict) else (
            bars_payload if isinstance(bars_payload, list) else []
        )
        latest_price: Optional[float] = None
        for item in sorted(bars, key=lambda bar: str(bar.get("t", ""))):
            bar_time = _parse_bar_timestamp(item.get("t"))
            close_raw = item.get("c")
            if bar_time is None or close_raw is None or bar_time > cutoff:
                continue
            latest_price = float(close_raw)
        return latest_price
```

   (Consider refactoring the shared bar-parsing loop out of `fetch_price_at_or_before` to avoid
   duplication — optional cleanup.) Also add `fetch_premarket_price` to the `MarketDataProvider`
   Protocol in `src/providers/market_data/types.py:74-96` if you want it type-visible; it's a new
   optional capability so guard the call with `getattr`/`hasattr` in the ingestion service to keep
   non-Alpaca providers working.

2. **Prior close** is already available in `_refresh_technical`: it's `normalized_bars[-1]["close"]`
   from the daily bars (the last completed regular-session close). Use that as the denominator.

3. **Compute in `_refresh_technical`** and add to payload:

```python
        prior_close = None
        last_bar = normalized_bars[-1] if normalized_bars else None
        if isinstance(last_bar, dict) and isinstance(last_bar.get("close"), (int, float)):
            prior_close = float(last_bar["close"])
        premarket_gap_pct = None
        premarket_fetch = getattr(self.market_provider, "fetch_premarket_price", None)
        if premarket_fetch is not None and prior_close not in (None, 0):
            premarket_price = policy.execute(ticker, lambda: premarket_fetch(ticker, as_of))
            if isinstance(premarket_price, (int, float)):
                premarket_gap_pct = (premarket_price - prior_close) / prior_close
        # ...add "premarket_gap_pct": premarket_gap_pct to the payload dict
```

   Note the daily bars are ascending (protocol contract, types.py:77), so `[-1]` is the most recent
   completed session — but if `as_of` is mid-session the last daily bar could be *today's* partial
   bar depending on Alpaca aggregation. **Verify** the last daily bar is the *prior* close during
   the pre-open window (before 09:30 the last completed daily bar should be yesterday). If Alpaca
   returns a forming daily bar, use `normalized_bars[-2]` or filter by date < today.

### Missing-flag nuance (design decision for reviewer)

`premarket_gap_pct` is only defined in the pre-open window. Intraday and post-close it will be
`None` and therefore always reported "missing" — a false alarm. Options (pick one, out of scope to
force here):
- (a) Accept it — it's genuinely absent outside pre-open.
- (b) Make missing-detection phase-aware so `premarket_gap_pct` is only "required" during the
  pre-open phase. That logic would live near where `REQUIRED_TECHNICAL_FIELDS` is evaluated
  (`technical.py:94`) or in the snapshot assembly (`src/trading/signals/snapshots.py:66-75`).

Flag this to the owner; don't silently change the required-set semantics.

---

## Tests

- **Task A:** unit-test `build_technical_signals` already covers the RS path when
  `benchmark_returns` is present — add/confirm a case. For the ingestion service, inject a fake
  `market_provider` whose `fetch_daily_bars` returns known SPY/QQQ closes and assert the technical
  `SourceRecord.payload["benchmark_returns"]` has the expected 1d values, and that a second ticker
  in the same run reuses the cache (provider called once per benchmark).
- **Task B:** inject a fake provider exposing `fetch_premarket_price` returning a known price;
  assert `payload["premarket_gap_pct"] == (premarket - prior_close)/prior_close`. Add a `None`-price
  case → gap `None`, no exception. Add a case where the provider lacks the method (getattr guard) →
  gap `None`.
- **Manual (needs live Alpaca, do at implement time):** run the pre-open technical refresh for
  MRVL/AMAT/CRDO and confirm `rs_vs_spy_1d`/`rs_vs_qqq_1d` are non-null, and `premarket_gap_pct` is
  non-null for names that have IEX pre-market prints.

## Definition of done

- `_refresh_technical` writes `benchmark_returns` (SPY, QQQ 1d) → `rs_vs_spy_1d`/`rs_vs_qqq_1d`
  populated for every ticker; benchmark bars fetched once per run, not per ticker.
- `premarket_gap_pct` populated during the pre-open window for tickers with pre-market data;
  degrades to `None` (no exception) when the provider can't supply a pre-market price.
- Unit conversions match the ticker's daily `return_1d` semantics (fractional daily return).
- The `premarket_gap_pct` missing-flag-outside-preopen nuance is raised with the owner.

## Relationship to the other handoff

The fundamental-family missing signals (`ev_sales_percentile`, `fcf_margin_score`,
`short_interest_bucket`, `valuation_percentile`) are a separate data-source task — see
`pr_44_yfinance_fundamentals_backfill.md`. The capability markers
(`option_chain_availability`, `full_transcript_interpretation`, `macro_sector_readthrough`) and the
`insider.*` family are still out of scope for both handoffs.
