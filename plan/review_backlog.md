# Future Work — Trading Agent Review Backlog

> Consolidated backlog from a code review (2026-06). Covers three reported symptoms
> (orders not placing, reflection not running, confusing UI) plus structural issues
> found while investigating them. Items are grouped by theme and ranked within each
> group. File:line references were accurate at review time — re-verify before acting.
>
> Two items already have a detailed implementation spec:
> **`plan/implementation/pr_31_refactor-dead-tables-and-repository-split.md`** (dead-table removal + repository split).

---

## How these problems relate

The three reported symptoms are **not independent** — they share one root cause and one
chain:

> **Root cause:** the critical paths are full of *silent* `return` / "log a WARNING and
> call it done" branches. Failures don't raise, don't persist, and don't surface in the UI.

> **Chain:** pre-open order gate silently skips → no `paper_order` / `portfolio_snapshot`
> persisted → post-close reflection finds no data → reflection silently skips (WARNING only)
> → UI shows neither *why* no order nor *why* no reflection. You see "it broke again" with
> no diagnosable reason.

Fixing **observability first** (make every silent skip a visible, reasoned record) is the
highest-leverage change: it turns "it broke and I can't tell why" into "skipped — reason:
X," after which the real gate/timezone/data bugs are obvious.

---

## P0 — Reliability (the reported symptoms)

### 1. Orders silently not placed
**Where:** `src/trading/workflows/paper_execution.py:327-336` (stock; option path ~209-225).
**Problem:** a chain of un-logged `return`s before the broker is ever called. Any one of
them drops the order with no record:
- `paper_trade_authorized` not `True` in `metadata_json` (set false when strategy isn't
  `active`/`experimental`, or decision is `no_trade`/`hold`) — `trading_decision.py:206-211`.
- `risk_decision is None`, or status not in `{approved, reduced}`.
- `TRADING_EXECUTE_PAPER_ORDERS` env false → `preopen_runner.py:88` returns a `dry_run`
  report with `orders_submitted=0` that *looks like success*.
- Option broker (`paper_option.py`) enters live mode whenever `trading_base_url` is set; if
  Alpaca creds are missing it raises mid-submit (no try/except around `submit_order`),
  potentially crashing the whole pre-open run.

**Fix direction:** replace each silent `return` with a persisted, reasoned "skipped"
execution record + structured log (reason codes: `not_authorized`, `risk_rejected`,
`dry_run`, `missing_credentials`, …). Execution report must distinguish
`submitted / skipped(reason) / failed(error)` — never conflate "0 orders" with "success".
Option broker should fail-fast with a clear error or fall back to local sim, not 401
mid-flight.

### 2. Reflection silently doesn't run
**Where:** `src/trading/runtime/reflection.py:31-36`, `:86-88`;
`src/scheduler/jobs/trading_reflection_job.py:24`.
**Problem:**
- Hard guards: if `portfolio_outcome` missing OR `portfolio_snapshots` empty → returns
  `status="skipped"`, and the job only emits a `logger.warning`. To you that reads as
  "reflection didn't run."
- **Dependency on item #1:** snapshots/outcome come from pre-open/intraday portfolio sync.
  If orders didn't place / sync didn't run, reflection has nothing to reflect on and skips.
  This is *why the same days break both.*
- **Timezone boundary:** `trade_date = datetime.now(timezone.utc).date()` but the job is
  scheduled at 16:20 in `SCHEDULER_TIMEZONE`. The repository filters everything with
  `row.X.date() == trade_date` (~26 sites in `repositories/sqlalchemy.py:459+`). If the
  scheduled local time straddles UTC midnight, `trade_date` misses the day's rows → empty →
  skip. Also `sqlalchemy.py:456` compares a naive `datetime.combine(...)` against a
  timezone-aware column.

