# PR 52: Long-Horizon Reflection And Strategy Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reflection and strategy evolution use multi-day, horizon-aware evidence so post-close learning is not overfit to one trading day's moves.

**Architecture:** Keep same-day reflection useful for operator review, but add bounded historical context and explicit evidence labels so the agent separates daily noise, interim horizon marks, and final horizon outcomes. Strategy evolution will consume a trailing evidence window and must pass deterministic Python gates before a new strategy definition is accepted or moved to `shadow`; the LLM proposes hypotheses and cites supporting outcome ids, but Python decides whether evidence is sufficient.

**Tech Stack:** Python, Pydantic, SQLAlchemy, Alembic, Postgres JSONB, existing `PromptRegistry`, pytest, existing post-close phase packages.

---

## Required Reading

Read these before implementation:

- `documents/general_instructions.md`
- `plan/implementation/README.md`
- `plan/design/07_replay_reflection_learning.md`
- `plan/implementation/pr_09_reflection_learning_factors.md`
- `plan/implementation/pr_10_strategy_evolution.md`
- Current code:
  - `src/agents/prompts/trading/reflection_v1.yaml`
  - `src/agents/prompts/trading/strategy_evolution_v1.yaml`
  - `src/agents/reflection_schemas.py`
  - `src/agents/strategy_evolution_schemas.py`
  - `src/trading/phases/reflection/pipeline.py`
  - `src/trading/phases/strategy_evolution/pipeline.py`
  - `src/trading/repositories/mixins/reflection.py`
  - `src/trading/repositories/mixins/strategy.py`

## Scope

In scope:

- Add long-horizon context to reflection input.
- Expand strategy evolution input from same-day artifacts to a bounded historical window.
- Require LLM strategy proposals to cite supporting `candidate_outcome_evaluation_id` values.
- Add deterministic evidence gates for new proposal acceptance and strategy lifecycle promotion.
- Preserve current safe behavior: no active/experimental strategy should be created directly by the LLM.
- Persist rejected proposals when evidence is insufficient, with metrics in `metadata_json`.

Out of scope:

- Rebuilding the historical replay evaluator.
- Adding new source data families.
- New UI design. Existing System/Learning surfaces only need enough serialized metadata to diagnose rejected proposals.
- Live external API calls. Unit tests use fakes; any DB smoke is read-only unless explicitly approved later.

## Evidence Policy

Use these defaults unless implementation discovers a stronger existing config surface:

```python
LONG_HORIZON_LOOKBACK_DAYS = 60
MIN_FINAL_OUTCOMES_FOR_PROPOSAL = 3
MIN_DISTINCT_TRADE_DATES_FOR_PROPOSAL = 3
MIN_DISTINCT_TICKERS_FOR_PROPOSAL = 2
MIN_PROPOSAL_WIN_RATE = 0.60
MIN_PROPOSAL_MEAN_ALPHA = 0.0
```

Rules:

- `interim` rows may appear in prompt context, but cannot satisfy proposal or promotion evidence gates.
- Same-day rows may contribute to daily reflection, but cannot alone justify new strategy creation.
- A proposal without valid `supporting_outcome_ids` is `insufficient_evidence_rejected`.
- Missing supporting outcome ids are a rejection, not a fallback.
- Sector/theme concentration should be recorded in metrics. Do not block sector-specific strategies solely because all rows share a sector, but the prompt must call out when alpha may only be a sector tailwind.

## File Structure

- Modify `src/agents/prompts/trading/reflection_v1.yaml`
  - Add explicit horizon-aware evidence labels and anti-overfit instructions.
- Modify `src/agents/prompts/trading/strategy_evolution_v1.yaml`
  - Require multi-day support and `supporting_outcome_ids`.
- Modify `src/agents/reflection_schemas.py`
  - Add optional historical context fields accepted by the reflection agent.
- Modify `src/agents/strategy_evolution_schemas.py`
  - Add `supporting_outcome_ids` and optional evidence reference fields to proposals.
