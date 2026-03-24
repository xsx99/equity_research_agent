# Same-Day Research Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the research app into a same-day signal iteration workflow: fixed `time_horizon=1d`, one scheduled pre-open research batch, one `16:10 ET` eval batch, formal open-to-close scoring for pre-open runs, and run-time-price-to-close quick scoring for post-open manual runs.

**Architecture:** Keep the current custom orchestration boundary. Enforce `1d` at the prompt and Pydantic output layer, keep the DB schema broad enough to avoid an unnecessary migration, and move same-day eval window selection into repository/eval helpers. Manual quick eval must use the persisted run-time snapshot price for the ticker and a provider-fetched benchmark price from the same timestamp window.

**Tech Stack:** Python, FastAPI, SQLAlchemy ORM, Pydantic, APScheduler, Alpaca market data, pytest

---

## Context And Constraints

- Design reference: `plan/research_app/design_doc.md`
- Architecture reference: `plan/research_app/architecture_recommendation.md`
- Environment: run `source ~/.venv/bin/activate` before Python or pytest commands.
- The user will clear old `3d/5d` data manually, so this change should enforce `1d` at runtime without adding a DB migration just to narrow historical enum values.
- Keep `time_horizon` as a field in prompts, outputs, and UI. Only the current runtime contract changes.
- Do not add a new action schema; `decision + actionability + confidence + invalidators` remains the signal contract.

## File Map

- `src/prompts/templates/research_v1.yaml`
  - Fix prompt instructions so `time_horizon` can only be `1d` and is explicitly same-day feedback.
- `src/agents/research.py`
  - Narrow `StructuredResearchOutput.time_horizon` to `Literal["1d"]`.
- `src/research/pipeline.py`
  - Preserve the run-time `price_snapshot.last_price` in `input_json`; this is the manual quick-eval entry price.
- `src/tools/market_data.py`
  - Add focused helpers for same-day open/close prices and benchmark/timestamp price lookup needed by eval.
- `src/research/repository.py`
  - Replace elapsed-horizon eligibility logic with same-day candidate selection for succeeded `1d` runs.
- `src/research/eval_pipeline.py`
  - Implement dual-window scoring: pre-open `open_to_close`; post-open manual `run_time_price_to_close`.
- `src/core/config.py`
  - Remove the scheduled close research slot and set eval default time to `16:10 ET`.
- `src/scheduler/jobs/research_job.py`
  - Collapse scheduler semantics to a single pre-open research job.
- `scripts/run_scheduler_service.py`
  - Register only the pre-open research job plus eval.
- `src/app.py`
  - Keep manual `/admin/run-now` behavior, but make list/detail aggregation aware of formal vs quick eval metadata.
- `src/templates/research.html`
  - Keep main summary focused on formal eval only.
- `src/templates/research_detail.html`
  - Show eval window metadata for the current run.
- `tests/prompts/test_prompt_registry.py`
  - Add failing coverage for non-`1d` output rejection.
- `tests/research/test_pipeline.py`
  - Update pipeline fixtures to use `1d`.
- `tests/research/test_repository.py`
  - Replace elapsed-window tests with same-day eligibility tests.
- `tests/research/test_eval_pipeline.py`
  - Add formal-vs-quick same-day eval coverage and error cases.
- `tests/tools/test_market_data.py`
  - Add market-data helper coverage for open/close and timestamp price lookup.
- `tests/test_scheduler_jobs.py`
  - Lock in one research job and `16:10 ET` eval.
- `tests/test_app.py`
  - Lock in UI aggregation and detail rendering for eval window metadata.
- `plan/research_app/progress_tracker.md`
  - Record the planning milestone now, then append implementation milestones as tasks complete.

## Task 1: Fix The Runtime Horizon Contract To `1d`

**Files:**
- Modify: `src/prompts/templates/research_v1.yaml`
- Modify: `src/agents/research.py`
- Modify: `tests/prompts/test_prompt_registry.py`
- Modify: `tests/research/test_pipeline.py`
- Modify: `tests/research/test_repository.py`

- [ ] **Step 1: Write the failing tests**

Add or update tests so the runtime contract is explicit:

```python
def test_structured_output_rejects_non_1d_time_horizon():
    payload = {
        "decision": "bullish",
        "confidence": 0.7,
        "time_horizon": "3d",
        "actionability": "actionable",
        "thesis_summary": "Same-day signal only.",
        "key_drivers": ["insider buying"],
        "counterarguments": ["macro risk"],
        "invalidators": ["broad selloff"],
    }

    with pytest.raises(ValidationError):
        StructuredResearchOutput.model_validate(payload)
```

Also update pipeline/repository fixtures so their expected good output uses `1d`, not `3d`.

- [ ] **Step 2: Run the targeted tests and verify they fail for the right reason**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/prompts/test_prompt_registry.py tests/research/test_pipeline.py tests/research/test_repository.py -q
```

Expected:
- at least one failure because the current code still accepts or assumes `3d`
- no unrelated import or environment failures

- [ ] **Step 3: Implement the minimal runtime contract change**

Make the smallest code changes that enforce `1d` at runtime:

```python
class StructuredResearchOutput(BaseModel):
    decision: Literal["bullish", "bearish", "neutral", "abstain"]
    confidence: float = Field(ge=0, le=1)
    time_horizon: Literal["1d"]
    time_horizon_rationale: Optional[str] = None
    actionability: Literal["abstain", "watch", "actionable"]
```

Prompt text should explicitly say `time_horizon: 1d` and describe it as a same-day feedback window.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/prompts/test_prompt_registry.py tests/research/test_pipeline.py tests/research/test_repository.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/prompts/templates/research_v1.yaml src/agents/research.py tests/prompts/test_prompt_registry.py tests/research/test_pipeline.py tests/research/test_repository.py
git commit -m "feat: fix research runtime horizon to 1d"
```

## Task 2: Add Same-Day Eval Price Helpers And Candidate Selection

**Files:**
- Modify: `src/tools/market_data.py`
- Modify: `src/research/repository.py`
- Modify: `tests/tools/test_market_data.py`
- Modify: `tests/research/test_repository.py`

- [ ] **Step 1: Write the failing tests**

Add tests for the two missing pieces:

```python
def test_fetch_price_at_or_before_returns_latest_intraday_price():
    price = fetch_price_at_or_before(
        "SPY",
        datetime(2026, 3, 24, 14, 37, tzinfo=timezone.utc),
        provider=stub_provider,
    )
    assert price == pytest.approx(512.25)


def test_get_same_day_eval_candidates_only_returns_succeeded_1d_runs_for_trade_date():
    results = repository.get_same_day_eval_candidates(session, trade_date=date(2026, 3, 24))
    assert results == [(run, output)]
```

The repository test should filter out:
- failed runs
- runs with missing output rows
- runs not on the requested trade date
- runs with non-`1d` outputs if stale data still exists

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py tests/research/test_repository.py -q
```

Expected:
- failures because `fetch_price_at_or_before` and `get_same_day_eval_candidates` do not exist yet

- [ ] **Step 3: Implement the minimal helper layer**

Add focused helpers instead of over-generalizing:

```python
class MarketDataProvider(Protocol):
    def fetch_price_at_or_before(self, ticker: str, as_of: datetime) -> Optional[float]:
        ...


def fetch_open_to_close_return(ticker: str, trading_date: date, provider: Optional[MarketDataProvider] = None) -> Optional[float]:
    ...


def fetch_close_price_on_date(ticker: str, trading_date: date, provider: Optional[MarketDataProvider] = None) -> Optional[float]:
    ...
```

Repository candidate selection should be explicit and name the new semantics:

```python
def get_same_day_eval_candidates(session: Session, trade_date: date) -> list[tuple[ResearchRun, ResearchOutput]]:
    ...
```

Do not delete `time_horizon` from storage. Do not add a migration.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/tools/test_market_data.py tests/research/test_repository.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/market_data.py src/research/repository.py tests/tools/test_market_data.py tests/research/test_repository.py
git commit -m "feat: add same-day eval price helpers"
```

## Task 3: Implement Dual-Track Same-Day Eval Logic

