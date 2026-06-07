# News Condensation First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-pass deterministic news condensation layer that preserves full provider timestamps, filters obvious low-signal items, collapses near-duplicate news before persistence, stabilizes event-news signal counts, and limits LLM evidence items.

**Architecture:** Keep the new logic deterministic and ingestion-first. Provider adapters continue to normalize raw rows, `src/providers/news_data/helpers.py` owns condensation-specific normalization/filtering/grouping/ranking helpers, `src/trading/signals/source_ingestion.py` applies those helpers before building `EventNewsItemRecord`s, and downstream consumers continue reading `event_news_items` while using the richer metadata and smaller evidence surface.

**Tech Stack:** Python, pytest, dataclasses, existing in-memory trading repositories, provider adapters, trading signal workflows.

---

### Task 1: Provider Timestamp Preservation

**Files:**
- Modify: `src/providers/news_data/finnhub.py`
- Modify: `src/providers/news_data/marketaux.py`
- Modify: `src/providers/news_data/alpaca.py`
- Test: `tests/tools/test_news_data.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_provider_adapters_preserve_full_iso_timestamps():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: FAIL because the providers still truncate timestamps to `YYYY-MM-DD`.

- [ ] **Step 3: Write minimal implementation**

```python
published_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
published_at = raw_date
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: PASS

### Task 2: Deterministic Condenser Helper

**Files:**
- Modify: `src/providers/news_data/helpers.py`
- Test: `tests/tools/test_news_data.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_condense_news_items_drops_low_signal_duplicates_and_keeps_new_facts():
    ...

def test_condense_news_items_prefers_earliest_available_item_and_emits_metadata():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: FAIL because no condenser exists yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class CondensedNewsItem:
    raw_item: NewsItem
    event_type: str
    ...

def condense_news_items(...):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py -q`
Expected: PASS

### Task 3: Source Ingestion Integration

**Files:**
- Modify: `src/trading/signals/source_ingestion.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/test_run_trading_source_ingestion_smoke.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_source_ingestion_service_condenses_news_and_records_run_metadata():
    ...

def test_run_trading_source_ingestion_smoke_reports_condensation_summary():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py tests/test_run_trading_source_ingestion_smoke.py -q`
Expected: FAIL because ingestion currently persists every normalized news row and does not emit condensation counters.

- [ ] **Step 3: Write minimal implementation**

```python
condensed = condense_news_items(...)
metadata_json = {"news_condensation": {...}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_signal_sources.py tests/test_run_trading_source_ingestion_smoke.py -q`
Expected: PASS

### Task 4: Event-News Signal Semantics

**Files:**
- Modify: `src/trading/signals/event_news.py`
- Test: `tests/trading/test_event_news_signals.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_event_news_signals_apply_negative_catalyst_precedence():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_event_news_signals.py -q`
Expected: FAIL because the first negative item currently wins.

- [ ] **Step 3: Write minimal implementation**

```python
NEGATIVE_CATALYST_PRECEDENCE = {...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_event_news_signals.py -q`
Expected: PASS

### Task 5: LLM Evidence Budget

**Files:**
- Modify: `src/trading/workflows/trading_decision.py`
- Test: `tests/trading/test_trading_decision_repository.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_trading_decision_pipeline_limits_news_evidence_to_representative_budget():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py -q`
Expected: FAIL because the pipeline currently forwards every windowed news item.

- [ ] **Step 3: Write minimal implementation**

```python
TRADING_NEWS_EVIDENCE_LIMIT = 4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source ~/.venv/bin/activate && pytest tests/trading/test_trading_decision_repository.py -q`
Expected: PASS

### Task 6: Final Verification And Documentation

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`
- Modify: `documents/repo_overview.md`

- [ ] **Step 1: Run targeted verification**

Run: `source ~/.venv/bin/activate && pytest tests/tools/test_news_data.py tests/trading/test_signal_sources.py tests/trading/test_event_news_signals.py tests/trading/test_trading_decision_repository.py tests/trading/test_news_alerts.py tests/test_run_trading_source_ingestion_smoke.py -q`
Expected: PASS

- [ ] **Step 2: Run broader regression coverage**

Run: `source ~/.venv/bin/activate && pytest tests/trading -q`
Expected: PASS

- [ ] **Step 3: Run whitespace diff check**

Run: `git diff --check`
Expected: PASS

- [ ] **Step 4: Update tracker/docs**

```markdown
- 2026-06-07: Implemented the first-pass news condensation slice...
```