- Create `src/trading/phases/strategy_evolution/evidence.py`
  - Own evidence policy constants, metrics, and gate helpers.
- Modify `src/trading/phases/reflection/pipeline.py`
  - Carry historical context from runtime/repository into LLM input.
- Modify `src/trading/phases/strategy_evolution/pipeline.py`
  - Include evidence policy in prompt input, validate proposals with deterministic gate, and harden lifecycle promotion gates.
- Modify `src/trading/phases/strategy_evolution/__init__.py`
  - Ensure loader skip logic still requires a current-day reflection even when historical reflections are returned.
- Modify `src/trading/repositories/mixins/reflection.py`
  - Load bounded prior reflections and prior outcome context.
- Modify `src/trading/repositories/mixins/strategy.py`
  - Load trailing-window strategy-evolution inputs.
- Modify `src/db/models/trading/enums.py`
  - Add `INSUFFICIENT_EVIDENCE_REJECTED`.
- Create Alembic migration under `alembic/versions/`
  - Update `ck_strategy_proposals_status`.
- Modify `src/web/routers/loaders/universe_learning.py`
  - Expose `metadata_json.evidence_gate` for proposals.
- Modify `src/web/presenters/today_learning_strategies.py`
  - Rank `insufficient_evidence_rejected` with other rejected statuses.
- Tests:
  - Create `tests/agents/test_post_close_prompt_contracts.py`
  - Modify `tests/agents/test_strategy_evolution_agent.py`
  - Modify `tests/trading/test_reflection_pipeline.py`
  - Modify `tests/trading/test_runtime_strategy_evolution_live.py`
  - Modify `tests/trading/test_strategy_evolution.py`
  - Modify `tests/trading/test_strategy_lifecycle.py`
  - Modify `tests/trading/test_sqlalchemy_repository.py`
  - Modify `tests/db/test_trading_models.py`
  - Modify `tests/web/test_today_learning_strategies.py`
  - Modify `tests/web/test_today.py` only if loader-level proposal serialization coverage currently lives there.

---

### Task 1: Prompt And Output Contracts

**Files:**
- Create: `tests/agents/test_post_close_prompt_contracts.py`
- Modify: `tests/agents/test_strategy_evolution_agent.py`
- Modify: `src/agents/prompts/trading/reflection_v1.yaml`
- Modify: `src/agents/prompts/trading/strategy_evolution_v1.yaml`
- Modify: `src/agents/strategy_evolution_schemas.py`

- [ ] **Step 1: Write prompt contract tests**

Add tests that load the real prompt files and assert the anti-overfit terms are present.

```python
from src.agents.prompt_registry import PromptRegistry
from src.agents.prompt_registry import PROMPTS_ROOT


def test_reflection_prompt_requires_horizon_aware_evidence_labels():
    template = PromptRegistry(root=PROMPTS_ROOT).load("reflection", "v1").template

    assert "single_day_noise" in template
    assert "interim_horizon_mark" in template
    assert "final_horizon_evidence" in template
    assert "Do not infer a durable strategy edge from one trade date" in template


def test_strategy_evolution_prompt_requires_multi_day_supporting_outcomes():
    template = PromptRegistry(root=PROMPTS_ROOT).load("strategy_evolution", "v1").template

    assert "supporting_outcome_ids" in template
    assert "at least 3 final outcome rows" in template
    assert "at least 3 distinct trade dates" in template
    assert "Return an empty proposals array" in template
```

- [ ] **Step 2: Write schema test for proposal supporting ids**

In `tests/agents/test_strategy_evolution_agent.py`, add:

```python
from src.agents.strategy_evolution_schemas import StrategyEvolutionOutput


def test_strategy_evolution_output_accepts_supporting_outcome_ids():
    output = StrategyEvolutionOutput.model_validate(
        {
            "proposals": [
                {
                    "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                    "display_name": "Post-Gap VWAP Reclaim",
                    "source_reflection_ids": ["reflection-1"],
                    "supporting_outcome_ids": ["outcome-1", "outcome-2", "outcome-3"],
                    "core_thesis": "Gap fades that reclaim VWAP can continue.",
                    "typical_horizon": "intraday-3d",
                    "required_signals": ["opening_gap_pct", "vwap_reclaim", "relative_volume"],
                    "optional_signals": [],
                    "scoring_rules": {},
                    "risk_tags": ["gap_risk"],
                    "macro_blocked_regimes": [],
                    "invalidators": ["loses VWAP"],
                    "evidence_summary": "Three final rows across three dates beat QQQ.",
                }
            ],
            "schema_version": "v1",
            "generated_at": "2026-06-02T22:00:00+00:00",
        }
    )

    assert output.proposals[0].supporting_outcome_ids == ["outcome-1", "outcome-2", "outcome-3"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/agents/test_post_close_prompt_contracts.py tests/agents/test_strategy_evolution_agent.py -q
```

Expected: failures for missing prompt text and missing `supporting_outcome_ids` field.

- [ ] **Step 4: Update schemas and prompts**

In `src/agents/strategy_evolution_schemas.py`, add defaults so older fallback content still validates when needed:

```python
class StrategyProposalOutputItem(BaseModel):
    ...
    supporting_outcome_ids: list[str] = Field(default_factory=list)
    supporting_learning_factor_keys: list[str] = Field(default_factory=list)
```

In `reflection_v1.yaml`, add requirements that:

- evidence must be labeled as `single_day_noise`, `interim_horizon_mark`, `final_horizon_evidence`, or `repeated_pattern`;
- `what_worked`, `what_failed`, `learning_factors`, and `strategy_proposal_hints` must not imply durable behavior from one trade date;
- interim rows are useful for monitoring but not final proof;
- the model must compare returns to benchmark, peer basket, and sector/theme context where present.

In `strategy_evolution_v1.yaml`, update the JSON shape to include:

```json
"supporting_outcome_ids": ["candidate-outcome-id-1"]
```

Add rules that proposals require at least 3 final outcome rows across at least 3 distinct trade dates, and that the model should return `"proposals": []` when the evidence is only same-day or interim.

- [ ] **Step 5: Run prompt/schema tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/agents/test_post_close_prompt_contracts.py tests/agents/test_strategy_evolution_agent.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add tests/agents/test_post_close_prompt_contracts.py tests/agents/test_strategy_evolution_agent.py src/agents/prompts/trading/reflection_v1.yaml src/agents/prompts/trading/strategy_evolution_v1.yaml src/agents/strategy_evolution_schemas.py
git commit -m "plan-followup: add post-close long-horizon prompt contracts"
```

---

### Task 2: Reflection Historical Context

**Files:**
- Modify: `tests/trading/test_reflection_pipeline.py`
- Modify: `tests/trading/test_sqlalchemy_repository.py`
- Modify: `src/agents/reflection_schemas.py`
- Modify: `src/trading/phases/reflection/pipeline.py`
- Modify: `src/trading/repositories/mixins/reflection.py`

- [ ] **Step 1: Write reflection pipeline test**

Extend `test_reflection_pipeline_passes_option_and_hedge_payloads_to_agent` or add a focused test:

```python
def test_reflection_pipeline_passes_long_horizon_context_to_agent(tmp_path):
    ...
    request = _request()
    request = ReflectionPipelineRequest(
        **{
            **request.__dict__,
            "historical_outcome_context": (
                {"ticker": "AAPL", "strategy_id": "gap_reclaim_v1", "evaluation_status": "final", "alpha": 0.03},
            ),
            "prior_reflection_context": (
                {"trade_date": "2026-05-31", "what_failed": ["single-day chase"]},
            ),
        }
    )

    pipeline.run(request=request)

    assert captured["historical_outcome_context"][0]["ticker"] == "AAPL"
    assert captured["prior_reflection_context"][0]["trade_date"] == "2026-05-31"
