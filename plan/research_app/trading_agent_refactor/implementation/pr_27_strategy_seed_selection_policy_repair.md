# PR 27 — Strategy seed selection-policy repair

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the live preopen bug where actionable strategy candidates are downgraded to watch because seeded tactical strategy rows in Postgres are missing expression-bucket `selection_policy` metadata.

**Architecture:** Keep `StrategyPipeline` and `PrimaryStrategySelector` behavior unchanged. Repair the bootstrap/data layer so seed strategy definitions are synchronized from the canonical in-code catalog when rows are missing or when existing seed rows lack critical config keys such as `selection_policy`. Add a standalone, auditable DB repair script for the already-running environment, while keeping live preopen bootstrap idempotent.

**Tech Stack:** Python, SQLAlchemy, Postgres JSONB, existing trading strategy catalog, pytest, standalone operator script.

---

## Background

The latest live preopen dry-run produced:

- `signal_snapshot_count = 17`
- `candidate_count = 153`
- `classification_count = 0`
- `risk_decision_count = 0`
- `trading_decision_count = 0`
- `execution.mode = dry_run`

DB inspection showed that several high-scoring candidates were genuinely actionable, for example:

- `APP / oversold_bounce_v1 / score=1.0`
- `AAOI / oversold_bounce_v1 / score=1.0`
- `LITE / oversold_bounce_v1 / score=1.0`
- `MU / strong_theme_catalyst_continuation_v1 / score≈0.708`

But each trade-path candidate was persisted as a watch candidate with:

```text
strategy has no eligible active expression bucket mapping
```

The immediate cause is that live `strategy_definitions` rows have active expression buckets, but tactical strategy `config_json.selection_policy` is `null`. `PrimaryStrategySelector` only selects an expression through `selection_policy.allowed_expression_bucket_ids` or `selection_policy.eligible_expression_bucket_ids`, so no selected trade is produced.

The likely lifecycle cause is a stale seed table: `seed_initial_strategy_definitions()` currently returns immediately when any strategy definition exists, so older seed rows are never patched when the canonical catalog gains `selection_policy` or expression-bucket metadata.

## Non-Goals

- Do not loosen `PrimaryStrategySelector` to guess a fallback expression when strategy metadata is incomplete.
- Do not lower actionable score thresholds.
- Do not change trading prompts or LLM behavior.
- Do not submit paper orders as part of verification.
- Do not overwrite user-created or reflection-created strategy definitions.

## File Plan

### Modify

- `src/trading/runtime/support.py`
  - Replace all-or-nothing seed behavior with idempotent seed synchronization.
  - Insert missing canonical seed definitions.
  - Patch only missing critical config fields on existing seed rows.

- `tests/trading/test_runtime_live.py`
  - Update seed bootstrap tests to cover legacy partial seed rows.
  - Preserve idempotency and non-overwrite behavior.

- `tests/trading/test_pipeline.py`
  - Add an end-to-end regression proving a patched actionable candidate advances into trade classification with `long_stock`.

- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Record the plan and, after implementation, record files changed and verification output.

### Create

- `scripts/repair_trading_strategy_definitions.py`
  - Standalone operator script to inspect and optionally repair live DB seed strategy definitions without running provider-heavy preopen.

- `tests/scripts/test_repair_trading_strategy_definitions.py`
  - Unit tests for script argument handling and dry-run/apply behavior using fake session/repository objects.

## Design Decisions

### Seed Sync Policy

Use the canonical seed rows from:

```python
from src.trading.strategies.definitions import load_all_trading_definitions
```

For every canonical seed row keyed by `(strategy_id, version)`:

1. If no row exists, insert it.
2. If a row exists and `source != "seed"`, skip it.
3. If a seed row exists, preserve identity and lifecycle fields, then merge only missing config keys from the canonical seed:
   - For tactical strategies, patch missing `selection_policy`.
   - For expression buckets, patch missing `default_trade_identity`, `allowed_trade_identities`, `allowed_instruments`, `allowed_option_strategy_types`, `required_option_leg_fields`, `required_assignment_fields`, `option_policy`, `earnings_policy`, and `default_exit_policy`.
   - Do not overwrite a non-empty existing key.

This is deliberately conservative: the code repairs missing metadata required by downstream contracts, but it does not replace operator edits or learned strategy evolution output.

### Verification Contract

After the fix:

