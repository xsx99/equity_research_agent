# Provider Availability Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the deterministic FRED gold-series 404 noise and cut avoidable duplicate Finnhub traffic during pre-open runs without redesigning the broader provider-resilience stack.

**Architecture:** Keep the fix surgical. Stop querying the removed FRED gold series and build `gold_price` directly from the existing GLD proxy path; add per-provider-instance caching for `AlpacaMarketDataProvider.fetch_context()` so the targeted-universe stage and the signal-ingestion stage reuse the same Finnhub payloads within one runtime. Do not change DB schema, scheduler wiring, or the public trading runtime contract in this PR.

**Tech Stack:** Python 3.13, `httpx`, `pytest`, FRED, Finnhub, Alpaca

---

## Required reading before coding

1. `documents/general_instructions.md`
2. `plan/research_app/trading_agent_refactor/module_contracts.md`
3. `plan/research_app/trading_agent_refactor/implementation/reading_guide.md`
4. This file
5. `plan/research_app/trading_agent_refactor/progress_tracker.md`

## Verified context and constraints

- `FRED_API_KEY` is not configured in the current local runtime environment, so `FredMacroDataProvider` falls back to `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series_id>`.
- The configured gold series `GOLDAMGBD228NLBM` is no longer available from FRED. The direct series URL now redirects to the St. Louis Fed announcement about IBA data removal: `https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/`.
- Current gold handling is in:
  - `src/providers/global_context/types.py`
  - `src/providers/global_context/fred_provider.py`
- Current Finnhub request fan-out is structural, not random:
  - `src/trading/data_sources/live_universe.py` calls `market_provider.fetch_context(symbol)` when building targeted assets.
  - `src/trading/signals/source_ingestion.py` calls `market_provider.fetch_context(ticker)` again when refreshing the `fundamental` source family.
  - `src/providers/market_data/alpaca_provider.py::fetch_context()` makes three Finnhub HTTP requests per ticker when `FINNHUB_API_KEY` is set: `stock/profile2`, `stock/metric`, and `calendar/earnings`.
  - `src/providers/news_data/finnhub.py` adds a separate `company-news` request per ticker when Finnhub is the active news provider.
- For the observed 17-ticker pre-open run, the current request volume is approximately:
  - `17 * 3 = 51` Finnhub requests for targeted-universe `fetch_context()`
  - `17 * 3 = 51` Finnhub requests for signal-ingestion `fetch_context()`
  - `17 * 1 = 17` Finnhub requests for company news
  - Total: about `119` Finnhub requests in one run
- `ProviderResiliencePolicy` only wraps the outer `fetch_context()` operation. It does not currently meter the three internal Finnhub HTTP calls individually. Do **not** redesign that in this PR.

## Non-goals

- Do not add or change Alembic migrations.
- Do not redesign `ProviderResiliencePolicy` into a cross-endpoint/shared-quota system.
- Do not switch the news provider away from Finnhub.
- Do not change the `/today` UI contract or runtime JSON schema.
- Do not change scheduler phase names, CLI flags, or execution modes.

### Task 1: Bypass the removed FRED gold series

**Files:**
- Modify: `src/providers/global_context/fred_provider.py`
- Test: `tests/tools/test_fred_provider.py`

- [ ] **Step 1: Write the failing regression test**

Add a new test to `tests/tools/test_fred_provider.py`:

```python
def test_fetch_indicators_uses_gld_proxy_for_gold_without_querying_removed_fred_series():
    provider = FredMacroDataProvider(client=MagicMock())

    def _fake_latest(series_id: str, as_of: datetime):
        if series_id == "GOLDAMGBD228NLBM":
            raise AssertionError("removed_gold_series_should_not_be_queried")
        return 1.23, "2026-03-26"

    provider._fetch_latest_observation = MagicMock(side_effect=_fake_latest)
    provider._fetch_gold_proxy_from_market_data = MagicMock(return_value=(313.12, "2026-03-26"))
    provider._fetch_live_vix_from_yahoo = MagicMock(return_value=(27.44, "2026-03-26"))

    indicators = provider.fetch_indicators(datetime(2026, 3, 26, 21, 59, tzinfo=timezone.utc))

    assert indicators["gold_price"] == {
        "label": "Gold Proxy (GLD ETF)",
        "source": "ALPACA:GLD_PROXY",
        "unit": "USD/share",
        "value": 313.12,
        "observed_on": "2026-03-26",
    }
```