```

- [ ] **Step 2: Write repository lookback test**

In `tests/trading/test_sqlalchemy_repository.py`, add a test that creates:

- one same-day `CandidateOutcomeEvaluation` row;
- one prior row inside 60 days;
- one prior row older than 60 days;
- one prior `DailyReflection` inside 60 days;
- current trade date `2026-06-30`.

Assert:

```python
payload = repository.load_reflection_inputs(trade_date=trade_date, window=window)

assert [row["ticker"] for row in payload["candidate_outcome_evaluations"]] == ["TODAY"]
assert [row["ticker"] for row in payload["historical_outcome_context"]] == ["PRIOR_IN_WINDOW"]
assert payload["prior_reflection_context"][0]["trade_date"] == "2026-06-20"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_reflection_pipeline.py::test_reflection_pipeline_passes_long_horizon_context_to_agent tests/trading/test_sqlalchemy_repository.py -q -k 'reflection_inputs or long_horizon_context'
```

Expected: failures for missing dataclass/schema fields and missing repository keys.

- [ ] **Step 4: Add reflection input fields**

In `src/agents/reflection_schemas.py`, add:

```python
historical_outcome_context: list[dict[str, Any]] = Field(default_factory=list)
prior_reflection_context: list[dict[str, Any]] = Field(default_factory=list)
```

In `src/trading/phases/reflection/pipeline.py`, add matching `ReflectionPipelineRequest` tuple fields and include them in the payload passed to `ReflectionAgent`.

- [ ] **Step 5: Load historical reflection context**

In `src/trading/repositories/mixins/reflection.py`:

- compute `lookback_start_utc` from `trade_date - 60 days` using `local_day_bounds_utc`;
- keep existing same-day `candidate_outcome_evaluations` behavior unchanged;
- add `historical_outcome_context` from rows where `decision_time >= lookback_start_utc` and `< start_utc`;
- add `prior_reflection_context` from `DailyReflection.trade_date < trade_date` and `>= trade_date - 60 days`;
- keep payloads compact: include existing `_candidate_outcome_payload(row)` for outcomes and a small dict for reflections:

```python
{
    "daily_reflection_id": str(row.daily_reflection_id),
    "trade_date": row.trade_date.isoformat(),
    "status": row.status,
    "what_worked": list((row.reflection_json or {}).get("what_worked") or ()),
    "what_failed": list((row.reflection_json or {}).get("what_failed") or ()),
    "strategy_proposal_hints": list(row.strategy_proposal_hints_json or ()),
}
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_reflection_pipeline.py tests/trading/test_sqlalchemy_repository.py -q -k 'reflection'
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add tests/trading/test_reflection_pipeline.py tests/trading/test_sqlalchemy_repository.py src/agents/reflection_schemas.py src/trading/phases/reflection/pipeline.py src/trading/repositories/mixins/reflection.py
git commit -m "plan-followup: add long-horizon context to reflection"
```

---

### Task 3: Strategy Evolution Historical Input Window

**Files:**
- Modify: `tests/trading/test_runtime_strategy_evolution_live.py`
- Modify: `tests/trading/test_sqlalchemy_repository.py`
- Modify: `src/trading/phases/strategy_evolution/__init__.py`
- Modify: `src/trading/repositories/mixins/strategy.py`

- [ ] **Step 1: Write loader skip test for missing current reflection**

The repository will start returning historical reflections. The live loader must still skip if the current trade date has no reflection.

```python
def test_live_strategy_evolution_loader_requires_current_day_reflection():
    decision_time = datetime(2026, 6, 4, 22, 30, tzinfo=timezone.utc)
    loader = LiveStrategyEvolutionRequestLoader(
        repository=_Repository(
            {
                "daily_reflections": (
                    SimpleNamespace(
                        daily_reflection_id="reflection-old",
                        trade_date=date(2026, 6, 3),
                        status="succeeded",
                        strategy_proposal_hints=(),
                        metadata_json={},
                    ),
                ),
                "learning_factors": (),
                "rejected_candidates": (),
                "candidate_outcome_evaluations": (),
            }
        )
    )

    result = loader.load(trade_date=date(2026, 6, 4), decision_time=decision_time)

    assert result.status == "skipped"
    assert result.reasons == ("daily_reflection_missing",)