- `seed_initial_strategy_definitions()` is safe to call on every live runtime build.
- Legacy DB rows missing `selection_policy` are patched before strategy matching runs.
- A high-scoring actionable candidate can become a `SelectedTradeRecord`.
- `TradeClassifier` can produce a `TradeClassificationRecord`.
- A live dry-run preopen should no longer stop at `classification_count = 0` when actionable candidates exist.

---

## Task 1: Capture the seed-bootstrap root cause

**Files:**
- Modify: `tests/trading/test_runtime_live.py`

- [ ] **Step 1: Replace the stale preserve-only test with targeted legacy-row coverage**

Update the existing `test_bootstrap_seed_strategy_definitions_preserves_existing_repository_rows` so it no longer asserts that all existing rows block seeding. The old behavior is the bug.

Add a test shaped like:

```python
def test_bootstrap_seed_strategy_definitions_patches_legacy_seed_rows_missing_selection_policy():
    legacy = StrategyDefinitionRecord.from_mapping({
        **next(
            row for row in load_all_trading_definitions()
            if row["strategy_id"] == "oversold_bounce_v1"
        ),
        "strategy_definition_id": "legacy-oversold",
        "config_json": {"required_signals": ["rsi_oversold"]},
        "source": "seed",
    })

    repository = _Repository(rows=[legacy])

    seed_initial_strategy_definitions(repository)

    repaired = next(row for row in repository.rows if row.strategy_id == "oversold_bounce_v1")
    assert repaired.strategy_definition_id == "legacy-oversold"
    assert repaired.config_json["selection_policy"]["eligible_expression_bucket_ids"] == ["long_stock"]
    assert repaired.config_json["required_signals"] == ["rsi_oversold"]
```

Also add:

```python
def test_bootstrap_seed_strategy_definitions_inserts_missing_expression_buckets_for_partial_catalog():
    repository = _Repository(rows=[legacy_tactical_row])

    seed_initial_strategy_definitions(repository)

    assert "long_stock" in {row.strategy_id for row in repository.rows}
    assert "defined_risk_directional_option" in {row.strategy_id for row in repository.rows}
```

- [ ] **Step 2: Add non-overwrite coverage**

Add a test proving custom non-empty values are preserved:

```python
def test_bootstrap_seed_strategy_definitions_does_not_overwrite_existing_selection_policy():
    legacy = StrategyDefinitionRecord.from_mapping({
        **catalog_row,
        "strategy_definition_id": "custom-catalyst",
        "config_json": {
            **catalog_row["config_json"],
            "selection_policy": {
                "actionable_score_threshold": 0.72,
                "eligible_expression_bucket_ids": ["defined_risk_directional_option"],
            },
        },
        "source": "seed",
    })

    repository = _Repository(rows=[legacy])

    seed_initial_strategy_definitions(repository)

    repaired = next(row for row in repository.rows if row.strategy_id == legacy.strategy_id)
    assert repaired.config_json["selection_policy"]["actionable_score_threshold"] == 0.72
    assert repaired.config_json["selection_policy"]["eligible_expression_bucket_ids"] == [
        "defined_risk_directional_option"
    ]
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_runtime_live.py -q -k "bootstrap_seed_strategy_definitions"
```

Expected before implementation:

- The new legacy-row tests fail because the current helper returns when any definition exists.

## Task 2: Implement conservative seed synchronization

**Files:**
- Modify: `src/trading/runtime/support.py`

- [ ] **Step 1: Switch the seed source to the split definition loader**

Replace:

```python
from src.trading.strategies.catalog import get_initial_strategy_definitions
```

with:

```python
from dataclasses import replace

from src.trading.strategies.definitions import load_all_trading_definitions
```

- [ ] **Step 2: Rewrite `seed_initial_strategy_definitions`**

Implement the helper as idempotent sync:

```python
def seed_initial_strategy_definitions(repository: Any) -> None:
    """Insert missing seed definitions and patch missing seed config metadata."""
    existing = {
        (definition.strategy_id, definition.version): definition
        for definition in repository.load_strategy_definitions()
    }
    for row in load_all_trading_definitions():
        expected = StrategyDefinitionRecord.from_mapping(row)
        key = (expected.strategy_id, expected.version)
        current = existing.get(key)
        if current is None:
            repository.save_strategy_definition(expected)
            existing[key] = expected
            continue
        if current.source != "seed":
            continue
        repaired_config = _merge_missing_seed_config(
            current=current.config_json,
            expected=expected.config_json,
        )
        if repaired_config == current.config_json:
            continue
        repository.save_strategy_definition(
            replace(current, config_json=repaired_config)
        )
```