**Files:**
- Modify: `src/research/eval_pipeline.py`
- Modify: `tests/research/test_eval_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add tests for both same-day windows and their metadata:

```python
def test_pre_open_run_uses_open_to_close_window():
    run = _make_run(as_of=datetime(2026, 3, 24, 13, 20, tzinfo=timezone.utc))  # 9:20 ET
    output = _make_output(time_horizon="1d")
    ...
    assert call_kwargs["evaluation_params"]["price_window"] == "open_to_close"


def test_post_open_manual_run_uses_run_snapshot_price_to_close():
    run = _make_run(
        as_of=datetime(2026, 3, 24, 15, 15, tzinfo=timezone.utc),
        input_json={"price_snapshot": {"last_price": 150.0}},
    )
    ...
    assert call_kwargs["realized_return"] == pytest.approx((153.0 / 150.0) - 1)
    assert call_kwargs["evaluation_params"]["price_window"] == "run_time_price_to_close"
    assert call_kwargs["evaluation_params"]["entry_price_source"] == "research_input_last_price"
```

Cover these failure cases:
- missing `input_json.price_snapshot.last_price` on a post-open run
- missing benchmark timestamp price
- missing close price
- admin re-run still uses `upsert_eval_result` without duplicating rows

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/research/test_eval_pipeline.py -q
```

Expected:
- failures because eval still assumes elapsed `1d/3d/5d` close-to-close logic

- [ ] **Step 3: Implement the minimal dual-track eval logic**

Implementation rules:

```python
if run_is_before_regular_open(run.as_of):
    price_window = "open_to_close"
    realized_return = fetch_open_to_close_return(run.ticker, trade_date, provider=self.provider)
    benchmark_return = fetch_open_to_close_return(self.benchmark_symbol, trade_date, provider=self.provider)
else:
    price_window = "run_time_price_to_close"
    entry_price = run.input_json["price_snapshot"]["last_price"]
    exit_price = fetch_close_price_on_date(run.ticker, trade_date, provider=self.provider)
    benchmark_entry = fetch_price_at_or_before(self.benchmark_symbol, run.as_of, provider=self.provider)
    benchmark_exit = fetch_close_price_on_date(self.benchmark_symbol, trade_date, provider=self.provider)
```

Persist metadata in `evaluation_params` at minimum:

```python
{
    "price_window": "open_to_close" | "run_time_price_to_close",
    "entry_price_source": "...",
    "exit_price_source": "session_close",
    "benchmark_entry_price_source": "...",
}
```

Keep `evaluation_method="rule_v1"`; use `evaluation_params` to distinguish the window.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/research/test_eval_pipeline.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/research/eval_pipeline.py tests/research/test_eval_pipeline.py
git commit -m "feat: add same-day dual-track eval windows"
```

## Task 4: Simplify Scheduler Semantics To One Research Batch And `16:10 ET` Eval

**Files:**
- Modify: `src/core/config.py`
- Modify: `src/scheduler/jobs/research_job.py`
- Modify: `scripts/run_scheduler_service.py`
- Modify: `tests/test_scheduler_jobs.py`

- [ ] **Step 1: Write the failing tests**

Add or update scheduler tests so the intended runtime is locked in:

```python
def test_research_job_trigger_is_pre_open_only():
    cfg = ResearchJob().config
    assert cfg.trigger_kwargs["hour"] == 9
    assert cfg.trigger_kwargs["minute"] == 20


def test_eval_job_trigger_is_1610_et():
    cfg = EvalJob().config
    assert cfg.trigger_kwargs["hour"] == 16
    assert cfg.trigger_kwargs["minute"] == 10
```

Delete tests that still assume `ResearchJob("close")`.

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/test_scheduler_jobs.py -q
```

Expected:
- failures because the code still exposes and registers the close research slot
- eval still defaults to `18:00 ET`

- [ ] **Step 3: Implement the minimal scheduler change**

Simplify instead of preserving dead configuration:

```python
RESEARCH_SCHEDULE_HOUR = 9
RESEARCH_SCHEDULE_MINUTE = 20
EVAL_SCHEDULE_HOUR = 16
EVAL_SCHEDULE_MINUTE = 10
```

`ResearchJob` should become a single pre-open job, and `scripts/run_scheduler_service.py` should register only:

