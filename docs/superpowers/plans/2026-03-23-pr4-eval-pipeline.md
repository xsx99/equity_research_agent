# PR4 – Evaluation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an `EvalPipeline` that finds matured research runs, fetches realized and benchmark returns, applies `rule_v1` labeling, and persists results to `eval_results`.

**Architecture:** `EvalPipeline` class in `src/research/eval_pipeline.py` mirrors the existing `ResearchPipeline` pattern — injectable `MarketDataProvider`, no commits (caller owns transaction), `EvalPipelineResult`/`EvalTickerResult` dataclasses. A new `fetch_daily_closes_range` method on the market data provider handles historical date-range price fetching. Repository helpers `get_eligible_runs` and `upsert_eval_result` handle all DB access.

**Tech Stack:** Python 3.11+, SQLAlchemy (mock session pattern for tests), httpx (via `AlpacaMarketDataProvider`), pytest + `unittest.mock`.

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `src/tools/market_data.py` | Add `fetch_daily_closes_range` to protocol + `AlpacaMarketDataProvider`; add `fetch_return_over_range` helper |
| Modify | `src/research/repository.py` | Add `get_eligible_runs`, `upsert_eval_result` |
| Create | `src/research/eval_pipeline.py` | `apply_rule_v1`, dataclasses, `EvalPipeline` class |
| Create | `scripts/run_eval_once.py` | CLI entry point |
| Modify | `tests/tools/test_market_data.py` | Tests for `fetch_daily_closes_range` and `fetch_return_over_range` |
| Modify | `tests/research/test_repository.py` | Tests for `get_eligible_runs` and `upsert_eval_result` |
| Create | `tests/research/test_eval_pipeline.py` | Tests for `apply_rule_v1` and `EvalPipeline` |

---

## Task 1: `fetch_daily_closes_range` on `AlpacaMarketDataProvider`

**Files:**
- Modify: `src/tools/market_data.py`
- Test: `tests/tools/test_market_data.py`

### Background

`fetch_daily_closes(ticker, lookback_days)` is anchored to `now()` — it cannot fetch prices for a historical window like "AAPL from 2026-03-01 to 2026-03-04". We need a separate method that takes explicit `start_date`/`end_date`.

The `MarketDataProvider` Protocol gets a new method. `AlpacaMarketDataProvider` implements it using the same `/v2/stocks/bars` endpoint but with ISO date strings instead of lookback arithmetic.

- [ ] **Step 1: Write the failing tests**

Append to `tests/tools/test_market_data.py`:

```python
from datetime import date
from src.tools.market_data import fetch_return_over_range


def test_fetch_daily_closes_range_returns_chronological_closes():
    client = _CapturingClient(
        {
            "bars": {
                "AAPL": [
                    {"t": "2026-03-01T05:00:00Z", "c": 170.0},
                    {"t": "2026-03-04T05:00:00Z", "c": 174.0},
                ]
            }
        }
    )
    provider = AlpacaMarketDataProvider(
        api_key="k", secret_key="s", client=client
    )
    closes = provider.fetch_daily_closes_range(
        "AAPL", date(2026, 3, 1), date(2026, 3, 4)
    )
    assert closes == [170.0, 174.0]
    call = client.calls[0]
    assert call["params"]["start"] == "2026-03-01"
    assert call["params"]["end"] == "2026-03-04"
    assert "limit" not in call["params"]


def test_fetch_daily_closes_range_returns_empty_for_no_bars():
    client = _CapturingClient({"bars": {"AAPL": []}})
    provider = AlpacaMarketDataProvider(api_key="k", secret_key="s", client=client)
    closes = provider.fetch_daily_closes_range("AAPL", date(2026, 3, 1), date(2026, 3, 1))
    assert closes == []


def test_fetch_return_over_range_computes_return():
    class _StubProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            return [100.0, 105.0]
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 4), provider=_StubProvider())
    assert result == pytest.approx(0.05)


def test_fetch_return_over_range_returns_none_for_fewer_than_two_bars():
    class _StubProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            return [100.0]
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 1), provider=_StubProvider())
    assert result is None


def test_fetch_return_over_range_returns_none_on_provider_error():
    class _RaisingProvider:
        def fetch_daily_closes_range(self, ticker, start_date, end_date):
            raise RuntimeError("network_error")
        def fetch_daily_closes(self, ticker, lookback_days):
            return []
    result = fetch_return_over_range("AAPL", date(2026, 3, 1), date(2026, 3, 4), provider=_RaisingProvider())
    assert result is None
```