- [ ] **Step 3: Add focused merge helpers**

Add private helpers in the same file:

```python
_PATCHABLE_SEED_CONFIG_KEYS = (
    "selection_policy",
    "default_trade_identity",
    "allowed_trade_identities",
    "allowed_instruments",
    "allowed_option_strategy_types",
    "required_option_leg_fields",
    "required_assignment_fields",
    "option_policy",
    "earnings_policy",
    "default_exit_policy",
)


def _merge_missing_seed_config(
    *,
    current: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current or {})
    changed = False
    for key in _PATCHABLE_SEED_CONFIG_KEYS:
        if _has_non_empty_value(merged.get(key)):
            continue
        expected_value = expected.get(key)
        if not _has_non_empty_value(expected_value):
            continue
        merged[key] = expected_value
        changed = True
    return merged if changed else dict(current or {})


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    if value == {}:
        return False
    return True
```

- [ ] **Step 4: Re-run seed tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_runtime_live.py -q -k "bootstrap_seed_strategy_definitions"
```

Expected:

- All seed bootstrap tests pass.

## Task 3: Prove the strategy pipeline reaches classification after repair

**Files:**
- Modify: `tests/trading/test_pipeline.py`

- [ ] **Step 1: Add a regression test for the actual funnel failure**

Add a test that builds a repository with a legacy tactical row missing `selection_policy`, then calls `seed_initial_strategy_definitions`, then runs `StrategyPipeline` with a fake matcher returning one actionable candidate.

Test shape:

```python
def test_strategy_pipeline_classifies_actionable_candidate_after_seed_policy_repair():
    now = datetime(2026, 6, 22, 13, 45, tzinfo=timezone.utc)
    repository = InMemoryTradingRepository()
    legacy_row = next(
        row for row in load_all_trading_definitions()
        if row["strategy_id"] == "oversold_bounce_v1"
    )
    repository.save_strategy_definition(
        StrategyDefinitionRecord.from_mapping({
            **legacy_row,
            "strategy_definition_id": "legacy-oversold",
            "config_json": {"required_signals": legacy_row["config_json"]["required_signals"]},
            "source": "seed",
        })
    )

    seed_initial_strategy_definitions(repository)
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="ignored-by-fake-matcher",
        signal_snapshot_id="snapshot-1",
        ticker="APP",
        strategy_id="oversold_bounce_v1",
        strategy_version="v1",
        strategy_definition_id="legacy-oversold",
        candidate_score=1.0,
        direction="bullish",
        action="enter_long",
        typical_horizon="2w-3m",
        core_signal_evidence={"technical.rsi_14": 24.0},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=["support breaks"],
        risk_tags=["mean_reversion"],
        macro_compatibility="allowed",
        selection_source="scanner",
        manual_request_id=None,
        selection_reason="deterministic signals matched strategy",
        rejection_reason=None,
        benchmark_context={"primary_benchmark": "QQQ"},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
        candidate_status="actionable",
    )

    result = StrategyPipeline(
        repository=repository,
        matcher=_FakeMatcher(candidate),
    ).run(snapshots=(), decision_time=now)

    assert len(result.selected_trades) == 1
    assert result.selected_trades[0].expression_bucket_id == "long_stock"
    assert len(result.classifications) == 1
    assert result.classifications[0].ticker == "APP"
    assert result.classifications[0].expression_bucket_id == "long_stock"
```

- [ ] **Step 2: Run the focused pipeline test**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_pipeline.py -q -k "seed_policy_repair"
```

Expected:

- Passes after Task 2.

## Task 4: Add a standalone DB repair script

**Files:**
- Create: `scripts/repair_trading_strategy_definitions.py`
- Create: `tests/scripts/test_repair_trading_strategy_definitions.py`

- [ ] **Step 1: Define script behavior**

The script should:

- activate through normal repo imports, matching existing script style
- support `--dry-run`
- support `--json`
- open a DB session through `src.db.connection.get_session`
- inspect strategy definitions before and after calling `seed_initial_strategy_definitions`
- commit only when not `--dry-run`
- rollback when `--dry-run`
- print inserted/patched/missing-after counts, plus the strategy ids with missing `selection_policy`

Recommended CLI:

```bash
source ~/.venv/bin/activate
python scripts/repair_trading_strategy_definitions.py --dry-run --json
python scripts/repair_trading_strategy_definitions.py --json
```