```

- [ ] **Step 2: Write repository strategy-evolution window test**

In `tests/trading/test_sqlalchemy_repository.py`, create current-day and prior rows. Assert `load_strategy_evolution_inputs()` includes in-window historical rows and excludes older rows.

Assertions:

```python
payload = repository.load_strategy_evolution_inputs(trade_date=date(2026, 6, 30))

assert [row.daily_reflection_id for row in payload["daily_reflections"]] == [
    str(current_reflection_id),
    str(prior_reflection_id),
]
assert {row.factor_key for row in payload["learning_factors"]} == {"lf-current", "lf-prior"}
assert {row.ticker for row in payload["candidate_outcome_evaluations"]} == {"TODAY", "PRIOR_IN_WINDOW"}
assert {row["ticker"] for row in payload["rejected_candidates"]} == {"TODAY_REJECT", "PRIOR_REJECT"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_runtime_strategy_evolution_live.py::test_live_strategy_evolution_loader_requires_current_day_reflection tests/trading/test_sqlalchemy_repository.py -q -k 'strategy_evolution_inputs or current_day_reflection'
```

Expected: loader accepts historical-only reflections, and repository only returns same-day rows.

- [ ] **Step 4: Update loader current-day check**

In `src/trading/phases/strategy_evolution/__init__.py`, replace the current `if not daily_reflections` check with:

```python
current_reflections = tuple(
    reflection
    for reflection in daily_reflections
    if getattr(reflection, "trade_date", None) == trade_date
)
if not current_reflections:
    return StrategyEvolutionLoadResult(
        status="skipped",
        request=None,
        reasons=("daily_reflection_missing",),
    )
```

Pass the full `daily_reflections` tuple into the request once a current-day reflection exists.

- [ ] **Step 5: Update repository strategy-evolution inputs**

In `src/trading/repositories/mixins/strategy.py`:

- compute a 60-day lookback start;
- query `DailyReflection.trade_date >= start_date` and `<= trade_date`;
- sort records newest first, current trade date first;
- query `LearningFactor.trade_date` over the same date window;
- query rejected `CandidateScore` rows by UTC decision window from lookback start to current day end;
- query `CandidateOutcomeEvaluation` rows by the same UTC window;
- keep existing `_daily_reflection_record`, `_learning_factor_record`, `_rejected_candidate_payload`, and `_candidate_outcome_record` adapters.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_runtime_strategy_evolution_live.py tests/trading/test_sqlalchemy_repository.py -q -k 'strategy_evolution'
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add tests/trading/test_runtime_strategy_evolution_live.py tests/trading/test_sqlalchemy_repository.py src/trading/phases/strategy_evolution/__init__.py src/trading/repositories/mixins/strategy.py
git commit -m "plan-followup: load long-horizon strategy evolution inputs"
```

---

### Task 4: Deterministic Evidence Gate For Proposals

**Files:**
- Create: `src/trading/phases/strategy_evolution/evidence.py`
- Modify: `tests/trading/test_strategy_evolution.py`
- Modify: `tests/trading/test_strategy_lifecycle.py`
- Modify: `src/trading/phases/strategy_evolution/pipeline.py`

- [ ] **Step 1: Write evidence helper tests**

Create tests in `tests/trading/test_strategy_evolution.py` or a new focused `tests/trading/test_strategy_evolution_evidence.py`.

Minimum cases:

```python
def test_proposal_evidence_gate_rejects_single_day_outcomes():
    metrics = evaluate_proposal_evidence(
        supporting_outcome_ids=("outcome-1", "outcome-2", "outcome-3"),
        outcomes=(same_day_outcome_1, same_day_outcome_2, same_day_outcome_3),
        policy=EvidenceGatePolicy(),
    )

    assert metrics.passed is False
    assert metrics.reason_code == "insufficient_distinct_trade_dates"


def test_proposal_evidence_gate_accepts_multi_day_positive_alpha():
    metrics = evaluate_proposal_evidence(
        supporting_outcome_ids=("outcome-1", "outcome-2", "outcome-3"),
        outcomes=(day_1_positive, day_2_positive, day_3_negative),
        policy=EvidenceGatePolicy(),
    )

    assert metrics.passed is True
    assert metrics.metrics_json["final_outcome_count"] == 3
    assert metrics.metrics_json["distinct_trade_dates"] == 3
    assert metrics.metrics_json["win_rate"] >= 0.6
```

- [ ] **Step 2: Write pipeline rejection test**

Update the existing accepted-proposal test. First add a new failing test:

```python
def test_strategy_evolution_pipeline_rejects_proposal_with_only_same_day_evidence(tmp_path):
    pipeline = StrategyEvolutionPipeline(...)
    result = pipeline.run(request=_request_with_three_same_day_outcomes())

    assert result.strategy_proposals[0].proposal_status == "insufficient_evidence_rejected"
    assert result.strategy_proposals[0].rejection_reason == "insufficient_distinct_trade_dates"
    assert result.strategy_definitions == ()
    assert result.strategy_proposals[0].metadata_json["evidence_gate"]["passed"] is False
```

- [ ] **Step 3: Write accepted-proposal test with multi-day supporting ids**

Change `test_strategy_evolution_pipeline_creates_shadow_strategy_from_unique_proposal` so the request contains at least 3 final rows over 3 distinct dates and at least 2 tickers. The LLM fixture must return matching `supporting_outcome_ids`.

Expected:

```python
assert result.strategy_proposals[0].proposal_status == "accepted"
assert result.strategy_proposals[0].metadata_json["evidence_gate"]["passed"] is True
assert result.strategy_definitions[0].lifecycle_status == "shadow"
```

- [ ] **Step 4: Harden lifecycle promotion tests**

In `tests/trading/test_strategy_lifecycle.py`, add cases proving `maybe_promote_strategy_from_outcomes()` does not promote when:

- the three final outcomes are all on one trade date;
- the three final outcomes are one ticker repeated;
- win rate is below 60%;
- mean alpha is non-positive.

Keep the existing positive promotion test, but make its fixture use 3 distinct dates and at least 2 tickers.

- [ ] **Step 5: Run tests to verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_strategy_evolution.py tests/trading/test_strategy_lifecycle.py -q
```

Expected: failures because helper/module/status do not exist and old pipeline accepts same-day evidence.

- [ ] **Step 6: Implement evidence helper**

Create `src/trading/phases/strategy_evolution/evidence.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from src.trading.phases.replay.outcomes import CandidateOutcomeEvaluationRecord


@dataclass(frozen=True)
class EvidenceGatePolicy:
    min_final_outcomes: int = 3
    min_distinct_trade_dates: int = 3
    min_distinct_tickers: int = 2
    min_win_rate: float = 0.60
    min_mean_alpha: float = 0.0


@dataclass(frozen=True)
class EvidenceGateResult:
    passed: bool
    reason_code: str
    metrics_json: dict[str, object]


def evaluate_proposal_evidence(
    *,
    supporting_outcome_ids: Iterable[str],
    outcomes: Iterable[CandidateOutcomeEvaluationRecord],
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> EvidenceGateResult:
    ...
```

Implementation details:

- Index outcomes by `candidate_outcome_evaluation_id`.
- Reject empty `supporting_outcome_ids`.
- Reject missing ids.
- Count only `evaluation_status == "final"`.
- Derive trade dates from `decision_time.date()`.
- Use alpha values where `alpha is not None`.
- `win_rate = count(alpha > 0) / count(alpha not None)`.
- Include `distinct_regimes`, `distinct_sector_themes`, and `interim_outcome_count` in metrics.

- [ ] **Step 7: Gate new proposal acceptance**

In `src/trading/phases/strategy_evolution/pipeline.py`, before duplicate detection or definition creation:

```python
gate = evaluate_proposal_evidence(
    supporting_outcome_ids=proposal_json.get("supporting_outcome_ids", ()),
    outcomes=request.candidate_outcome_evaluations,
)
if not gate.passed:
    proposal = StrategyProposalRecord(
        ...,
        proposal_status="insufficient_evidence_rejected",
        proposed_lifecycle_status=None,
        rejection_reason=gate.reason_code,
        metadata_json={"evidence_gate": gate.metrics_json},
    )
    self.repository.save_strategy_proposal(proposal)
    proposals.append(proposal)
    continue
```

Run duplicate detection after evidence passes so a weak duplicate does not become an accepted duplicate. If the implementation team prefers to detect duplicates first, it must still persist evidence metrics in duplicate rows; document that choice in the commit message.

- [ ] **Step 8: Harden lifecycle promotion gates**

Update `maybe_promote_strategy_from_outcomes()` to reuse evidence metrics for existing strategies:

- Use all final outcomes for that strategy.
- Require the same distinct-date, ticker, alpha, and win-rate gates before promoting `shadow -> experimental` or `experimental -> active`.
- Preserve the stronger active promotion mean-alpha threshold currently used for `experimental -> active` (`mean_alpha > 0.01`) in addition to the shared gate.

- [ ] **Step 9: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_strategy_evolution.py tests/trading/test_strategy_lifecycle.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add src/trading/phases/strategy_evolution/evidence.py src/trading/phases/strategy_evolution/pipeline.py tests/trading/test_strategy_evolution.py tests/trading/test_strategy_lifecycle.py
git commit -m "plan-followup: gate strategy evolution on multi-day evidence"
```

---

### Task 5: Persist Rejection Status And Surface Evidence Metrics

**Files:**
- Modify: `tests/db/test_trading_models.py`
- Modify: `tests/web/test_today_learning_strategies.py`
- Modify: `tests/web/test_today.py` if needed for loader coverage
- Modify: `src/db/models/trading/enums.py`
- Modify: `src/web/routers/loaders/universe_learning.py`
- Modify: `src/web/presenters/today_learning_strategies.py`
- Create: `alembic/versions/0XX_strategy_proposal_insufficient_evidence_status.py`

- [ ] **Step 1: Write enum/model test**

In `tests/db/test_trading_models.py`, update:

```python
assert StrategyProposalStatus.choices() == (
    "accepted",
    "duplicate_rejected",
    "proposal_failed",
    "insufficient_evidence_rejected",
)
```

Also instantiate `StrategyProposal(proposal_status="insufficient_evidence_rejected", rejection_reason="insufficient_final_outcomes")`.

- [ ] **Step 2: Write loader/presenter test**

Use the existing strategy proposal loader/presenter tests to assert:

```python
assert proposal["proposal_status_label"] == "Insufficient Evidence Rejected"
assert proposal["evidence_gate"]["final_outcome_count"] == 2
```

For presenter rank:

```python
assert _proposal_status_rank({"proposal_status": "insufficient_evidence_rejected"})[0] < 99
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/web/test_today_learning_strategies.py tests/web/test_today.py -q -k 'StrategyProposalStatus or strategy_proposal or evidence_gate'
```

Expected: enum/status and loader metadata failures.

- [ ] **Step 4: Update enum and migration**

In `src/db/models/trading/enums.py`:

```python
class StrategyProposalStatus(ChoiceEnum):
    ACCEPTED = "accepted"
    DUPLICATE_REJECTED = "duplicate_rejected"
    PROPOSAL_FAILED = "proposal_failed"
    INSUFFICIENT_EVIDENCE_REJECTED = "insufficient_evidence_rejected"
```

Create an Alembic revision that drops and recreates `ck_strategy_proposals_status` with the expanded set. Name it after the next revision number, not literally `0XX`.

- [ ] **Step 5: Expose proposal evidence metadata**

In `src/web/routers/loaders/universe_learning.py`, add:

```python
"evidence_gate": dict((row.metadata_json or {}).get("evidence_gate") or {}),
```

In `src/web/presenters/today_learning_strategies.py`, add rank:

```python
"insufficient_evidence_rejected": 3,
```

Adjust existing ranks so `proposal_failed` remains lowest priority.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/web/test_today_learning_strategies.py tests/web/test_today.py -q -k 'StrategyProposalStatus or strategy_proposal or evidence_gate'
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add tests/db/test_trading_models.py tests/web/test_today_learning_strategies.py tests/web/test_today.py src/db/models/trading/enums.py src/web/routers/loaders/universe_learning.py src/web/presenters/today_learning_strategies.py alembic/versions/*strategy_proposal_insufficient_evidence_status.py
git commit -m "plan-followup: persist insufficient strategy evidence status"
```

---

### Task 6: Final Verification And Documentation

**Files:**
- Modify: `plan/design/07_replay_reflection_learning.md`
- Modify: `plan/progress_tracker.md`
- Optional modify: `documents/repo_overview.md` only if the implementation substantially restructures files beyond adding `evidence.py`.

- [ ] **Step 1: Update design doc**

In `plan/design/07_replay_reflection_learning.md`, add a short subsection under Strategy Evolution / Learning that records:

- reflection now receives same-day plus bounded prior outcome/reflection context;
- strategy evolution consumes a trailing window;
- LLM proposals must cite supporting outcome ids;
- Python evidence gates decide whether proposals are accepted.

- [ ] **Step 2: Run full relevant tests**

Run:

```bash
source ~/.venv/bin/activate && pytest tests/agents/test_post_close_prompt_contracts.py tests/agents/test_strategy_evolution_agent.py tests/agents/test_reflection_agent.py tests/trading/test_reflection_pipeline.py tests/trading/test_runtime_reflection_live.py tests/trading/test_runtime_strategy_evolution_live.py tests/trading/test_strategy_evolution.py tests/trading/test_strategy_lifecycle.py tests/trading/test_sqlalchemy_repository.py tests/db/test_trading_models.py tests/web/test_today_learning_strategies.py -q
```

Expected: pass.

- [ ] **Step 3: Run compile and diff checks**

Run:

```bash
source ~/.venv/bin/activate && python -m compileall -q src
git diff --check
```

Expected: both commands pass with no output.

- [ ] **Step 4: Optional DB migration smoke**

Only if a local Postgres is available and the user approves any required DB access:

```bash
source ~/.venv/bin/activate && alembic upgrade head
source ~/.venv/bin/activate && alembic current
```

Expected: database reaches the new head. Per `documents/general_instructions.md`, verify Postgres storage is on persistent disk before doing real deployment work:

```sql
SHOW data_directory;
```

The result must not be `/tmp`, `/run`, `/dev/shm`, tmpfs, or an anonymous container volume.

- [ ] **Step 5: Update progress tracker**

Prepend a dated entry to `plan/progress_tracker.md` summarizing:

- long-horizon context fields;
- trailing strategy evolution window;
- deterministic evidence gate;
- migration status;
- tests run and any known residual risks.

- [ ] **Step 6: Commit documentation and tracker**

```bash
git add plan/design/07_replay_reflection_learning.md plan/progress_tracker.md documents/repo_overview.md
git commit -m "docs: record long-horizon learning evidence gates"
```

Skip `documents/repo_overview.md` in `git add` if it was not changed.

---

## Rollout Notes

- This change should be behaviorally conservative. It may reduce the number of accepted strategy proposals because weak same-day proposals will now be rejected.
- Existing active strategies should not be demoted by this plan. Promotion is hardened; demotion/retirement is out of scope.
- Existing proposal rows remain valid. The migration only expands allowed statuses.
- Prompt changes alone are not trusted. Deterministic Python gates are the source of truth for accepting proposals or promoting lifecycle states.

## Handoff

Recommended implementation mode: `superpowers:subagent-driven-development`, one task per worker or one worker per pair of adjacent tasks:

- Worker A: Tasks 1-2, prompt/schema/reflection context.
- Worker B: Task 3, strategy evolution input window.
- Worker C: Tasks 4-5, evidence gates/status/UI metadata.
- Final integrator: Task 6 verification and docs.

If implemented inline, use `superpowers:executing-plans` and stop after each task for review.