- [ ] **Step 2: Run the focused test to verify it fails for the expected reason**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_fred_provider.py -q -k gold_proxy
```

Expected:

- The new test fails with `AssertionError: removed_gold_series_should_not_be_queried`.
- Existing FRED tests are not modified yet.

- [ ] **Step 3: Implement the minimal production fix**

In `src/providers/global_context/fred_provider.py`, change `fetch_indicators()` so `gold_price` never calls `_fetch_latest_observation()` and instead always uses the existing GLD proxy helper.

Implementation requirements:

- Keep the indicator key as `gold_price`.
- Keep the rest of the FRED loop unchanged for oil, treasuries, credit spread, and VIX.
- For `gold_price`, initialize the indicator with proxy-facing metadata immediately:

```python
indicators[key] = _empty_indicator("Gold Proxy (GLD ETF)", "ALPACA:GLD_PROXY", "USD/share")
```

- Then call:

```python
value, observed_on = self._fetch_gold_proxy_from_market_data()
```

- Assign `value` and `observed_on`, then `continue` to the next loop iteration.
- Add a short code comment explaining that the historical FRED IBA gold series was removed upstream, so this path now intentionally avoids the dead series instead of logging a guaranteed 404 every run.
- Do **not** modify the VIX live-fallback behavior.
- Do **not** delete `_fetch_gold_proxy_from_market_data()`; reuse it exactly.

- [ ] **Step 4: Re-run the focused test and then the full FRED provider test file**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_fred_provider.py -q -k gold_proxy
source ~/.venv/bin/activate && pytest tests/tools/test_fred_provider.py -q
```

Expected:

- The focused gold test passes.
- The full file passes with no regressions to VIX behavior.

- [ ] **Step 5: Commit the isolated gold fix**

```bash
git add tests/tools/test_fred_provider.py src/providers/global_context/fred_provider.py
git commit -m "fix: stop querying removed FRED gold series"
```

### Task 2: Cache Finnhub-backed `fetch_context()` results per provider instance

**Files:**
- Modify: `src/providers/market_data/alpaca_provider.py`
- Test: `tests/tools/test_market_data.py`

- [ ] **Step 1: Write the failing regression test**

Add a new test near the existing `fetch_context` coverage in `tests/tools/test_market_data.py`:

```python
def test_fetch_context_caches_finnhub_payloads_per_ticker():
    client = _RoutingClient(
        {
            "stock/profile2": {
                "name": "Apple Inc.",
                "finnhubIndustry": "Technology",
                "marketCapitalization": 3000000,
            },
            "stock/metric": {
                "metric": {
                    "revenueGrowthTTMYoy": 18.0,
                    "operatingMarginTTM": 31.0,
                    "roeTTM": 145.0,
                    "evSalesTTM": 7.5,
                    "freeCashFlowMarginTTM": 24.0,
                    "shortPercentOfFloat": 1.2,
                    "peTTM": 29.0,
                    "psTTM": 7.0,
                }
            },
            "calendar/earnings": {
                "earningsCalendar": [
                    {"date": "2026-07-10"},
                ]
            },
        }
    )
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        finnhub_api_key="finnhub-key",
        client=client,
    )

    first = provider.fetch_context("AAPL")
    second = provider.fetch_context("aapl")

    assert first == second
    assert len(client.calls) == 3

    first["company_name"] = "mutated"
    third = provider.fetch_context("AAPL")

    assert third["company_name"] == "Apple Inc."
    assert len(client.calls) == 3
```

Why this exact test:

- `len(client.calls) == 3` proves the second and third lookups reused cached Finnhub data instead of firing another `profile2 + metric + calendar` triplet.
- The post-mutation assertion forces the implementation to return a shallow copy of the cached dict instead of exposing the mutable cached object directly.