```python
SchedulerService(jobs=[
    SECEdgarJob(),
    ResearchJob(),
    EvalJob(),
]).start()
```

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/test_scheduler_jobs.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py src/scheduler/jobs/research_job.py scripts/run_scheduler_service.py tests/test_scheduler_jobs.py
git commit -m "feat: simplify same-day research scheduler"
```

## Task 5: Surface Formal Vs Quick Eval Cleanly In The App

**Files:**
- Modify: `src/app.py`
- Modify: `src/templates/research.html`
- Modify: `src/templates/research_detail.html`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Add app-level tests that lock in two UI rules:

```python
def test_research_list_aggregate_ignores_manual_quick_eval():
    ...
    assert "wrong_direction" not in rendered_summary_from_manual_only_rows


def test_research_detail_shows_eval_window_metadata():
    ...
    assert "run_time_price_to_close" in response.text
```

At minimum, detail should show:
- current eval window name
- realized return
- benchmark return
- benchmark symbol

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/test_app.py -q
```

Expected:
- failures because current list aggregation counts every eval result
- detail page does not yet expose eval window metadata

- [ ] **Step 3: Implement the minimal UI behavior**

Keep the main list simple:
- aggregate only eval rows whose `evaluation_params.price_window == "open_to_close"`
- do not create a second dashboard

Detail page should expose the current run's eval metadata pulled from `EvalResult.evaluation_params`.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/test_app.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/templates/research.html src/templates/research_detail.html tests/test_app.py
git commit -m "feat: distinguish formal and quick eval in UI"
```

## Task 6: Final Verification, Docs, And Tracking

**Files:**
- Modify: `plan/research_app/progress_tracker.md`
- Modify: `documents/research_app_runbook.md`
- Modify: `documents/research_app_deploy.md`
- Modify: `documents/repo_overview.md` if the implementation ends up being a major refactor

- [ ] **Step 1: Update runbook and deploy docs**

Document:
- scheduled research at `9:20 ET`
- scheduled eval at `16:10 ET`
- manual run semantics after `9:30 ET`
- requirement that manual quick eval uses persisted run-time ticker price
- how to manually run research and eval in sequence for same-day testing

- [ ] **Step 2: Update the progress tracker**

Append the completed implementation bullets under the current date in:

```markdown
## 2026-03-24

- Finalized the same-day iteration implementation plan: fixed runtime `time_horizon=1d`, one pre-open research batch, `16:10 ET` eval, formal pre-open `open_to_close` scoring, and post-open manual `run_time_price_to_close` quick eval.
```

Add further bullets only after each implementation task is actually completed.

- [ ] **Step 3: Run the focused test suite**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/prompts/test_prompt_registry.py tests/research/test_pipeline.py tests/research/test_repository.py tests/research/test_eval_pipeline.py tests/tools/test_market_data.py tests/test_scheduler_jobs.py tests/test_app.py -q
```

Expected: PASS

- [ ] **Step 4: Run the full unit suite**

Run:

```bash
source ~/.venv/bin/activate && pytest -q
```

Expected: PASS

- [ ] **Step 5: Optional smoke checks if API credentials are available**

Run:

```bash
source ~/.venv/bin/activate && python scripts/run_research_once.py --ticker AAPL
source ~/.venv/bin/activate && python scripts/run_eval_once.py
```

Expected:
- research run writes `research_runs` and `research_outputs`
- eval writes `eval_results` with `evaluation_params.price_window`

- [ ] **Step 6: Commit**

```bash
git add plan/research_app/progress_tracker.md documents/research_app_runbook.md documents/research_app_deploy.md documents/repo_overview.md
git commit -m "docs: record same-day iteration workflow"
```

## Suggested Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6

## Notes For The Implementer

- Prefer renaming repository helpers instead of silently changing the semantics of `get_eligible_runs`; the old name encodes elapsed-window logic that will no longer be true.
- Do not try to solve position management in this change. This feature is only about signal generation plus same-day feedback.
- Keep manual quick eval and formal eval separated in persisted metadata and UI summaries; they are both useful, but not interchangeable.
- If Alpaca intraday timestamp lookup becomes flaky, make the helper return `None` and let eval persist a null outcome rather than fabricating a price.