Add `import pytest` to the top of `tests/tools/test_market_data.py` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_market_data.py -v -k "range"
```

Expected: `AttributeError: 'AlpacaMarketDataProvider' object has no attribute 'fetch_daily_closes_range'` or `ImportError` for `fetch_return_over_range`.

- [ ] **Step 3: Add `fetch_daily_closes_range` to the `MarketDataProvider` Protocol**

In `src/tools/market_data.py`, update the `MarketDataProvider` Protocol class (around line 34):

```python
class MarketDataProvider(Protocol):
    """Contract for pluggable market data providers."""

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        """Return close prices in ascending time order."""

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        """Return close prices in ascending time order for bars within [start_date, end_date]."""

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        """Return optional context fields such as sector and earnings distance."""
```

Add `from datetime import date, datetime, timedelta, timezone` (update the existing datetime import at the top to include `date`).

- [ ] **Step 4: Implement `fetch_daily_closes_range` on `AlpacaMarketDataProvider`**

Add this method to `AlpacaMarketDataProvider` after `fetch_daily_closes`:

```python
def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
    symbol = ticker.upper()
    response = self._client.get(
        f"{self.data_base_url}/v2/stocks/bars",
        params={
            "symbols": symbol,
            "timeframe": "1Day",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "sort": "asc",
            "adjustment": "split",
            "feed": "iex",
        },
        headers=self._auth_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    bars_payload = payload.get("bars", {})
    if isinstance(bars_payload, dict):
        bars = bars_payload.get(symbol, [])
    elif isinstance(bars_payload, list):
        bars = bars_payload
    else:
        bars = []
    return [float(item["c"]) for item in bars if item.get("c") is not None]
```

- [ ] **Step 5: Implement `fetch_return_over_range` module-level helper**

Add this function after `get_market_snapshot` in `src/tools/market_data.py`:

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
    - Returns None if fewer than 2 bars are available or on any provider error.
    - Weekend/holiday MVP: if end_date falls on a non-trading day, the last
      available bar before it is used; returns None if fewer than 2 bars result.
    """
    created_default = provider is None
    provider_instance = provider or AlpacaMarketDataProvider()
    try:
        closes = provider_instance.fetch_daily_closes_range(ticker, start_date, end_date)
        if len(closes) < 2:
            logger.warning(
                "fetch_return_over_range_insufficient_bars",
                ticker=ticker,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                bar_count=len(closes),
            )
            return None
        start_close = closes[0]
        end_close = closes[-1]
        if start_close == 0:
            return None
        return (end_close / start_close) - 1
    except Exception as exc:
        logger.error(
            "fetch_return_over_range_failed",
            ticker=ticker,
            error=str(exc),
            exc_info=True,
        )
        return None
    finally:
        if created_default and hasattr(provider_instance, "close"):
            try:
                provider_instance.close()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("market_provider_close_failed", ticker=ticker)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/tools/test_market_data.py -v
```

Expected: all tests pass including the existing ones.

- [ ] **Step 7: Commit**

```bash
git add src/tools/market_data.py tests/tools/test_market_data.py
git commit -m "feat: add fetch_daily_closes_range and fetch_return_over_range for eval"
```

---

## Task 2: Repository helpers — `get_eligible_runs` and `upsert_eval_result`

**Files:**
- Modify: `src/research/repository.py`
- Test: `tests/research/test_repository.py`

### Background

`get_eligible_runs` queries for succeeded runs whose horizon window has elapsed. It joins `research_runs` with `research_outputs`, then filters in Python (simpler than SQL interval arithmetic for MVP). It includes already-evaluated runs since we use upsert semantics.

`upsert_eval_result` checks for an existing `EvalResult` row and updates it, or inserts a new one.

- [ ] **Step 1: Write the failing tests**

Append to `tests/research/test_repository.py`:

```python
from datetime import timedelta
from unittest.mock import MagicMock, patch, call
import uuid

from src.db.models.evaluation import EvalResult, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, RunStatus
from src.research import repository

_AS_OF = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
_CUTOFF = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)  # well past all horizons


def _make_run_and_output(
    time_horizon="3d",
    status=RunStatus.SUCCEEDED.value,
    as_of=_AS_OF,
):
    run_id = uuid.uuid4()
    run = MagicMock(spec=ResearchRun)
    run.run_id = run_id
    run.ticker = "AAPL"
    run.as_of = as_of
    run.status = status

    output = MagicMock(spec=ResearchOutput)
    output.run_id = run_id
    output.decision = "bullish"
    output.time_horizon = time_horizon
    return run, output


class TestGetEligibleRuns:
    def test_returns_eligible_run(self):
        run, output = _make_run_and_output()
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (run, output)
        ]
        results = repository.get_eligible_runs(session, as_of_cutoff=_CUTOFF)
        assert len(results) == 1
        assert results[0] == (run, output)

    def test_filters_out_run_with_elapsed_window_not_yet_passed(self):
        # as_of + 3 days = 2026-03-04, cutoff = 2026-03-03 → not elapsed
        run, output = _make_run_and_output(
            time_horizon="3d",
            as_of=datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
        )
        early_cutoff = datetime(2026, 3, 3, 9, 0, 0, tzinfo=timezone.utc)
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (run, output)
        ]
        results = repository.get_eligible_runs(session, as_of_cutoff=early_cutoff)
        assert results == []

    def test_returns_empty_when_no_rows(self):
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = []
        results = repository.get_eligible_runs(session, as_of_cutoff=_CUTOFF)
        assert results == []


class TestUpsertEvalResult:
    def _call(self, session, existing=None, run_id=None):
        run_id = run_id or uuid.uuid4()
        session.query.return_value.filter.return_value.first.return_value = existing
        return repository.upsert_eval_result(
            session,
            run_id=run_id,
            horizon_days=3,
            realized_return=0.05,
            benchmark_return=0.02,
            benchmark_symbol="SPY",
            evaluation_method=EvaluationMethod.RULE_V1.value,
            evaluation_params=None,
            outcome_label="correct",
        )

    def test_inserts_when_no_existing_row(self):
        session = MagicMock()
        result = self._call(session, existing=None)
        session.add.assert_called_once_with(result)
        assert result.outcome_label == "correct"
        assert result.horizon_days == 3

    def test_updates_when_existing_row(self):
        existing = MagicMock(spec=EvalResult)
        session = MagicMock()
        result = self._call(session, existing=existing)
        assert result is existing
        session.add.assert_not_called()
        assert existing.outcome_label == "correct"
        assert existing.realized_return == 0.05

    def test_upsert_twice_updates_outcome_label(self):
        existing = MagicMock(spec=EvalResult)
        existing.outcome_label = "partially_correct"
        session = MagicMock()
        run_id = uuid.uuid4()
        # First call — existing row with old label
        self._call(session, existing=existing, run_id=run_id)
        # Simulate updated outcome on second call
        existing.outcome_label = "correct"
        self._call(session, existing=existing, run_id=run_id)
        assert existing.outcome_label == "correct"
```

Add the missing imports to the top of the test file (they're mostly already there; add `EvalResult`, `EvaluationMethod`, `ResearchOutput`).

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/research/test_repository.py -v -k "Eligible or Upsert"
```

Expected: `AttributeError: module 'src.research.repository' has no attribute 'get_eligible_runs'`.

- [ ] **Step 3: Implement `get_eligible_runs` in `src/research/repository.py`**

Add these imports at the top of `src/research/repository.py`:

```python
from datetime import timedelta
from src.db.models.evaluation import EvalResult, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon, RunStatus
```

Add the function after `persist_output`:

```python
# ---------------------------------------------------------------------------
# EvalResult helpers
# ---------------------------------------------------------------------------


def get_eligible_runs(
    session: Session,
    as_of_cutoff: datetime,
) -> list[tuple[ResearchRun, ResearchOutput]]:
    """Return (run, output) pairs eligible for evaluation.

    Eligibility: succeeded status, valid time_horizon, and
    as_of + horizon_days <= as_of_cutoff (window has fully elapsed).
    Includes runs that already have an EvalResult (upsert semantics).
    """
    horizon_map = ResearchTimeHorizon.days_mapping()
    valid_horizons = list(horizon_map.keys())

    rows = (
        session.query(ResearchRun, ResearchOutput)
        .join(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
        .filter(
            ResearchRun.status == RunStatus.SUCCEEDED.value,
            ResearchOutput.time_horizon.in_(valid_horizons),
        )
        .all()
    )

    eligible = []
    for run, output in rows:
        horizon_days = horizon_map.get(output.time_horizon)
        if horizon_days is None:
            logger.warning(
                "get_eligible_runs_unknown_horizon",
                run_id=str(run.run_id),
                time_horizon=output.time_horizon,
            )
            continue
        if run.as_of + timedelta(days=horizon_days) <= as_of_cutoff:
            eligible.append((run, output))
    return eligible
```

- [ ] **Step 4: Implement `upsert_eval_result` in `src/research/repository.py`**

```python
def upsert_eval_result(
    session: Session,
    *,
    run_id: uuid.UUID,
    horizon_days: int,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    benchmark_symbol: str,
    evaluation_method: str,
    evaluation_params: Optional[dict[str, Any]],
    outcome_label: Optional[str],
) -> EvalResult:
    """Insert or overwrite an EvalResult row for the given run_id."""
    existing = session.query(EvalResult).filter(EvalResult.run_id == run_id).first()
    if existing is not None:
        existing.horizon_days = horizon_days
        existing.realized_return = realized_return
        existing.benchmark_return = benchmark_return
        existing.benchmark_symbol = benchmark_symbol
        existing.evaluation_method = evaluation_method
        existing.evaluation_params = evaluation_params
        existing.outcome_label = outcome_label
        logger.info("eval_result_updated", run_id=str(run_id), outcome_label=outcome_label)
        return existing
    result = EvalResult(
        run_id=run_id,
        horizon_days=horizon_days,
        realized_return=realized_return,
        benchmark_return=benchmark_return,
        benchmark_symbol=benchmark_symbol,
        evaluation_method=evaluation_method,
        evaluation_params=evaluation_params,
        outcome_label=outcome_label,
    )
    session.add(result)
    logger.info("eval_result_created", run_id=str(run_id), outcome_label=outcome_label)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/research/test_repository.py -v
```

Expected: all tests pass including existing ones.

- [ ] **Step 6: Commit**

```bash
git add src/research/repository.py tests/research/test_repository.py
git commit -m "feat: add get_eligible_runs and upsert_eval_result to repository"
```

---

## Task 3: `apply_rule_v1` pure function

**Files:**
- Create: `src/research/eval_pipeline.py`
- Create: `tests/research/test_eval_pipeline.py`

### Background

`apply_rule_v1` has no I/O — pure function, easiest to test exhaustively. Write all label matrix tests first, then implement.

- [ ] **Step 1: Create `tests/research/test_eval_pipeline.py` with the rule tests**

```python
"""Unit tests for src/research/eval_pipeline.py."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.evaluation import EvalOutcomeLabel
from src.db.models.research import ResearchOutput, ResearchRun, RunStatus


# ---------------------------------------------------------------------------
# apply_rule_v1 — imported after the module exists
# ---------------------------------------------------------------------------


class TestRuleV1:
    """Exhaustive label matrix tests. No I/O required."""

    def _label(self, decision, realized, benchmark=0.01, threshold=0.01):
        from src.research.eval_pipeline import apply_rule_v1
        return apply_rule_v1(decision, realized, benchmark, neutral_threshold=threshold)

    # --- realized_return is None ---

    def test_none_realized_returns_none(self):
        assert self._label("bullish", None) is None

    def test_none_realized_bearish_returns_none(self):
        assert self._label("bearish", None) is None

    def test_none_realized_neutral_returns_none(self):
        assert self._label("neutral", None) is None

    # --- bullish ---

    def test_bullish_positive_outperforms_benchmark_is_correct(self):
        assert self._label("bullish", 0.05, benchmark=0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bullish_positive_equals_benchmark_is_correct(self):
        assert self._label("bullish", 0.03, benchmark=0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bullish_positive_underperforms_benchmark_is_partially_correct(self):
        assert self._label("bullish", 0.01, benchmark=0.05) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bullish_exactly_zero_is_partially_correct(self):
        assert self._label("bullish", 0.0, benchmark=0.01) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bullish_negative_is_wrong_direction(self):
        assert self._label("bullish", -0.03, benchmark=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_bullish_none_benchmark_positive_is_partially_correct(self):
        # Can't confirm outperformance without benchmark
        assert self._label("bullish", 0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # --- bearish ---

    def test_bearish_negative_beats_benchmark_is_correct(self):
        # stock fell -5%, SPY fell -3% → stock fell more → bearish correct
        assert self._label("bearish", -0.05, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_equals_benchmark_is_correct(self):
        assert self._label("bearish", -0.03, benchmark=-0.03) == EvalOutcomeLabel.CORRECT.value

    def test_bearish_negative_outperforms_benchmark_is_partially_correct(self):
        # stock fell -1%, SPY fell -5% → stock held up better → partial
        assert self._label("bearish", -0.01, benchmark=-0.05) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_exactly_zero_is_partially_correct(self):
        assert self._label("bearish", 0.0, benchmark=-0.01) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    def test_bearish_positive_is_wrong_direction(self):
        assert self._label("bearish", 0.03, benchmark=-0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_bearish_none_benchmark_negative_is_partially_correct(self):
        assert self._label("bearish", -0.05, benchmark=None) == EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # --- neutral / abstain ---

    def test_neutral_small_move_is_uninformative(self):
        assert self._label("neutral", 0.005, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_neutral_exactly_at_threshold_is_uninformative(self):
        assert self._label("neutral", 0.01, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_neutral_exceeds_threshold_positive_is_wrong_direction(self):
        assert self._label("neutral", 0.02, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_neutral_exceeds_threshold_negative_is_wrong_direction(self):
        assert self._label("neutral", -0.02, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value

    def test_abstain_small_move_is_uninformative(self):
        assert self._label("abstain", 0.005, threshold=0.01) == EvalOutcomeLabel.UNINFORMATIVE.value

    def test_abstain_large_move_is_wrong_direction(self):
        assert self._label("abstain", 0.05, threshold=0.01) == EvalOutcomeLabel.WRONG_DIRECTION.value
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/research/test_eval_pipeline.py::TestRuleV1 -v
```

Expected: `ModuleNotFoundError: No module named 'src.research.eval_pipeline'`.

- [ ] **Step 3: Create `src/research/eval_pipeline.py` with `apply_rule_v1`**

```python
"""Evaluation pipeline — batch orchestration for scoring matured research runs.

Responsible for:
- Querying succeeded runs whose time_horizon window has elapsed.
- Fetching realized return (ticker) and benchmark return (SPY by default).
- Applying rule_v1 labeling.
- Upserting EvalResult rows via the repository layer.

Does not commit; callers own transaction boundaries.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models.evaluation import EvalOutcomeLabel, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon
from src.research import repository
from src.tools.market_data import AlpacaMarketDataProvider, MarketDataProvider, fetch_return_over_range

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure labeling function
# ---------------------------------------------------------------------------


def apply_rule_v1(
    decision: str,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    neutral_threshold: float = 0.01,
) -> Optional[str]:
    """Apply rule_v1 label matrix.

    Returns None when realized_return is None (market data unavailable).
    When benchmark_return is None, bullish/bearish cannot achieve 'correct'
    (defaults to 'partially_correct' for correct-direction moves).
    """
    if realized_return is None:
        return None

    if decision == "bullish":
        if realized_return < 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return > 0
            and benchmark_return is not None
            and realized_return >= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    if decision == "bearish":
        if realized_return > 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return < 0
            and benchmark_return is not None
            and realized_return <= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # neutral or abstain
    if abs(realized_return) > neutral_threshold:
        return EvalOutcomeLabel.WRONG_DIRECTION.value
    return EvalOutcomeLabel.UNINFORMATIVE.value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/research/test_eval_pipeline.py::TestRuleV1 -v
```

Expected: all 20 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/research/eval_pipeline.py tests/research/test_eval_pipeline.py
git commit -m "feat: add apply_rule_v1 with exhaustive label matrix tests"
```

---

## Task 4: `EvalPipeline` class

**Files:**
- Modify: `src/research/eval_pipeline.py`
- Modify: `tests/research/test_eval_pipeline.py`

### Background

`EvalPipeline` mirrors `ResearchPipeline`: injectable provider, no commits, result dataclasses. The benchmark return is cached per `(symbol, as_of_date, horizon_days)` to avoid redundant API calls within a single batch.

- [ ] **Step 1: Write the failing pipeline tests**

Append to `tests/research/test_eval_pipeline.py`:

```python
# ---------------------------------------------------------------------------
# Helpers for EvalPipeline tests
# ---------------------------------------------------------------------------

_AS_OF = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
_CUTOFF = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)


def _make_run(ticker="AAPL", as_of=_AS_OF) -> MagicMock:
    run = MagicMock(spec=ResearchRun)
    run.run_id = uuid.uuid4()
    run.ticker = ticker
    run.as_of = as_of
    run.status = RunStatus.SUCCEEDED.value
    return run


def _make_output(decision="bullish", time_horizon="3d") -> MagicMock:
    output = MagicMock(spec=ResearchOutput)
    output.decision = decision
    output.time_horizon = time_horizon
    return output


class _StubProvider:
    """Returns a fixed return for every ticker/date pair."""

    def __init__(self, return_value: Optional[float] = 0.05):
        self.call_count = 0
        self._return_value = return_value

    def fetch_daily_closes_range(self, ticker: str, start_date: date, end_date: date) -> list[float]:
        self.call_count += 1
        if self._return_value is None:
            raise RuntimeError("simulated_market_failure")
        # Fake two bars that produce the configured return
        return [100.0, 100.0 * (1 + self._return_value)]

    def fetch_daily_closes(self, ticker: str, lookback_days: int) -> list[float]:
        return []

    def fetch_context(self, ticker: str) -> dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# TestEvalPipelineHappyPath
# ---------------------------------------------------------------------------


class TestEvalPipelineHappyPath:

    @patch("src.research.eval_pipeline.repository")
    def test_happy_path_calls_upsert(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(
            session=MagicMock(),
            provider=_StubProvider(return_value=0.05),
        )
        result = pipeline.run_all(as_of=_CUTOFF)

        mock_repo.upsert_eval_result.assert_called_once()
        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["run_id"] == run.run_id
        assert call_kwargs["horizon_days"] == 3
        assert call_kwargs["outcome_label"] is not None
        assert result.evaluated == 1
        assert result.failed == 0

    @patch("src.research.eval_pipeline.repository")
    def test_benchmark_fetched_only_once_per_unique_key(self, mock_repo):
        """Two runs with same as_of, same horizon → SPY fetched once."""
        from src.research.eval_pipeline import EvalPipeline

        run1 = _make_run("AAPL", as_of=_AS_OF)
        run2 = _make_run("MSFT", as_of=_AS_OF)
        output1 = _make_output("bullish", "3d")
        output2 = _make_output("bullish", "3d")
        mock_repo.get_eligible_runs.return_value = [(run1, output1), (run2, output2)]

        provider = _StubProvider(return_value=0.05)
        pipeline = EvalPipeline(session=MagicMock(), provider=provider, benchmark_symbol="SPY")
        pipeline.run_all(as_of=_CUTOFF)

        # 2 ticker calls (AAPL, MSFT) + 1 SPY call = 3 total
        assert provider.call_count == 3

    @patch("src.research.eval_pipeline.repository")
    def test_market_failure_writes_null_outcome_no_exception(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(
            session=MagicMock(),
            provider=_StubProvider(return_value=None),
        )
        result = pipeline.run_all(as_of=_CUTOFF)

        mock_repo.upsert_eval_result.assert_called_once()
        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["realized_return"] is None
        assert call_kwargs["outcome_label"] is None
        assert result.evaluated == 1  # written, so counts as evaluated

    @patch("src.research.eval_pipeline.repository")
    def test_correct_outcome_label_for_bullish_outperform(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output(decision="bullish", time_horizon="3d")
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        # ticker returns 5%, SPY returns 2% → bullish correct
        call_count = {"n": 0}
        class _DirectedProvider:
            def fetch_daily_closes_range(self, ticker, start_date, end_date):
                call_count["n"] += 1
                if ticker == "SPY":
                    return [100.0, 102.0]
                return [100.0, 105.0]
            def fetch_daily_closes(self, ticker, lookback_days):
                return []
            def fetch_context(self, ticker):
                return {}

        pipeline = EvalPipeline(session=MagicMock(), provider=_DirectedProvider())
        pipeline.run_all(as_of=_CUTOFF)

        call_kwargs = mock_repo.upsert_eval_result.call_args.kwargs
        assert call_kwargs["outcome_label"] == EvalOutcomeLabel.CORRECT.value


# ---------------------------------------------------------------------------
# TestEvalPipelineEdgeCases
# ---------------------------------------------------------------------------


class TestEvalPipelineEdgeCases:

    @patch("src.research.eval_pipeline.repository")
    def test_no_eligible_runs_returns_zero_counts(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline, EvalPipelineResult

        mock_repo.get_eligible_runs.return_value = []
        pipeline = EvalPipeline(session=MagicMock(), provider=_StubProvider())
        result = pipeline.run_all(as_of=_CUTOFF)

        assert isinstance(result, EvalPipelineResult)
        assert result.evaluated == 0
        assert result.failed == 0
        mock_repo.upsert_eval_result.assert_not_called()

    @patch("src.research.eval_pipeline.repository")
    def test_run_single_bypasses_eligibility(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run_id = uuid.uuid4()
        run = _make_run()
        run.run_id = run_id
        output = _make_output()

        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [run, output]

        pipeline = EvalPipeline(session=session, provider=_StubProvider())
        result = pipeline.run_single(run_id)

        assert result.success is True
        assert result.run_id == run_id
        mock_repo.upsert_eval_result.assert_called_once()

    @patch("src.research.eval_pipeline.repository")
    def test_run_single_no_output_returns_failure(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run_id = uuid.uuid4()
        run = _make_run()
        run.run_id = run_id

        session = MagicMock()
        # First query returns run, second (output) returns None
        session.query.return_value.filter.return_value.first.side_effect = [run, None]

        pipeline = EvalPipeline(session=session, provider=_StubProvider())
        result = pipeline.run_single(run_id)

        assert result.success is False
        assert result.error == "no_output_row"
        mock_repo.upsert_eval_result.assert_not_called()

    @patch("src.research.eval_pipeline.repository")
    def test_run_all_twice_calls_upsert_twice(self, mock_repo):
        from src.research.eval_pipeline import EvalPipeline

        run = _make_run()
        output = _make_output()
        mock_repo.get_eligible_runs.return_value = [(run, output)]

        pipeline = EvalPipeline(session=MagicMock(), provider=_StubProvider())
        pipeline.run_all(as_of=_CUTOFF)
        pipeline.run_all(as_of=_CUTOFF)

        assert mock_repo.upsert_eval_result.call_count == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/research/test_eval_pipeline.py -v -k "Pipeline"
```

Expected: `ImportError` for `EvalPipeline`.

- [ ] **Step 3: Add dataclasses and `EvalPipeline` to `src/research/eval_pipeline.py`**

Append to `src/research/eval_pipeline.py` after `apply_rule_v1`:

```python
# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvalTickerResult:
    """Outcome of evaluating a single research run."""

    run_id: uuid.UUID
    ticker: str
    success: bool
    outcome_label: Optional[str] = None
    error: Optional[str] = None


@dataclass
class EvalPipelineResult:
    """Aggregate outcome of a full eval batch."""

    evaluated: int = 0
    failed: int = 0
    skipped: int = 0
    ticker_results: list[EvalTickerResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class EvalPipeline:
    """Orchestrates the full evaluation batch pipeline.

    Parameters
    ----------
    session:
        SQLAlchemy session. Does not commit; callers own transactions.
    provider:
        MarketDataProvider for fetching returns. Defaults to AlpacaMarketDataProvider.
    benchmark_symbol:
        Ticker symbol used for benchmark comparison. Default: 'SPY'.
    neutral_threshold:
        Abs return threshold above which neutral/abstain is labeled wrong_direction.
    """

    def __init__(
        self,
        session: Session,
        provider: Optional[MarketDataProvider] = None,
        benchmark_symbol: str = "SPY",
        neutral_threshold: float = 0.01,
    ) -> None:
        self.session = session
        self.provider = provider or AlpacaMarketDataProvider()
        self.benchmark_symbol = benchmark_symbol
        self.neutral_threshold = neutral_threshold
        self._benchmark_cache: dict[tuple[str, date, int], Optional[float]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_all(self, as_of: Optional[datetime] = None) -> EvalPipelineResult:
        """Evaluate all eligible runs."""
        as_of = as_of or datetime.now(timezone.utc)
        eligible = repository.get_eligible_runs(self.session, as_of_cutoff=as_of)

        if not eligible:
            logger.info("eval_pipeline_no_eligible_runs")
            return EvalPipelineResult()

        logger.info("eval_pipeline_started", run_count=len(eligible))
        result = EvalPipelineResult()

        for run, output in eligible:
            ticker_result = self._eval_run(run, output)
            result.ticker_results.append(ticker_result)
            if ticker_result.success:
                result.evaluated += 1
            else:
                result.failed += 1

        logger.info(
            "eval_pipeline_finished",
            evaluated=result.evaluated,
            failed=result.failed,
        )
        return result

    def run_single(self, run_id: uuid.UUID) -> EvalTickerResult:
        """Force-evaluate a single run by run_id, bypassing eligibility check."""
        run = self.session.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run is None:
            return EvalTickerResult(run_id=run_id, ticker="unknown", success=False, error="run_not_found")
        output = self.session.query(ResearchOutput).filter(ResearchOutput.run_id == run_id).first()
        if output is None:
            return EvalTickerResult(run_id=run_id, ticker=run.ticker, success=False, error="no_output_row")
        return self._eval_run(run, output)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _eval_run(self, run: ResearchRun, output: ResearchOutput) -> EvalTickerResult:
        horizon_map = ResearchTimeHorizon.days_mapping()
        horizon_days = horizon_map.get(output.time_horizon)
        if horizon_days is None:
            logger.warning(
                "eval_pipeline_invalid_horizon",
                run_id=str(run.run_id),
                time_horizon=output.time_horizon,
            )
            return EvalTickerResult(
                run_id=run.run_id,
                ticker=run.ticker,
                success=False,
                error=f"invalid_time_horizon:{output.time_horizon}",
            )

        start_date = run.as_of.date()
        end_date = start_date + timedelta(days=horizon_days)

        realized_return = self._fetch_return(run.ticker, start_date, end_date)
        benchmark_return = self._fetch_benchmark(start_date, end_date, horizon_days)

        outcome_label = apply_rule_v1(
            decision=output.decision,
            realized_return=realized_return,
            benchmark_return=benchmark_return,
            neutral_threshold=self.neutral_threshold,
        )

        repository.upsert_eval_result(
            self.session,
            run_id=run.run_id,
            horizon_days=horizon_days,
            realized_return=realized_return,
            benchmark_return=benchmark_return,
            benchmark_symbol=self.benchmark_symbol,
            evaluation_method=EvaluationMethod.RULE_V1.value,
            evaluation_params=None,
            outcome_label=outcome_label,
        )

        logger.info(
            "eval_pipeline_run_evaluated",
            run_id=str(run.run_id),
            ticker=run.ticker,
            outcome_label=outcome_label,
        )
        return EvalTickerResult(
            run_id=run.run_id,
            ticker=run.ticker,
            success=True,
            outcome_label=outcome_label,
        )

    def _fetch_return(self, ticker: str, start_date: date, end_date: date) -> Optional[float]:
        try:
            return fetch_return_over_range(ticker, start_date, end_date, provider=self.provider)
        except Exception as exc:
            logger.warning(
                "eval_pipeline_fetch_return_failed",
                ticker=ticker,
                error=str(exc),
            )
            return None

    def _fetch_benchmark(self, start_date: date, end_date: date, horizon_days: int) -> Optional[float]:
        cache_key = (self.benchmark_symbol, start_date, horizon_days)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]
        value = self._fetch_return(self.benchmark_symbol, start_date, end_date)
        self._benchmark_cache[cache_key] = value
        return value
```

- [ ] **Step 4: Run all eval pipeline tests**

```bash
pytest tests/research/test_eval_pipeline.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/research/eval_pipeline.py tests/research/test_eval_pipeline.py
git commit -m "feat: add EvalPipeline class with benchmark caching and upsert"
```

---

## Task 5: `scripts/run_eval_once.py` CLI entry point

**Files:**
- Create: `scripts/run_eval_once.py`

### Background

Mirrors `scripts/run_research_once.py`. Accepts `--run-id` for single-run evaluation; no flag evaluates all eligible runs. Prints JSON summary, exits non-zero on any failure.

- [ ] **Step 1: Create `scripts/run_eval_once.py`**

```python
#!/usr/bin/env python3
"""Run the evaluation pipeline once — for all eligible runs or a single run.

Usage examples
--------------
# Evaluate all eligible runs:
python scripts/run_eval_once.py

# Force-evaluate a single run by UUID:
python scripts/run_eval_once.py --run-id <UUID>
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.logging import get_logger
from src.db.connection import get_session
from src.research.eval_pipeline import EvalPipeline, EvalPipelineResult

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Force-evaluate a single research run by UUID.",
    )
    args = parser.parse_args()

    with get_session() as session:
        pipeline = EvalPipeline(session=session)

        if args.run_id:
            try:
                run_id = uuid.UUID(args.run_id)
            except ValueError:
                print(f"Error: invalid UUID '{args.run_id}'", file=sys.stderr)
                return 1

            logger.info("run_eval_once_single_run", run_id=str(run_id))
            ticker_result = pipeline.run_single(run_id)
            pipeline_result = EvalPipelineResult(
                evaluated=1 if ticker_result.success else 0,
                failed=0 if ticker_result.success else 1,
                ticker_results=[ticker_result],
            )
        else:
            logger.info("run_eval_once_all_eligible")
            pipeline_result = pipeline.run_all()

    summary = {
        "evaluated": pipeline_result.evaluated,
        "failed": pipeline_result.failed,
        "skipped": pipeline_result.skipped,
        "runs": [
            {
                "run_id": str(r.run_id),
                "ticker": r.ticker,
                "success": r.success,
                "outcome_label": r.outcome_label,
                "error": r.error,
            }
            for r in pipeline_result.ticker_results
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0 if pipeline_result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the script is importable**

```bash
python -c "import scripts.run_eval_once" 2>&1 || python scripts/run_eval_once.py --help
```

Expected: usage help printed, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_eval_once.py
git commit -m "feat: add run_eval_once.py CLI entry point for eval pipeline"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass, no regressions.

- [ ] **Verify script help**

```bash
python scripts/run_eval_once.py --help
```

Expected: help text displayed.
