# Signal Ingestion Request-Budget Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure large pre-open and intraday ticker scopes cannot starve late tickers such as LITE of required daily technical data.

**Architecture:** Complete Alpaca multi-symbol daily-bar pagination, preload required ticker and benchmark daily bars once per ingestion run, and use an independently sized single-symbol fallback policy for missing or failed batch results. Split premarket and intraday enrichment into phase-aware policies whose failures remain observable but cannot discard valid daily-bar records.

**Tech Stack:** Python 3.13, httpx, existing `ProviderResiliencePolicy`, existing market-data provider protocol, pytest.

**Design:** `plan/design/2026-07-28-signal-ingestion-request-budget-isolation.md`

---

## File Responsibilities

- `src/providers/market_data/alpaca_provider.py`
  - Own Alpaca multi-symbol daily-bar HTTP pagination and normalization.
- `src/trading/signals/source_ingestion.py`
  - Own run-scoped daily-bar preload/fallback, operation-specific resilience
    policies, phase selection, technical source-record assembly, and degraded
    run error propagation.
- `tests/tools/test_market_data.py`
  - Verify multi-page Alpaca batch behavior and repeated-token protection.
- `tests/trading/test_signal_sources.py`
  - Verify large-scope technical coverage, fallback isolation, phase-aware
    calls, optional failure preservation, and run status.
- `tests/trading/test_pipeline.py`
  - Verify a late ticker receives a non-empty technical snapshot through the
    public `SignalPipeline` boundary.
- `plan/progress_tracker.md`
  - Record the completed slice and verification evidence.

No migration, database model, prompt, strategy, risk, UI, or deployment file
changes are required.

---

### Task 1: Complete Alpaca multi-symbol daily-bar pagination

**Files:**

- Modify: `tests/tools/test_market_data.py`
- Modify: `src/providers/market_data/alpaca_provider.py:114-153`

- [ ] **Step 1: Write a failing pagination test**

Add a client that returns responses in sequence and captures request params:

```python
class _SequenceClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, *, params, headers):
        self.calls.append({"url": url, "params": dict(params), "headers": headers})
        return _StubResponse(self.payloads.pop(0))
```

Add:

```python
def test_fetch_daily_bars_for_symbols_follows_page_tokens():
    client = _SequenceClient(
        [
            {
                "bars": {
                    "AAPL": [
                        {"t": "2026-03-23T04:00:00Z", "c": 200.0, "v": 10}
                    ]
                },
                "next_page_token": "page-2",
            },
            {
                "bars": {
                    "AAPL": [
                        {"t": "2026-03-24T04:00:00Z", "c": 201.0, "v": 20}
                    ],
                    "LITE": [
                        {"t": "2026-03-24T04:00:00Z", "c": 850.0, "v": 30}
                    ],
                },
                "next_page_token": None,
            },
        ]
    )
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        client=client,
    )

    result = provider.fetch_daily_bars_for_symbols(
        ["AAPL", "LITE"],
        lookback_days=2,
        batch_size=2,
    )

    assert [bar["close"] for bar in result["AAPL"]] == [200.0, 201.0]
    assert result["LITE"][0]["close"] == 850.0
    assert "page_token" not in client.calls[0]["params"]
    assert client.calls[1]["params"]["page_token"] == "page-2"
```

- [ ] **Step 2: Write a failing repeated-token test**

```python
def test_fetch_daily_bars_for_symbols_rejects_repeated_page_token():
    client = _SequenceClient(
        [
            {"bars": {}, "next_page_token": "same-token"},
            {"bars": {}, "next_page_token": "same-token"},
        ]
    )
    provider = AlpacaMarketDataProvider(
        api_key="test-key",
        secret_key="test-secret",
        client=client,
    )

    with pytest.raises(RuntimeError, match="repeated_alpaca_page_token"):
        provider.fetch_daily_bars_for_symbols(["AAPL"], lookback_days=2)
```

- [ ] **Step 3: Run the tests to verify RED**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/tools/test_market_data.py::test_fetch_daily_bars_for_symbols_follows_page_tokens tests/tools/test_market_data.py::test_fetch_daily_bars_for_symbols_rejects_repeated_page_token -q
```

Expected: both tests fail because the current method makes one request per
chunk and ignores `next_page_token`.

- [ ] **Step 4: Implement pagination**

For each symbol chunk:

```python
raw_bars_by_symbol: dict[str, list[dict[str, Any]]] = {
    symbol: [] for symbol in chunk
}
page_token: str | None = None
seen_page_tokens: set[str] = set()

