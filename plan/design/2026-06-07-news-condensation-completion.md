# News Condensation Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining approved news-condensation design work after the first-pass slice by tightening new-fact escape behavior, preserving legacy fallback semantics when the condenser flag is off, and extending workflow coverage to strategy matching and intraday alerts.

**Architecture:** Keep the ingestion-first deterministic design from the first pass. The remaining work stays centered in `src/providers/news_data/helpers.py` and `src/trading/signals/source_ingestion.py`, with downstream verification added through strategy-matching and intraday-alert tests rather than new persistence layers.

**Tech Stack:** Python, pytest, dataclasses, environment-flag controls, existing in-memory trading repositories and workflows.

---

### Task 1: Remaining Condenser Semantics

**Files:**
- Modify: `src/providers/news_data/helpers.py`
- Test: `tests/tools/test_news_data.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_condense_news_items_keeps_stage_change_as_new_fact():
    ...

def test_condense_news_items_keeps_later_negative_fact_as_distinct_event():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: FAIL because the current duplicate keying does not explicitly preserve stage-change / negative-fact escape behavior.

- [ ] **Step 3: Write minimal implementation**

```python
def _extract_event_stage(...):
    ...

def _headline_signature(...):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: PASS

### Task 2: Feature-Flag Fallback Semantics

**Files:**
- Modify: `src/trading/signals/source_ingestion.py`
- Test: `tests/trading/test_signal_sources.py`

- [ ] **Step 1: Write the failing test**

```python
def test_source_ingestion_service_preserves_legacy_event_typing_when_condenser_disabled(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py -q`
Expected: FAIL because the current flag-off path no longer preserves legacy event typing/sentiment behavior.

- [ ] **Step 3: Write minimal implementation**

```python
event_type = infer_news_event_type(...)
sentiment = infer_news_sentiment(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py -q`
Expected: PASS

### Task 3: Workflow Coverage For Alerts And Strategy Matching

**Files:**
- Modify: `tests/trading/test_news_alerts.py`
- Modify: `tests/trading/test_strategy_matching.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_news_alert_service_keeps_distinct_alerts_for_new_fact_rewrites():
    ...

def test_strategy_matcher_score_is_not_inflated_by_duplicate_news_volume_after_condensation():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_news_alerts.py tests/trading/test_strategy_matching.py -q`
Expected: FAIL because the remaining workflow coverage is missing.

- [ ] **Step 3: Write minimal implementation**

```python
# Prefer code changes only if the tests prove a real behavior gap.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_news_alerts.py tests/trading/test_strategy_matching.py -q`
Expected: PASS

### Task 4: Verification And Documentation

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Modify: `documents/repo_overview.md` (only if architecture wording needs an extra update)

- [ ] **Step 1: Run focused verification**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py tests/trading/test_signal_sources.py tests/trading/test_news_alerts.py tests/trading/test_strategy_matching.py -q`
Expected: PASS

- [ ] **Step 2: Run broader relevant verification**

Run: `source ~/.venv/bin/activate && pytest tests/trading -q`
Expected: PASS in the user’s local environment.

- [ ] **Step 3: Run whitespace diff check**

Run: `git diff --check`
Expected: PASS

- [ ] **Step 4: Update tracker**

```markdown
- 2026-06-07: Completed the remaining news-condensation design work...
```
