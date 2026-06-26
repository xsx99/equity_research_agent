# Refactor Handoff: Remove Dead/Half-Wired Tables + Split the God Repository

> **Audience:** an implementing coding agent that CAN push to this repo.
> **Author:** review/analysis agent (read-only environment, cannot run the app or push).
> **Scope:** two independent, low-risk structural cleanups. They share no code — implement and verify them in **two separate PRs** in the order given.
> **Hard rule:** these are *structural* refactors. **Do not change runtime behavior.** No business logic, no control-flow, no schema semantics for tables that stay. If you discover a behavior change is unavoidable, stop and flag it in the PR description instead of proceeding.

---

## Repo facts you can rely on (verified at handoff time)

- Alembic **HEAD revision is `027`** (`alembic/versions/027_trading_runtime_runs.py`, `revision = "027"`). Nothing depends on it, so a new migration must use `down_revision = "027"`.
- The production repository class is `SQLAlchemyTradingRepository` in `src/trading/repositories/sqlalchemy.py` (1 class, **66 public methods**, ~1900 lines of the file's 2547). It has a backward-compat alias `SqlAlchemyTradingRepository = SQLAlchemyTradingRepository` (line ~1941) — **both names are imported by callers and must keep working.**
- `__init__(self, session)` only stores `self.session`. Every method uses `self.session`.
- There is a separate `InMemoryTradingRepository` (`src/trading/repositories/in_memory.py`) used by smoke scripts and tests — it is **not** part of the split, but Part A touches a few of its lines.

---

# PART A — Remove dead / half-wired persistence tables

## Critical context (read before touching anything)

The earlier static scan flagged 5 tables as "never queried." On deeper inspection, **3 of them are not clean dead tables** — they are *half-wired*: a DB model + Alembic table exist, but the **production `SQLAlchemyTradingRepository` never writes them** (the data only ever lives in the in-memory repo / domain records / tests). That changes the removal scope per table, so treat each table separately. The other 2 flagged tables (`llm_prompt_runs`, `llm_prompt_templates`) are **out of scope here** — leave them; they need a product decision (wire up LLM-prompt logging or remove), not a mechanical cleanup.

The goal of Part A is to remove **DB-persistence artifacts that production never uses**, not to rip out in-memory machinery that is still exercised. Each table below states exactly what to remove and what to keep.

### Verification commands the implementer should re-run first (sanity, must still hold)

```bash
# Production repo must NOT read or write these tables (only one incidental FK read):
grep -n "historical_replay\|macro_readthrough\|learning_factor_application" src/trading/repositories/sqlalchemy.py
#   expected: a single hit at ~line 2416 reading historical_replay_run_id (handled below), nothing else
```

---

## A1. `learning_factor_applications` — TRULY DEAD, clean removal (do this one first)

**Evidence:** no domain record type, no in-memory list, no runtime builder, no repo method. Only references are the model definition, a `relationship` on `LearningFactor`, and one model-level test.

**Remove:**

1. **Model** — delete class `LearningFactorApplication` in `src/db/models/trading.py` (starts at the line with `class LearningFactorApplication(Base):`, `__tablename__ = "learning_factor_applications"`). Delete the entire class through its `__table_args__`/last column.
2. **Back-reference** — in the `LearningFactor` model (same file, ~line 1496) delete the line:
   ```python
   applications = relationship("LearningFactorApplication", back_populates="learning_factor")
   ```
3. **Enum** — if `LearningFactorApplication` was the only user of any `ChoiceEnum` defined for it, remove that enum too. Check with `grep -n "application_scope\|ApplicationScope" src` before deleting any enum; if it's used elsewhere, keep it.
4. **`src/db/models/__init__.py`** — remove `LearningFactorApplication` from both the import block and the `__all__` list (if present).
5. **Test** — `tests/db/test_trading_models.py`: remove the `LearningFactorApplication` import (~line 17) and the test body that constructs it (~line 267, the `application = LearningFactorApplication(...)` block and its assertions). If that leaves an empty test function, delete the function.
6. **Migration** — see the shared migration template in **A4** (drop table `learning_factor_applications` and its indexes).

**Keep:** `LearningFactor` model and everything else.

---

## A2. `macro_readthrough_events` — remove DB table only, KEEP the domain record

**Evidence:** production repo never reads/writes it. BUT the domain dataclass `MacroReadthroughEventRecord` (`src/trading/macro/context.py`) **is actively built during intraday refresh** (`src/trading/runtime/intraday_refresh_helpers.py:359-364`) and stored in the in-memory repo. So the *domain* concept is alive; only the *DB persistence* is dead.

**Remove (DB-persistence only):**

1. **Model** — delete class `MacroReadthroughEvent` in `src/db/models/trading.py` (~line 933, `__tablename__ = "macro_readthrough_events"`) through its `__table_args__`.
2. **`src/db/models/__init__.py`** — remove `MacroReadthroughEvent` from import + `__all__`.
3. **Test** — `tests/db/test_trading_models.py`: remove the `MacroReadthroughEvent` import (~line 28) and the `readthrough_event = MacroReadthroughEvent(...)` test block (~line 1024).
4. **Migration** — drop table `macro_readthrough_events` and its indexes (template in A4).

**KEEP (do NOT touch):**
- `MacroReadthroughEventRecord` dataclass in `src/trading/macro/context.py` and its `__init__.py` export.
- `src/trading/runtime/intraday_refresh_helpers.py` builder logic.
- `self.macro_readthrough_events` list in `InMemoryTradingRepository` (line ~65) and tests under `tests/trading/test_macro_context.py`, `test_event_calendar.py` — these exercise the domain record, not the DB table.

> ⚠️ Migration ordering caution: this table is created in `022_risk_macro_event_contract.py` and **conditionally recreated** in `025_backfill_risk_macro_event_contract.py` (`if not inspector.has_table("macro_readthrough_events")`). Your new drop migration must come after `027`, so it will run last and leave the table dropped. Do not edit 022/025.

---

## A3. `historical_replay_runs` — remove DB table + dangling FK column (most invasive of the three)

**Evidence:** production repo never persists a replay run. The whole `HistoricalReplayRunner` feature only runs against the in-memory repo and tests. Critically, `candidate_outcome_evaluations.historical_replay_run_id` is a **FK column pointing at this table** (`ondelete="SET NULL"`, `src/db/models/trading.py:1366-1370`) — in production it is **always NULL** because no replay run is ever written. `sqlalchemy.py:2416` reads that column into a record field.

**Decision required (default = A3-i):**

- **A3-i (recommended, matches "delete dead tables"):** Remove the DB table AND the always-NULL FK column. Keep the in-memory `HistoricalReplayRunner` machinery (harmless, test-covered) but sever it from the DB. This deletes truly-dead persistence.
- **A3-ii (alternative):** Complete the wiring instead — add `save_historical_replay_run` to the SQLAlchemy repo and persist `historical_replay_run_id`. Only choose this if the replay feature is meant to be productionized. **If you pick this, stop and confirm with the human — it is feature work, not cleanup.**

### Steps for A3-i

1. **Model — drop the FK column** on `CandidateOutcomeEvaluation` (`src/db/models/trading.py`, ~line 1366):
   ```python
   # DELETE these lines:
   historical_replay_run_id = Column(
       UUID(as_uuid=True),
       ForeignKey("historical_replay_runs.historical_replay_run_id", ondelete="SET NULL"),
       nullable=True,
       index=True,
   )
   ```
2. **Model — drop the relationship** on `CandidateOutcomeEvaluation` (and the `back_populates` target):
   - On `HistoricalReplayRun` (~line 1413): `outcome_evaluations = relationship(...)` — deleted with the class.
   - On `CandidateOutcomeEvaluation`: delete any `historical_replay_run = relationship("HistoricalReplayRun", ...)` line.
3. **Model — delete class `HistoricalReplayRun`** (~line 1330, `__tablename__ = "historical_replay_runs"`) through its `__table_args__`.
4. **Repository read site** — `src/trading/repositories/sqlalchemy.py:~2416`:
   ```python
   historical_replay_run_id=str(row.historical_replay_run_id) if row.historical_replay_run_id is not None else None,
   ```
   Remove this kwarg from the `CandidateOutcomeEvaluationRecord(...)` construction.
5. **Domain record** — `src/trading/replay/outcomes.py` `CandidateOutcomeEvaluationRecord`: if it has a `historical_replay_run_id` field, remove it AND every place that sets it (grep `historical_replay_run_id` across `src/trading` and fix each). The in-memory `save_historical_replay_run` (in_memory.py:334) and `self.historical_replay_runs` list (line 73) may stay (in-memory only) — but if they become unreferenced after this change, remove them too.
6. **`src/db/models/__init__.py`** — remove `HistoricalReplayRun` from import + `__all__`.
7. **Tests** — `tests/db/test_trading_models.py` (import ~line 15, `replay = HistoricalReplayRun(...)` ~line 735, and the snapshot at ~1315 that asserts the table name `"historical_replay_runs"`). Update/remove. `tests/trading/test_historical_replay.py` exercises the in-memory runner (`repo.historical_replay_runs`) — keep it ONLY if you kept the in-memory list in step 5; otherwise update it.
8. **Migration** — drop FK column `candidate_outcome_evaluations.historical_replay_run_id` FIRST, then drop table `historical_replay_runs` (template in A4).

---

## A4. Single Alembic migration for all of Part A

Create `alembic/versions/028_drop_dead_tables.py`. One migration covering all tables removed above. **`down_revision = "027"`.**

```python
"""Drop dead/half-wired tables: learning_factor_applications, macro_readthrough_events, historical_replay_runs"""
from __future__ import annotations
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- A3: sever FK column before dropping its target table ---
    op.drop_index("ix_candidate_outcome_evaluations_historical_replay_run_id",
                  table_name="candidate_outcome_evaluations")  # verify exact index name (see note)
    op.drop_constraint("<fk_name>", "candidate_outcome_evaluations", type_="foreignkey")  # see note
    op.drop_column("candidate_outcome_evaluations", "historical_replay_run_id")

    # --- drop tables (indexes drop with the table in Postgres, but drop explicitly to mirror create migrations) ---
    op.drop_table("historical_replay_runs")
    op.drop_table("macro_readthrough_events")
    op.drop_table("learning_factor_applications")


def downgrade() -> None:
    raise NotImplementedError(
        "Irreversible cleanup migration. Restore from migrations 008/014/022/025 if rollback is required."
    )
```

**Notes for the implementer:**
- **Find exact constraint/index names** before writing the migration. Postgres autogenerates FK names. Run against a migrated DB:
  ```sql
  SELECT conname FROM pg_constraint WHERE conrelid = 'candidate_outcome_evaluations'::regclass AND contype='f';
  SELECT indexname FROM pg_indexes WHERE tablename = 'candidate_outcome_evaluations';
  ```
  Or look at how migration `008`/the FK was created and reuse that name. If the FK was created inline without an explicit name, use the autogenerated name from the query above.
- The original `op.create_index(...)` / `op.create_table(...)` calls live in `008_strategy_matching_replay_tables.py` (historical_replay_runs + the candidate_outcome_evaluations FK), `014_reflection_learning_factor_tables.py` (learning_factor_applications), `022`/`025` (macro_readthrough_events). Mirror their teardown order.
- A non-reversible `downgrade` is acceptable for a dead-table cleanup; if repo convention requires reversibility, reconstruct the `create_table` calls from those source migrations.

## A5. Part A verification (implementer runs these; handoff author cannot)

```bash
# 1. No lingering references to removed MODELS (domain records for macro may remain — see A2):
grep -rn "class HistoricalReplayRun(Base)\|class MacroReadthroughEvent(Base)\|class LearningFactorApplication(Base)" src   # expect: none
grep -rn "historical_replay_runs\|learning_factor_applications" src/db src/trading/repositories   # expect: none

# 2. Models still import cleanly:
python -c "import src.db.models"   # or the project's module entrypoint

# 3. Migration applies on a fresh DB and round-trips with the rest:
alembic upgrade head

# 4. Test suite green (model + replay + macro tests are the risk area):
pytest tests/db/test_trading_models.py tests/trading/test_historical_replay.py tests/trading/test_macro_context.py -q
pytest -q   # full suite
```

---

# PART B — Split the God Repository (`SQLAlchemyTradingRepository`)

## Goal & constraint

`SQLAlchemyTradingRepository` has **66 public methods across ~1900 lines** — every change to any domain forces editing one giant file. Split it by domain **without changing the public interface**: every caller does `SqlAlchemyTradingRepository(session).some_method(...)`, and there are ~15 call sites across `src/web/routers/today.py`, `src/trading/runtime/*`, and `scripts/*`. They must keep working unchanged.

## Recommended technique: **mixins** (lowest-risk, zero caller changes)

Do **not** introduce composition/delegation (that changes construction and risks missing a method). Instead, split the method bodies into domain **mixin classes**, one file each, and have the facade inherit them all. The facade keeps the same name, alias, `__init__`, and every method (now inherited). Callers are untouched.

### Target file layout

```
src/trading/repositories/
    sqlalchemy.py                 # becomes a thin facade (see below)
    _base.py                      # shared imports + _RepositoryBase with __init__(self, session)
    mixins/
        __init__.py
        strategy.py               # StrategyRepositoryMixin
        signals.py                # SignalsRepositoryMixin
        risk.py                   # RiskRepositoryMixin
        execution.py              # ExecutionRepositoryMixin
        intraday.py               # IntradayRepositoryMixin
        reflection.py             # ReflectionRepositoryMixin
        macro_calendar.py         # MacroCalendarRepositoryMixin
        runtime_misc.py           # RuntimeMiscRepositoryMixin
```

### `_base.py`

Move the shared module-level imports (currently `sqlalchemy.py` lines 1–78: `uuid`, `datetime`, `Decimal`, `SimpleNamespace`, all `src.db.models.trading` model imports, and all the domain-record imports) into `_base.py` so each mixin can import what it needs. Define:

```python
class _RepositoryBase:
    def __init__(self, session: Any) -> None:
        self.session = session
```

Each mixin imports only the models/records it uses. (Simplest first pass: have `_base.py` re-export everything and let mixins `from src.trading.repositories._base import *` — then tighten imports per mixin in a follow-up if desired. Keep the first PR mechanical.)

### The facade (`sqlalchemy.py` after the split)

```python
from src.trading.repositories._base import _RepositoryBase
from src.trading.repositories.mixins.strategy import StrategyRepositoryMixin
from src.trading.repositories.mixins.signals import SignalsRepositoryMixin
from src.trading.repositories.mixins.risk import RiskRepositoryMixin
from src.trading.repositories.mixins.execution import ExecutionRepositoryMixin
from src.trading.repositories.mixins.intraday import IntradayRepositoryMixin
from src.trading.repositories.mixins.reflection import ReflectionRepositoryMixin
from src.trading.repositories.mixins.macro_calendar import MacroCalendarRepositoryMixin
from src.trading.repositories.mixins.runtime_misc import RuntimeMiscRepositoryMixin


class SQLAlchemyTradingRepository(
    StrategyRepositoryMixin,
    SignalsRepositoryMixin,
    RiskRepositoryMixin,
    ExecutionRepositoryMixin,
    IntradayRepositoryMixin,
    ReflectionRepositoryMixin,
    MacroCalendarRepositoryMixin,
    RuntimeMiscRepositoryMixin,
    _RepositoryBase,
):
    """Composed trading repository. Behavior is identical to the pre-split class;
    methods now live in domain mixins under repositories/mixins/."""


# Preserve the existing backward-compat alias — callers import BOTH names.
SqlAlchemyTradingRepository = SQLAlchemyTradingRepository
```

Each mixin is `class XRepositoryMixin:` (no base needed; they all get `self.session` from the facade's `_RepositoryBase`). Move the method bodies **verbatim** — do not edit logic, including the known `load_reflection_inputs` full-table-scan pattern (that is a separate fix, out of scope here).

### Method → mixin mapping (all 66 public methods)

Move each method (and any private helper it exclusively uses) into the listed mixin. Private helpers shared across mixins go into `_RepositoryBase` or a small `_helpers.py`.

**`strategy.py` — StrategyRepositoryMixin**
- `save_strategy_definition`, `load_strategy_definitions`, `load_active_strategy_definitions`
- `save_strategy_proposal`, `save_strategy_run`, `save_strategy_evaluation_result`
- `load_strategy_evolution_inputs`
- `save_candidate_scores`, `save_watch_candidates`
- `save_trade_classifications`, `load_trade_classification`

**`signals.py` — SignalsRepositoryMixin**
- `save_signal_snapshot`, `load_signal_snapshots_for_decision`, `load_previous_signal_snapshot`
- `load_event_news_items`, `load_latest_signal_snapshots_for_tickers`

**`risk.py` — RiskRepositoryMixin**
- `save_position_sizing_decision`, `save_portfolio_risk_snapshot`
- `save_portfolio_risk_intent`, `load_portfolio_risk_intents`
- `save_risk_factor_exposures`, `save_risk_decision`, `save_risk_hedge_decision`, `save_option_risk_snapshot`

**`execution.py` — ExecutionRepositoryMixin** (paper stock + options + positions)
- `save_paper_order`, `save_paper_execution`, `has_paper_execution`
- `load_paper_positions`, `replace_paper_positions`, `save_portfolio_snapshot`
- `save_option_strategy_decision`, `save_option_strategy_legs`
- `save_paper_option_order`, `save_paper_option_execution`, `has_paper_option_execution`
- `save_paper_option_position`, `load_paper_option_positions`

**`intraday.py` — IntradayRepositoryMixin**
- `save_intraday_signal_scan`, `save_intraday_signal_snapshot`, `load_latest_intraday_signal_snapshots_for_tickers`
- `save_news_alert`, `load_existing_news_alert_dedupe_keys`
- `save_intraday_rebalance_decision`
- `load_intraday_scope`, `load_intraday_request_contexts`, `load_intraday_candidate_context`

**`reflection.py` — ReflectionRepositoryMixin**
- `save_daily_reflection`, `save_learning_factor`, `load_active_learning_factors`
- `load_reflection_inputs`  *(the big one — move verbatim, do not refactor here)*

**`macro_calendar.py` — MacroCalendarRepositoryMixin**
- `save_macro_snapshot`, `load_latest_macro_snapshot`
- `save_calendar_events`, `load_calendar_events`
- `save_portfolio_event_risk_assessments`, `load_portfolio_event_risk_assessments`
- `load_decision_available_risk_macro_context`

**`runtime_misc.py` — RuntimeMiscRepositoryMixin** (decision/LLM/universe/runtime/manual-review — low-volume leftovers)
- `save_trading_decision`
- `save_prompt_template`, `save_prompt_run`, `save_usage_events`
- `save_universe_snapshot`, `load_active_universe_filter_config`
- `save_runtime_run`, `load_latest_runtime_run`
- `load_manual_review_audit_rows`

> The exact grouping is not sacred — if a method's private helpers make another grouping cleaner, adjust. What is non-negotiable: **all 66 methods end up on the facade with identical signatures and bodies**, and the `SqlAlchemyTradingRepository` alias survives.

### Procedure (mechanical, do it in this order)

1. Create `_base.py` with shared imports + `_RepositoryBase.__init__`.
2. Create `mixins/` package with empty mixin classes.
3. Move methods one mixin at a time. After **each** mixin, run `python -c "from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository, SqlAlchemyTradingRepository"` to catch import/indentation breakage early.
4. Reduce `sqlalchemy.py` to the facade shown above. Keep `from __future__ import annotations` at the top of every new file.
5. Confirm no private helper was left behind: `grep -n "def _" src/trading/repositories/sqlalchemy.py` should be empty (all moved), or any remaining shared helper lives in `_base.py`.

### Guard against silent method loss (do this — it's the one thing that makes this refactor safe)

Capture the public method set **before** and **after** and diff:

```bash
# BEFORE (on main, pre-refactor):
python - <<'PY' > /tmp/repo_methods_before.txt
from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository as R
print("\n".join(sorted(m for m in dir(R) if not m.startswith("_"))))
PY

# AFTER (on the refactor branch): regenerate to /tmp/repo_methods_after.txt the same way, then:
diff /tmp/repo_methods_before.txt /tmp/repo_methods_after.txt && echo "IDENTICAL PUBLIC API ✅"
```
The diff **must be empty**. If anything dropped, you missed a method.

## Part B verification

```bash
# 1. Both class names import and construct:
python -c "from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository, SqlAlchemyTradingRepository as A; print(A is SQLAlchemyTradingRepository)"   # True

# 2. Public API identical (see diff above) — MUST be empty diff.

# 3. All ~15 call sites still resolve (import-level smoke):
python -c "import src.web.routers.today, src.trading.runtime.preopen, src.trading.runtime.reflection, src.trading.runtime.preopen_dependencies, src.trading.runtime.intraday_refresh_dependencies, src.trading.runtime.strategy_evolution"

# 4. Repository + runtime tests:
pytest tests/ -q
```

---

## Summary for the PR descriptions

**PR 1 (Part A):** "Remove dead/half-wired persistence tables (`learning_factor_applications`, `macro_readthrough_events` DB table, `historical_replay_runs` + its always-NULL FK column on `candidate_outcome_evaluations`). Production repo never wrote these. Domain records for macro read-through are retained (still built in-memory during intraday refresh). One drop-only migration `028`, down_revision `027`. No behavior change."

**PR 2 (Part B):** "Split `SQLAlchemyTradingRepository` (66 methods / ~1900 lines) into 8 domain mixins under `repositories/mixins/`; facade re-composes them. Public API byte-for-byte identical (verified via dir() diff). Zero call-site changes. No behavior change."

## Things explicitly OUT of scope (do not do here)

- Promoting JSON keys (`paper_trade_authorized`, `strategy_lifecycle_status`) to typed columns — separate effort.
- Fixing the `load_reflection_inputs` full-table-scan / timezone issues — move it verbatim, fix later.
- The order-placement silent-return and reflection-skip observability fixes — separate effort.
- `llm_prompt_runs` / `llm_prompt_templates` — leave them; needs a product decision.
