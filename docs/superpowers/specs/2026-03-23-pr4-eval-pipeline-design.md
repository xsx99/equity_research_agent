# PR4 – Evaluation Pipeline Design

**Date:** 2026-03-23
**Status:** Approved
**Context:** `plan/research_app/implementation_plan.md` PR4 section; design reference `plan/research_app/design_doc.md`

---

## Summary

Implement the evaluation pipeline (`eval_runs.py` equivalent) that closes the research loop by computing realized vs benchmark returns for matured research runs and labeling them with a `rule_v1` outcome.

---

## Architecture & Module Layout

### New files

| File | Role |
|------|------|
| `src/research/eval_pipeline.py` | `EvalPipeline` class — orchestration |
| `scripts/run_eval_once.py` | CLI entry point (mirrors `run_research_once.py`) |
| `tests/research/test_eval_pipeline.py` | Unit tests |

### Extended files

| File | What is added |
|------|---------------|
| `src/research/repository.py` | `get_eligible_runs()`, `upsert_eval_result()` |
| `src/tools/market_data.py` | `fetch_daily_closes_range` method on protocol + `AlpacaMarketDataProvider`; `fetch_return_over_range(ticker, start_date, end_date, provider=None)` helper |

No new packages, no new ORM models — all reuse existing `EvalResult`, `ResearchRun`, `ResearchOutput`, `ResearchTimeHorizon`, `EvalOutcomeLabel`.

The `MarketDataProvider` protocol and `AlpacaMarketDataProvider` are extended with a new method `fetch_daily_closes_range(ticker, start_date, end_date)` to support historical date-range queries (the existing `fetch_daily_closes` only accepts `lookback_days` anchored to now and cannot be used for historical ranges).

---

## Eligibility Query

`get_eligible_runs(session, as_of_cutoff)` queries for:
- `research_runs.status = 'succeeded'`
- A matching `research_outputs` row exists with a valid `time_horizon` (`1d`, `3d`, `5d`)
- `research_runs.as_of + horizon_days <= as_of_cutoff` (window has fully elapsed)

Returns a list of `(ResearchRun, ResearchOutput)` tuples. Runs without a valid output or horizon are silently skipped with a warning log — no exception raised.

`get_eligible_runs` returns **all** eligible runs including those that already have an `EvalResult` row — re-evaluation is valid given upsert semantics. There is no filter to skip already-evaluated runs.

---

## Data Flow

For each eligible run `EvalPipeline`:

1. Looks up `horizon_days` via `ResearchTimeHorizon.days_mapping()`
2. Calls `fetch_return_over_range(ticker, start=run.as_of.date(), end=run.as_of.date() + timedelta(days=horizon_days))` for the ticker
3. Looks up benchmark return from in-memory cache keyed on `(benchmark_symbol, as_of.date(), horizon_days)`; calls `fetch_return_over_range(benchmark_symbol, ...)` only on cache miss
4. Both calls use an injectable `MarketDataProvider` — returns `None` on failure (logged; eval still written with `NULL` returns and `NULL` outcome_label)
5. Calls `apply_rule_v1(decision, realized_return, benchmark_return)` → outcome label
6. Calls `upsert_eval_result(session, run_id, ...)` — inserts or overwrites (upsert semantics)

The pipeline does **not** commit; callers own transaction boundaries (same pattern as `ResearchPipeline`).

---

## `fetch_return_over_range`

### New protocol method

```python
class MarketDataProvider(Protocol):
    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        """Return close prices in ascending time order for bars within [start_date, end_date]."""
```

`AlpacaMarketDataProvider` implements this by calling the Alpaca `/v2/stocks/bars` endpoint with explicit `start`/`end` ISO date params (same endpoint as `fetch_daily_closes`, different parameterization).

### New module-level helper

```python
def fetch_return_over_range(
    ticker: str,
    start_date: date,
    end_date: date,
    provider: Optional[MarketDataProvider] = None,
) -> Optional[float]:
    """Return (end_close / start_close) - 1 using daily close prices.

    - start_close: close of the first available trading day on or after start_date
    - end_close:   close of the last available trading day on or before end_date
    - Returns None if fewer than 2 bars are available in the range, or on any provider error.
    Uses AlpacaMarketDataProvider by default.
    """
```

**Weekend/holiday handling (MVP):** Horizon elapse is measured in calendar days (e.g., `as_of + 1 day` for `1d`). `fetch_return_over_range` uses the first available bar on/after `start_date` and the last available bar on/before `end_date`. If the range yields fewer than 2 bars (e.g., `as_of` is a Friday and `end_date` is Saturday with no Saturday bar), the function returns `None` and logs a warning — the eval is still written with `NULL` returns and `NULL` outcome_label. This is an accepted MVP limitation.

