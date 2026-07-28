# PR 61: Research Global-Indicator Schema Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore scheduled research input validation by aligning the strict research macro-indicator schema with the two optional fields already emitted by the global-context provider.

**Architecture:** Keep `ResearchGlobalIndicator` as the strict producer/consumer boundary and explicitly declare the provider's optional `previous_close` and `return_vs_previous_close` values. Prove the compatibility fix with a test-first regression in the existing validated research payload fixture; do not change provider, scheduler, persistence, prompt, or deployment behavior.

**Tech Stack:** Python 3.13, Pydantic v2, pytest

---

## Required Reading

- `documents/general_instructions.md`
- `plan/design/2026-07-28-research-global-indicator-schema-compatibility.md`
- `plan/implementation/README.md`
- `plan/module_contracts.md`
- `src/agents/research_schemas.py`
- `tests/agents/test_research_prompt_registry.py`

## Progress

| Task | Status | Evidence |
| --- | --- | --- |
| 1. Add the failing research-input compatibility regression | Pending | — |
| 2. Add the minimal schema compatibility fields | Pending | — |
| 3. Run focused and full verification, then update tracker | Pending | — |

## Task 1: Add The Failing Research-Input Compatibility Regression

**Files:**

- Modify: `tests/agents/test_research_prompt_registry.py:183-217`

- [ ] **Step 1: Extend the valid provider-shaped input**

Add the two fields now emitted for the VIX indicator:

```python
"previous_close": 17.9,
"return_vs_previous_close": pytest.approx((18.2 - 17.9) / 17.9),
```

Use a literal float in the input payload, not `pytest.approx`, so Pydantic receives the same primitive type as production:

```python
"previous_close": 17.9,
"return_vs_previous_close": (18.2 - 17.9) / 17.9,
```

Extend `test_research_input_payload_accepts_valid_data` with:

```python
indicator = payload.global_context.indicators["vix"]
assert indicator.previous_close == pytest.approx(17.9)
assert indicator.return_vs_previous_close == pytest.approx((18.2 - 17.9) / 17.9)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_research_prompt_registry.py::test_research_input_payload_accepts_valid_data -q
```

Expected: one failure containing `previous_close` and
`return_vs_previous_close` with Pydantic error type `extra_forbidden`.

- [ ] **Step 3: Record RED evidence in the progress table**

Update Task 1 to `Complete` and record the exact failing command and expected
two-field validation failure.

## Task 2: Add The Minimal Schema Compatibility Fields

**Files:**

- Modify: `src/agents/research_schemas.py:100-107`
- Test: `tests/agents/test_research_prompt_registry.py`

- [ ] **Step 1: Declare both optional consumer fields**

Add exactly these fields to `ResearchGlobalIndicator`:

```python
previous_close: Optional[float] = None
return_vs_previous_close: Optional[float] = None
```

Keep `model_config = ConfigDict(extra="forbid")` unchanged.

- [ ] **Step 2: Re-run the focused test and verify GREEN**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_research_prompt_registry.py::test_research_input_payload_accepts_valid_data -q
```

Expected: `1 passed`.

- [ ] **Step 3: Run the complete research-schema test file**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_research_prompt_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Record GREEN evidence in the progress table**

Update Task 2 to `Complete` with the focused and file-level pass counts.

## Task 3: Run Focused And Full Verification, Then Update Tracker

**Files:**

- Modify: `plan/progress_tracker.md`
- Modify: `plan/implementation/pr_61_research_global_indicator_schema_compatibility.md`

- [ ] **Step 1: Run the related producer/consumer suites**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/agents/test_research_prompt_registry.py \
  tests/research/test_pipeline.py \
  tests/tools/test_fred_provider.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the full unit-test suite**

Run:

```bash
source ~/.venv/bin/activate
pytest -q
```

Expected: no new failures relative to the repository's documented baseline.
Record all pre-existing failures exactly if the suite is not fully green.

- [ ] **Step 3: Run static and diff verification**

Run:

```bash
source ~/.venv/bin/activate
python -m compileall -q src
git diff --check
```

Expected: both commands exit successfully with no output.

- [ ] **Step 4: Update project tracking**

Prepend a 2026-07-28 entry to `plan/progress_tracker.md` describing:

- the provider/consumer schema mismatch;
- the two optional fields added while retaining `extra="forbid"`;
- the RED and GREEN test evidence;
- focused and full-suite verification results.

Mark all tasks in this plan `Complete` and record the final evidence.

- [ ] **Step 5: Review the final diff**

Run:

```bash
git status --short
git diff -- \
  src/agents/research_schemas.py \
  tests/agents/test_research_prompt_registry.py \
  plan/progress_tracker.md \
  plan/implementation/pr_61_research_global_indicator_schema_compatibility.md
```

Expected: only the approved schema compatibility fix, regression test, and
tracking updates are present.