- [ ] **Step 2: Keep implementation small**

Use helper functions that can be tested without a real DB:

```python
def find_seed_definition_issues(definitions: Iterable[StrategyDefinitionRecord]) -> dict[str, object]:
    ...


def run_repair(*, session: Any, dry_run: bool) -> dict[str, object]:
    repository = SqlAlchemyTradingRepository(session)
    before = find_seed_definition_issues(repository.load_strategy_definitions())
    seed_initial_strategy_definitions(repository)
    after = find_seed_definition_issues(repository.load_strategy_definitions())
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {"before": before, "after": after, "dry_run": dry_run}
```

Use the canonical seed definition loader to decide which tactical seed rows require `selection_policy`.

- [ ] **Step 3: Add script tests**

In `tests/scripts/test_repair_trading_strategy_definitions.py`, test:

- `find_seed_definition_issues` reports `oversold_bounce_v1` when `selection_policy` is missing.
- `find_seed_definition_issues` reports no issue when catalog seed rows are complete.
- `run_repair(dry_run=True)` calls rollback.
- `run_repair(dry_run=False)` calls commit.

- [ ] **Step 4: Run script tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/scripts/test_repair_trading_strategy_definitions.py -q
```

Expected:

- Passes without connecting to Postgres.

## Task 5: Run focused and regression tests

**Files:**
- No additional code changes unless tests reveal a bug.

- [ ] **Step 1: Run focused tests**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/trading/test_runtime_live.py \
  tests/trading/test_pipeline.py \
  tests/scripts/test_repair_trading_strategy_definitions.py \
  -q
```

Expected:

- All pass.

- [ ] **Step 2: Run strategy catalog tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_strategy_catalog.py -q
```

Expected:

- All pass.

- [ ] **Step 3: Run broader affected trading tests**

Run:

```bash
source ~/.venv/bin/activate
pytest \
  tests/trading/test_primary_strategy_selector.py \
  tests/trading/test_trade_classifier.py \
  tests/trading/test_runtime_live.py \
  tests/trading/test_pipeline.py \
  -q
```

Expected:

- All pass.

## Task 6: Repair the live DB and verify the preopen funnel

**Files:**
- Runtime data only; no source files.

- [ ] **Step 1: Dry-run the DB repair script**

Run:

```bash
source ~/.venv/bin/activate
python scripts/repair_trading_strategy_definitions.py --dry-run --json
```

Expected:

- Reports the stale tactical seed rows missing `selection_policy`.
- Reports `dry_run: true`.
- Does not commit DB changes.

- [ ] **Step 2: Apply the repair**

Run:

```bash
source ~/.venv/bin/activate
python scripts/repair_trading_strategy_definitions.py --json
```

Expected:

- Reports no missing `selection_policy` rows after repair.
- Commits DB changes.

- [ ] **Step 3: Verify with a safe live preopen dry-run**

Run:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_once.py --phase preopen --mode live-preopen --json
```

Expected:

- `candidate_count > 0`
- `classification_count > 0` when actionable candidates exist
- `risk_decision_count >= classification_count` unless risk workflow has an explicit skip reason
- `execution.mode == "dry_run"`
- `orders_submitted == 0`

Do not use `--execute-paper-orders` in this verification task.

## Task 7: Update tracker and operator notes

**Files:**
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

- [ ] **Step 1: Add progress tracker entry**

Record:

- root cause
- files changed
- test commands and results
- DB repair dry-run/apply result
- live preopen dry-run summary
- known gaps, if any

- [ ] **Step 2: Check formatting**

Run:

```bash
git diff --check
```

Expected:

- No whitespace errors.

## Acceptance Criteria

- Existing stale seed rows are repaired without overwriting non-empty seed config values.
- Missing seed definitions, including expression buckets, are inserted when absent.
- `PrimaryStrategySelector` continues requiring explicit expression mappings; no fallback guessing is added.
- The regression test proves an actionable candidate can become a `TradeClassificationRecord` after seed repair.
- The standalone repair script can be run without provider/API calls.
- Safe live preopen dry-run no longer stops at `classification_count = 0` when actionable candidates exist.

## Suggested Commit Sequence

1. `test: capture strategy seed policy repair regressions`
2. `fix: sync missing seed strategy definition metadata`
3. `chore: add strategy definition repair script`
4. `docs: record strategy seed selection-policy repair plan`