- [ ] **Step 2: Run the focused test to verify it fails before implementation**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py -q -k caches_finnhub_payloads
```

Expected:

- The new test fails because the current implementation makes 9 client calls, not 3.

- [ ] **Step 3: Implement the minimal cache in `AlpacaMarketDataProvider`**

In `src/providers/market_data/alpaca_provider.py`:

1. Add a provider-instance cache in `__init__`:

```python
self._context_cache: dict[str, dict[str, Any]] = {}
```

2. In `fetch_context()`:

- Normalize the symbol once at the top:

```python
symbol = ticker.upper()
```

- Before any Finnhub work, check the cache:

```python
cached = self._context_cache.get(symbol)
if cached is not None:
    return dict(cached)
```

- Use `symbol` for all downstream Finnhub calls in this method.
- Build the final flat context dict once, assign it to a local variable such as `context_payload`, then cache a copy:

```python
self._context_cache[symbol] = dict(context_payload)
return dict(context_payload)
```

Implementation rules:

- Only cache successful completed results. If any Finnhub call raises, let the exception propagate and do **not** populate the cache.
- Keep the returned data shape exactly the same as today.
- Do not add TTL, locking, or cross-process cache invalidation. This cache is intentionally per-provider-instance and in-memory only.
- Do not change `_fetch_profile_from_finnhub()`, `_fetch_metrics_from_finnhub()`, or `_fetch_earnings_in_days_from_finnhub()` signatures in this PR.

- [ ] **Step 4: Re-run the focused market-data test and the existing `fetch_context` test cluster**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py -q -k caches_finnhub_payloads
source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py -q -k "fetch_context"
```

Expected:

- The focused cache test passes.
- Existing `fetch_context` tests continue to pass.

- [ ] **Step 5: Commit the isolated Finnhub cache fix**

```bash
git add tests/tools/test_market_data.py src/providers/market_data/alpaca_provider.py
git commit -m "fix: cache finnhub context lookups per provider instance"
```

### Task 3: Full verification, smoke, and handoff notes

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Optional docs note only if needed for operator clarity: `documents/research_app/runbook.md`

- [ ] **Step 1: Run the local unit-test verification set**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_fred_provider.py tests/tools/test_market_data.py -q
```

Expected:

- Full pass.
- No new warnings from the test suite.

- [ ] **Step 2: Run one live scheduler-facing smoke check**

Use the existing live pre-open command:

```bash
source ~/.venv/bin/activate && python scripts/run_trading_once.py --phase preopen --json
```

Interpretation rules:

- The run should still complete successfully.
- The logs should no longer contain `global_context_fred_series_failed` for `GOLDAMGBD228NLBM`.
- This PR does **not** guarantee zero Finnhub `429` responses in every environment, because the remaining `company-news` traffic plus real plan limits may still be tight.
- The binding regression for the Finnhub fix is the new unit test proving that repeated `fetch_context("AAPL")` only triggers one `profile2 + metric + calendar` triplet per provider instance.

- [ ] **Step 3: Update the progress tracker**

Add one new top-of-file bullet to `plan/research_app/trading_agent_refactor/progress_tracker.md` summarizing:

- the removed FRED gold-series bypass,
- the new per-provider-instance Finnhub context cache,
- the exact tests run,
- whether the live pre-open smoke still showed any residual Finnhub 429s.

Keep the wording factual. Do not claim broader provider-resilience improvements than were actually implemented.

- [ ] **Step 4: Commit the tracker update**

```bash
git add plan/research_app/trading_agent_refactor/progress_tracker.md
git commit -m "docs: record provider availability reliability fixes"
```

## Acceptance criteria

- `gold_price` no longer attempts to query the removed `GOLDAMGBD228NLBM` FRED series during normal macro fetches.
- Pre-open runs no longer emit the deterministic `global_context_fred_series_failed` warning for that removed gold series.
- Repeated `AlpacaMarketDataProvider.fetch_context()` calls for the same ticker on the same provider instance reuse the first successful Finnhub payload instead of issuing duplicate HTTP requests.
- The returned `fetch_context()` payload remains mutable by callers without corrupting the cached provider state.
- No DB schema, CLI behavior, or scheduler contract changes are introduced.

## Explicit non-acceptance cases

- Do not merge a version that adds a new global/shared rate-limit coordinator.
- Do not merge a version that changes the meaning or shape of the `gold_price` key.
- Do not merge a version that suppresses all Finnhub exceptions silently without tests.
- Do not merge a version that stores mutable cached dicts and returns the same object reference to callers.