---

## `EvalPipeline` Class

```python
class EvalPipeline:
    def __init__(
        self,
        session: Session,
        provider: Optional[MarketDataProvider] = None,
        benchmark_symbol: str = "SPY",
        neutral_threshold: float = 0.01,
    ) -> None: ...

    def run_all(self, as_of: Optional[datetime] = None) -> EvalPipelineResult: ...
    def run_single(self, run_id: uuid.UUID) -> EvalTickerResult: ...
```

`run_single` bypasses the eligibility window check — it force-evaluates the run regardless of whether the horizon has elapsed. This is useful for manual testing and debugging. `ticker` is read from `ResearchRun.ticker`. If the run has no output row, it returns `EvalTickerResult(success=False, error="no_output_row")`.

### Dataclass fields

```python
@dataclass
class EvalTickerResult:
    run_id: uuid.UUID
    ticker: str
    success: bool
    outcome_label: Optional[str] = None
    error: Optional[str] = None

@dataclass
class EvalPipelineResult:
    evaluated: int = 0
    failed: int = 0
    skipped: int = 0
    ticker_results: list[EvalTickerResult] = field(default_factory=list)
```

---

## `rule_v1` Label Matrix

Pure function `apply_rule_v1(decision, realized_return, benchmark_return, neutral_threshold=0.01)`:

| Decision | Condition | Label |
|----------|-----------|-------|
| `bullish` | `realized_return > 0` AND `≥ benchmark_return` | `correct` |
| `bullish` | `realized_return < 0` | `wrong_direction` |
| `bullish` | otherwise | `partially_correct` |
| `bearish` | `realized_return < 0` AND `≤ benchmark_return` | `correct` | (intentional: if benchmark also fell further, bearish was correct even in a down market) |
| `bearish` | `realized_return > 0` | `wrong_direction` |
| `bearish` | otherwise | `partially_correct` |
| `neutral`/`abstain` | `abs(realized_return) > neutral_threshold` | `wrong_direction` |
| `neutral`/`abstain` | otherwise | `uninformative` |
| any | `realized_return is None` | `None` |

`neutral_threshold` defaults to `0.01` (1%) — hardcoded for MVP.

---

## Repository Additions

**`get_eligible_runs(session, as_of_cutoff)`**
- Joins `research_runs` with `research_outputs` on `run_id`
- Filters: `status='succeeded'`, valid `time_horizon`, `as_of + horizon_days <= as_of_cutoff`
- Returns `list[tuple[ResearchRun, ResearchOutput]]`

**`upsert_eval_result(session, run_id, horizon_days, realized_return, benchmark_return, benchmark_symbol, evaluation_method, evaluation_params, outcome_label)`**
- Checks for existing `EvalResult` row by `run_id`
- Updates all fields if found, inserts new row otherwise

---

## CLI Entry Point

`scripts/run_eval_once.py` — mirrors `run_research_once.py`:
- `--run-id UUID` — evaluate a single run
- No flag — evaluate all eligible runs
- Prints JSON summary to stdout
- Exits non-zero if any eval failed

---

## Test Plan

**`TestRuleV1`** — pure unit tests, no DB or mocks:
- All 8 label combinations from the matrix
- `None` realized_return → `None` label
- Boundary values (exactly 0, exactly at threshold)

**`TestEvalPipelineHappyPath`** — patches `repository`, injects stub market provider:
- Eligible run → returns fetched → label computed → `upsert_eval_result` called
- Benchmark cache: two runs with same `(SPY, as_of_date, horizon_days)` → provider called once for SPY
- Market fetch failure → eval written with `NULL` returns and `NULL` label, no exception raised

**`TestEvalPipelineEdgeCases`**:
- No eligible runs → zero counts, no market calls
- Run with no output row → skipped silently
- `run_all` called twice → `upsert_eval_result` called twice (upsert confirmed)

---

## Assumptions & Constraints

- Elapsed window measured from `research_runs.as_of`, not `finished_at`
- Eval pipeline lives in `src/research/` (not a separate package) for now
- `benchmark_return` cached in-memory per `(benchmark_symbol, as_of_date, horizon_days)` within a single batch run
- Upsert semantics: re-running overwrites existing `eval_results` row
- `neutral_threshold` is hardcoded `0.01` for MVP; `evaluation_params` JSONB column reserved for future configurability
- Pipeline does not commit — callers own transactions
- Market data fetched via existing `AlpacaMarketDataProvider`; no new provider introduced