**Fix direction:** persist a `reflection_run(status=skipped, reasons=[...])` so skips are
visible (and distinguish "no trades today, normal" from "data should exist but is missing,
anomaly"). Derive `trade_date` from the scheduler/trading-calendar timezone, consistent with
the `.date()` comparisons.

### 3. UI hard to understand / not simple enough → **now spec'd in `plan/design/14_today_ui_information_design.md`**
**Where:** `src/templates/today.html`, `src/web/presenters/*`, `src/web/routers/today.py`
(2095 lines), `plan/implementation/pr_28_ui-redesign-plan.md` (P0-P4 marked done but didn't cover the below).
**Status:** the open-ended "make it simpler" is now a concrete spec — design module 14
(diagnosis of as-built drift from D09 + information-design principles): label-map/machine-value
rules, the "today health bar" (IP-9/IP-10), and "conclusion → why → evidence" (IP-1/IP-2).
Its §9 maps which of the items below shrink because of the UI design.
**Problems:**
- Trades detail stacks ~9 equal-weight cards; no hierarchy, no collapse, no primary action.
- Raw machine values leak: empty label maps in `today_copy.py` (`event_type_label`,
  `risk_source_label`, `scope_label`, …) fall back to snake_case enums
  (`liquidity_crunch`, `partially_correct`, `expression_bucket_…`).
- 15+ unexplained jargon terms (Net/Gross Exp., Margin Util., Macro Regime, Edge,
  Invalidators, Lookahead risk, Hedge overlay…).
- Duplication: `approved_weight` shown 4-5×, confidence/risk status 2-3×.
- No clear "what do I do here" on any tab.

**Fix direction (ROI order):** (a) fill the empty label maps + format in presenters so no
snake_case reaches the UI; (b) a single "today health bar" — orders submitted / skipped
(with reason) / reflection ran? — which *also* solves "can't tell why nothing happened";
(c) collapse Trades detail into "conclusion → why → evidence" sections.

---

## P1 — Data model integrity (cause of the P0 bugs)

### 4. Control-flow logic keyed off untyped JSON
**Where:** 123 JSON columns in `db/models/trading.py`; `metadata_json` used 35×.
**Problem:** business branches read string keys out of untyped JSON; a missing/typo'd key
silently evaluates falsy → wrong branch, with no schema error. The worst offenders drive
control flow:
- `metadata_json.paper_trade_authorized` — **this is the "orders not placed" bug (#1).**
- `metadata_json.strategy_lifecycle_status` — **duplicated**: there is already a
  `StrategyLifecycleStatus` enum column, so JSON and column can drift.
- `metadata_json.generated_hedge_action`, `context_snapshot_json.*_context`,
  `config_json.{required_signals, selection_policy, allowed_instruments,
  macro_blocked_regimes}` (drives strategy matching/selection with no validation).

**Fix direction:** promote the ~2 control-flow-critical fields to real, constrained columns
first (`paper_trade_authorized`, `strategy_lifecycle_status` — drop the JSON duplicate). Add
pydantic schema validation for `config_json`. Leave display-only JSON (entry/exit plans,
key_drivers) as-is.

---

## P2 — Structural cleanup (lowers cost of every future change)

### 5. Dead / half-wired persistence tables → **spec'd in `plan/implementation/pr_31_refactor-dead-tables-and-repository-split.md` (Part A)**
- `learning_factor_applications` — truly dead, clean removal.
- `macro_readthrough_events` — remove DB table only; keep the in-memory domain record.
- `historical_replay_runs` — see item #7 (decide before removing).
- `llm_prompt_runs` / `llm_prompt_templates` — written-or-defined but never read; needs a
  product decision (wire up LLM-prompt logging, or remove). **Not yet spec'd.**

### 6. God Repository → **spec'd in `plan/implementation/pr_31_refactor-dead-tables-and-repository-split.md` (Part B)**
`SQLAlchemyTradingRepository`: 66 methods / ~1900 lines in one class. Split into domain
mixins, identical public API. Also note the God *files*: `db/models/trading.py` (2308,
60 tables), `workflows/trading_decision.py` (1584), `workflows/paper_execution.py` (1563),
`web/routers/today.py` (2095) — candidates for the same domain-split treatment later.

### 7. Repository query anti-pattern
**Where:** `repositories/sqlalchemy.py:454+`, ~26 sites in `load_reflection_inputs` and
others: `session.query(Model).all()` then filter in Python by `.date() == trade_date`.
**Problem:** loads whole tables into memory; slow/timeout as data grows; entangled with the
timezone bug (#2). **Fix direction:** push the date filter into a proper `WHERE` (timezone-
aware), done together with #2. Move first during the repository split (#6), fix logic after.

---

## P3 — Missing capability (decide, then build)

### 8. Wire Historical Replay into production (or remove)
**Where:** `src/trading/replay/historical.py`; runner only triggered by
`runtime/smoke_fixture_modes.py:200`.
**What it is:** look-ahead-free strategy backtesting/replay — reconstruct candidates from
point-in-time signal snapshots at a historical `decision_time`, rerun the
match → select → classify → score pipeline, and evaluate each candidate against actual
forward returns vs QQQ/SPY. `historical_replay_runs` is the per-batch header;
`candidate_outcome_evaluations.historical_replay_run_id` links the detail rows.
**Current state:** **in-memory / smoke only.** `save_historical_replay_run` and
`save_candidate_outcome_evaluations` exist **only** in `InMemoryTradingRepository`, not in
the production `SQLAlchemyTradingRepository`. No scheduler/UI/CLI triggers it. In production
the table is always empty and the FK column is always NULL.
**Decision:**
- **If learning/backtesting is on the roadmap (recommended):** wire it up — implement the
  two `save_*` methods on the SQLAlchemy repo, add a trigger (scheduled or on-demand), and
  surface replay outcomes in the UI. This is the same family of capability as the reflection
  / learning-loop you want working (#2, and the dead `learning_factor_applications` in #5) —
  evaluate decisions after the fact and feed strategy. **This is feature work, not cleanup.**
- **If not near-term:** remove it as part of #5 to cut dead weight.

---

## Suggested order

1. **#1 + #2 observability** (P0) — make silent skips visible. Unblocks all diagnosis.
2. **#4** promote `paper_trade_authorized` / `strategy_lifecycle_status` to columns — fixes
   the actual "orders not placed" bug, removes JSON/column drift.
3. **#2 timezone + #7 query** fix — fixes reflection not running.
4. **#3 UI** label maps + today health bar.
5. **#5 + #6** structural cleanup (already spec'd) — do when P0/P1 are stable.
6. **#8** decide replay direction; build if learning loop is a goal.