while True:
    params = {
        "symbols": ",".join(chunk),
        "timeframe": "1Day",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": min(max(lookback_days * len(chunk), 2), 10_000),
        "sort": "desc",
        "adjustment": "split",
        "feed": "iex",
    }
    if page_token is not None:
        params["page_token"] = page_token
    response = self._client.get(
        f"{self.data_base_url}/v2/stocks/bars",
        params=params,
        headers=self._auth_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    page_bars = payload.get("bars", {}) if isinstance(payload, dict) else {}
    if isinstance(page_bars, dict):
        for symbol in chunk:
            rows = page_bars.get(symbol, [])
            if isinstance(rows, list):
                raw_bars_by_symbol[symbol].extend(
                    row for row in rows if isinstance(row, dict)
                )
    next_page_token = payload.get("next_page_token") if isinstance(payload, dict) else None
    if not next_page_token:
        break
    token = str(next_page_token)
    if token in seen_page_tokens:
        raise RuntimeError(f"repeated_alpaca_page_token:{token}")
    seen_page_tokens.add(token)
    page_token = token
```

Normalize accumulated rows with `_normalize_daily_bars()` and retain only the
latest `lookback_days` entries for each symbol.

- [ ] **Step 5: Run provider tests to verify GREEN**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/tools/test_market_data.py -q
```

Expected: all market-data provider tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/providers/market_data/alpaca_provider.py tests/tools/test_market_data.py
git commit -m "fix alpaca batch bars pagination"
```

---

### Task 2: Preload required daily bars with isolated fallback

**Files:**

- Modify: `tests/trading/test_signal_sources.py`
- Modify: `src/trading/signals/source_ingestion.py:70-410`

- [ ] **Step 1: Add reusable batch-provider test fixtures**

Extend the fake market provider with a batch-capable subclass:

```python
class _BatchMarketProvider(_FakeMarketProvider):
    def __init__(self, *, omitted_symbols=(), fail_batch=False):
        super().__init__()
        self.omitted_symbols = set(omitted_symbols)
        self.fail_batch = fail_batch
        self.batch_calls = []

    def fetch_daily_bars_for_symbols(self, symbols, lookback_days):
        normalized = tuple(symbols)
        self.batch_calls.append((normalized, lookback_days))
        if self.fail_batch:
            raise RuntimeError("batch_failed")
        return {
            symbol: self.fetch_daily_bars(symbol, lookback_days)
            for symbol in normalized
            if symbol not in self.omitted_symbols
        }
```

Use synthetic tickers such as `T000` through `T176` plus `LITE`; avoid external
calls.

- [ ] **Step 2: Write the late-ticker batch regression test**

```python
def test_source_ingestion_batches_large_scope_without_starving_lite():
    tickers = tuple(f"T{index:03d}" for index in range(177)) + ("LITE",)
    provider = _BatchMarketProvider()

    result = SourceIngestionService(
        market_provider=provider,
        news_provider=None,
        source_repository=InMemorySignalSourceRepository(),
        artifact_repository=InMemoryTradingRepository(),
        provider_name="fixture",
        max_requests_per_endpoint=3,
        now=lambda: NOW,
        sleeper=lambda seconds: None,
    ).refresh_tickers(
        tickers,
        as_of=NOW,
        run_type="pre_open",
        source_families=("technical",),
    )

    records = {record.ticker: record for record in result.source_records}
    assert records["LITE"].payload["bars"]
    assert len(records) == 178
    assert provider.batch_calls == [
        (tickers + ("SPY", "QQQ"), 252)
    ]
```

Adapt the expected call to the final deduplicated symbol order when SPY or QQQ
already belongs to the requested scope.

- [ ] **Step 3: Write missing-symbol and batch-failure fallback tests**

Cover both:

```python
def test_source_ingestion_falls_back_for_symbol_omitted_from_batch():
    provider = _BatchMarketProvider(omitted_symbols={"LITE"})
    ...
    assert "LITE" in records
    assert ("LITE", 252) in provider.bar_calls


def test_source_ingestion_falls_back_for_malformed_batch_symbol():
    provider = _BatchMarketProvider(batch_overrides={"LITE": [{}]})
    ...
    assert records["LITE"].payload["bars"]
    assert ("LITE", 252) in provider.bar_calls


def test_source_ingestion_batch_failure_recovers_but_marks_run_degraded():
    provider = _BatchMarketProvider(fail_batch=True)
    ...
    assert records["LITE"].payload["bars"]
    assert result.ingestion_run.status == "degraded"
    assert result.ingestion_run.error_code == "RuntimeError"
```

- [ ] **Step 4: Write fallback budget and circuit regression tests**

Use a provider without `fetch_daily_bars_for_symbols`, more tickers than the
configured limit, and three early symbols whose single loads raise:

```python
def test_daily_fallback_budget_and_circuit_do_not_starve_late_ticker():
    tickers = ("BAD1", "BAD2", "BAD3", "LITE")
    provider = _FailingEarlySingleMarketProvider()
    ...
    assert records["LITE"].payload["bars"]
    assert ("LITE", 252) in provider.bar_calls
```

Assert provider telemetry contains failures for the early symbols but not
`circuit_open` for the LITE required daily request.

- [ ] **Step 5: Run focused tests to verify RED**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/trading/test_signal_sources.py::test_source_ingestion_batches_large_scope_without_starving_lite \
  tests/trading/test_signal_sources.py::test_source_ingestion_falls_back_for_symbol_omitted_from_batch \
  tests/trading/test_signal_sources.py::test_source_ingestion_falls_back_for_malformed_batch_symbol \
  tests/trading/test_signal_sources.py::test_source_ingestion_batch_failure_recovers_but_marks_run_degraded \
  tests/trading/test_signal_sources.py::test_daily_fallback_budget_and_circuit_do_not_starve_late_ticker \
  -q
```

Expected: tests fail because `SourceIngestionService` has no batch preload and
uses one fixed shared technical policy.

- [ ] **Step 6: Add internal result types**

Near the existing refresh result dataclasses:

```python
@dataclass(frozen=True)
class _DailyBarLoadResult:
    bars_by_symbol: dict[str, list[dict[str, Any]]]
    errors: tuple[Exception, ...]


@dataclass(frozen=True)
class _TechnicalRefreshResult:
    record: SourceRecord | None
    errors: tuple[Exception, ...] = ()
```

- [ ] **Step 7: Make policy sizing explicit**

Extend `_policy()` with optional limits:

```python
def _policy(
    self,
    endpoint,
    source_family,
    recorder,
    *,
    max_requests=None,
    circuit_failure_threshold=3,
):
    return ProviderResiliencePolicy(
        ...
        max_requests=(
            self.max_requests_per_endpoint
            if max_requests is None
            else max_requests
        ),
        circuit_failure_threshold=circuit_failure_threshold,
        ...
    )
```

Define one module-level constant matching `ProviderResiliencePolicy`:

```python
_PROVIDER_MAX_ATTEMPTS_PER_SCOPE = 3
```

Use it to size policies instead of duplicating an unexplained literal.

- [ ] **Step 8: Implement run-scoped daily loading**

Add `_load_daily_bars()` that:

1. Deduplicates requested tickers plus `SPY` and `QQQ`.
2. Attempts `fetch_daily_bars_for_symbols()` through
   `market_daily_bars_batch`.
3. Normalizes each returned value by retaining only dictionaries whose `close`
   is numeric and whose `date` is a `date`/`datetime` or a non-empty parseable
   date string accepted by the existing event-time parser. A symbol is valid
   only when at least one row survives normalization. `[{}]`, missing/invalid
   closes, and missing/invalid dates are malformed, not successful batch data.
4. Records the caught batch exception and selects all symbols for fallback if
   batch loading fails.
5. Selects omitted or malformed symbols for fallback after a successful batch;
   persisted payloads use the normalized rows rather than the unvalidated batch
   rows.
6. Creates a fresh `market_daily_bars_fallback` policy sized as:

```python
max(
    self.max_requests_per_endpoint,
    len(fallback_symbols) * _PROVIDER_MAX_ATTEMPTS_PER_SCOPE,
)
```

7. Sets `circuit_failure_threshold=len(fallback_symbols) + 1`.
8. Loads each fallback symbol with `fetch_daily_bars()` and records
   symbol-level exceptions without stopping later symbols.
9. Returns `_DailyBarLoadResult`.

- [ ] **Step 9: Build benchmark returns from run-local bars**

Replace `_benchmark_returns_1d(as_of, policy)` with a pure helper:

```python
def _benchmark_returns_1d(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    returns = {}
    for symbol in ("SPY", "QQQ"):
        closes = [
            float(bar["close"])
            for bar in bars_by_symbol.get(symbol, [])
            if isinstance(bar, dict)
            and isinstance(bar.get("close"), (int, float))
        ]
        if len(closes) >= 2 and closes[-2] != 0:
            returns[symbol] = (closes[-1] - closes[-2]) / closes[-2]
    return returns
```

Remove the cross-run `_benchmark_returns_cache`; the current run's daily result
is the source of truth.

- [ ] **Step 10: Wire preload into `refresh_tickers()`**

When `technical` is requested:

```python
daily_result = self._load_daily_bars(
    normalized_tickers,
    recorder=recorder,
)
errors.extend(daily_result.errors)
benchmark_returns = _benchmark_returns_1d(daily_result.bars_by_symbol)
```

Pass each ticker's preloaded bars and the run-local benchmark returns to
`_refresh_technical()`. Do not call the daily provider inside the per-ticker
technical builder.

- [ ] **Step 11: Run focused tests to verify GREEN**

Run the four tests from Step 5.

Expected: all pass.

- [ ] **Step 12: Run the full source-ingestion test module**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_signal_sources.py -q
```

Expected: all tests pass after updating legacy request-call assertions to the
new run-local benchmark and fallback behavior.

- [ ] **Step 13: Commit Task 2**

```bash
git add src/trading/signals/source_ingestion.py tests/trading/test_signal_sources.py
git commit -m "fix technical daily bar budget starvation"
```

---

### Task 3: Make optional enrichment phase-aware and non-destructive

**Files:**

- Modify: `tests/trading/test_signal_sources.py`
- Modify: `src/trading/signals/source_ingestion.py:122-406`
- Test: `tests/trading/test_runtime_intraday_live.py`

- [ ] **Step 1: Write failing phase-selection tests**

Add:

```python
def test_pre_open_technical_refresh_skips_intraday_fetch():
    provider = _OptionalMarketProvider()
    ...
    service.refresh_tickers(
        ("LITE",),
        as_of=PREOPEN_NOW,
        run_type="pre_open",
        source_families=("technical",),
    )
    assert provider.premarket_calls == [("LITE", PREOPEN_NOW)]
    assert provider.intraday_calls == []


def test_intraday_technical_refresh_skips_premarket_fetch():
    provider = _OptionalMarketProvider()
    ...
    service.refresh_tickers(
        ("LITE",),
        as_of=INTRADAY_NOW,
        run_type="intraday_refresh",
        source_families=("technical",),
    )
    assert provider.premarket_calls == []
    assert provider.intraday_calls == [("LITE", INTRADAY_NOW)]
```

Keep `targeted` and `fixture` compatible by permitting both optional capabilities
when present.

- [ ] **Step 2: Write failing optional-failure preservation tests**

Use providers whose optional method raises:

```python
def test_premarket_failure_keeps_daily_record_and_degrades_run():
    ...
    assert records["LITE"].payload["bars"]
    assert records["LITE"].payload["premarket_gap_pct"] is None
    assert result.ingestion_run.status == "degraded"
    assert result.ingestion_run.error_code == "RuntimeError"


def test_intraday_failure_keeps_daily_record_and_degrades_run():
    ...
    assert records["LITE"].payload["bars"]
    assert "intraday_bars" not in records["LITE"].payload
    assert result.ingestion_run.status == "degraded"
```

- [ ] **Step 3: Run the tests to verify RED**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/trading/test_signal_sources.py::test_pre_open_technical_refresh_skips_intraday_fetch \
  tests/trading/test_signal_sources.py::test_intraday_technical_refresh_skips_premarket_fetch \
  tests/trading/test_signal_sources.py::test_premarket_failure_keeps_daily_record_and_degrades_run \
  tests/trading/test_signal_sources.py::test_intraday_failure_keeps_daily_record_and_degrades_run \
  -q
```

Expected: phase tests and the premarket preservation test fail with current
shared-policy behavior.

- [ ] **Step 4: Create optional operation policies**

Only when technical ingestion is requested, create:

```python
optional_budget = max(
    self.max_requests_per_endpoint,
    len(normalized_tickers) * _PROVIDER_MAX_ATTEMPTS_PER_SCOPE,
)
premarket_policy = self._policy(
    "market_premarket_price",
    "technical",
    recorder,
    max_requests=optional_budget,
)
intraday_policy = self._policy(
    "market_intraday_bars",
    "technical",
    recorder,
    max_requests=optional_budget,
)
```

- [ ] **Step 5: Return optional errors with the technical record**

Change `_refresh_technical()` to accept:

```python
bars
benchmark_returns
run_type
premarket_policy
intraday_policy
```

It returns `_TechnicalRefreshResult`.

Use exact phase rules:

```python
include_premarket = run_type != "intraday_refresh"
include_intraday = run_type != "pre_open"
```

Catch only optional provider exceptions, append them to the result's errors, and
still construct the technical `SourceRecord` from valid daily bars.

- [ ] **Step 6: Merge optional errors in the run loop**

```python
technical_result = self._refresh_technical(...)
errors.extend(technical_result.errors)
if technical_result.record is not None:
    source_records.append(technical_result.record)
```

The existing `_ingestion_status()` now yields `degraded` for a recovered optional
failure.

- [ ] **Step 7: Run focused tests to verify GREEN**

Run the four tests from Step 3.

Expected: all pass.

- [ ] **Step 8: Run source and intraday regressions**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/trading/test_signal_sources.py \
  tests/trading/test_technical_signals.py \
  tests/trading/test_runtime_intraday_live.py \
  -q
```

Expected: all pass.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/trading/signals/source_ingestion.py tests/trading/test_signal_sources.py tests/trading/test_runtime_intraday_live.py
git commit -m "fix optional technical enrichment isolation"
```

---

### Task 4: Verify the public pipeline and production-safe smoke

**Files:**

- Modify: `tests/trading/test_pipeline.py`
- Modify: `plan/progress_tracker.md`

- [ ] **Step 1: Write a failing public-pipeline regression**

Build a `UniverseSnapshotResult` whose `included_symbols` contains more than 100
fake symbols with LITE near the end. Use a batch-capable fake provider and the
real `SignalPipeline` plus `SourceIngestionService`.

Assert:

```python
snapshot_by_ticker = {snapshot.ticker: snapshot for snapshot in snapshots}
lite = snapshot_by_ticker["LITE"]
assert lite.source_freshness_json["technical"] == "fresh"
assert lite.signal_json["technical"]["last_price"] is not None
assert "technical.market_bars" not in lite.missing_signals_json
```

- [ ] **Step 2: Run the public-pipeline test to verify RED or regression coverage**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_pipeline.py::test_large_preopen_scope_keeps_late_ticker_technical_snapshot -q
```

If Tasks 1–3 already make the new test pass on its first run, document that it is
integration regression coverage rather than a new RED unit; do not weaken the
assertions merely to force failure.

- [ ] **Step 3: Run all focused suites**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/tools/test_market_data.py \
  tests/trading/test_signal_sources.py \
  tests/trading/test_technical_signals.py \
  tests/trading/test_pipeline.py \
  tests/trading/test_runtime_live.py \
  tests/trading/test_runtime_intraday_live.py \
  -q
```

Expected: all pass.

- [ ] **Step 4: Run broader unit tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading -q
```

Expected: all tests pass, or any pre-existing environment-dependent failures are
listed with exact evidence and shown unrelated to this slice.

- [ ] **Step 5: Compile and check the diff**

Run:

```bash
source ~/.venv/bin/activate
python -m compileall -q src tests
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 6: Run a standalone rate-conscious live smoke**

Run only one ticker:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_source_ingestion_smoke.py \
  --ticker LITE \
  --families technical \
  --json
```

Expected:

- smoke status is passed or degraded only for optional enrichment;
- the LITE technical preview contains non-empty daily `bars`;
- benchmark returns are present when SPY/QQQ data is available;
- there is no `technical.market_bars` missing state.

This command hits Alpaca and must not be added to ordinary CI.

- [ ] **Step 7: Update the project progress tracker**

Prepend a 2026-07-28 entry to `plan/progress_tracker.md` recording:

- confirmed root cause;
- batch pagination and request-budget isolation behavior;
- phase-aware optional enrichment;
- late-LITE regressions;
- exact verification commands and results;
- live smoke outcome.

- [ ] **Step 8: Commit Task 4**

```bash
git add tests/trading/test_pipeline.py plan/progress_tracker.md
git commit -m "test signal ingestion budget isolation"
```

- [ ] **Step 9: Final verification**

Run:

```bash
git status --short
git log -5 --oneline
```

Expected: worktree is clean and contains the Task 1–4 commits.
