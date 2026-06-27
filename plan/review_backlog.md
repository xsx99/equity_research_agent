# Trading Agent Review Backlog

> Open problems, ranked. File:line references are current — re-verify before acting.

## How they relate

The reliability problems share one root cause: critical paths take *silent* `return` /
"log a WARNING and move on" branches — failures don't raise, don't persist, don't surface.
**#1** (order execution) and **#2** (reflection timezone) are the two live symptoms; **#3**
(JSON control flow) and **#4** (whole-table queries) are the data-model/query issues underneath
them. Fixing #1+#3 together, and #2+#4 together, is the efficient grouping.

---

## P0 — Reliability

### 1. Orders silently not placed [Resolved 2026-06-26]
**Where:** `src/trading/workflows/paper_execution.py:343-350` (stock); `paper_execution_options.py`
(option). Pre-open and intraday both flow through `PaperExecutionWorkflow`.

The stock gate is a chain of bare `return`s with no persisted record — any one drops the order
silently:
```
if decision not in {enter_long, reduce, exit, enter_short}: return
if not metadata_json["paper_trade_authorized"] and manual_request_id is None: return   # reads JSON, not the column (#3)
if risk_decision is None: return
if risk_decision.status not in {approved, reduced}: return
```
Intraday has the same gap one layer up: `IntradayRebalancePipeline._should_execute_decision`
(`src/trading/intraday/rebalance.py:485-491`) drops a decision from execution when
`risk_decision is None` / `status != "approved"` / action isn't execution-requiring, with **no
skipped(reason) execution record** — `execution_summary` only shows `orders_submitted: 0`, which
reads as success. (Intraday is otherwise wired end-to-end and does authorize its own decisions.)

The option broker enters live mode whenever `trading_base_url` is set; with missing Alpaca creds
it can raise mid-submit (no try/except around `submit_order`), potentially crashing the whole run.

**Status:** Fixed by PR 35. Execution paths now emit persisted `execution_attempts` rows for
`submitted`, `skipped(reason)`, and `failed(error)` outcomes; runtime execution reports now surface
`orders_skipped`, `orders_failed`, and `skip_reasons`; and the option broker now falls back to
local sim without credentials and returns rejected audit rows instead of raising on forced-live
auth failures.

### 2. Reflection skips on a timezone boundary [Resolved 2026-06-27]
**Where:** `src/trading/runtime/reflection.py:88` (`trade_date=decision_time.date()`);
`src/trading/repositories/mixins/reflection.py:16` (naive `datetime.combine(...)`).

`trade_date` is derived from a UTC `.date()` while the job runs at 16:20 in `SCHEDULER_TIMEZONE`,
and the repository compares a naive `datetime.combine(trade_date, ...)` against timezone-aware
columns. When local time straddles UTC midnight, `trade_date` misses the day's rows → empty →
reflection skips. **Fix together with #4** (push the filter into a timezone-aware `WHERE`).

**Status:** Fixed by PR 36. Reflection now derives `trade_date` in `SCHEDULER_TIMEZONE`, computes
the UTC `[start, end)` window for that local day, forwards the window into
`load_reflection_inputs(...)`, and has regression coverage for both the UTC-boundary case and the
window-helper DST behavior.

---

## P1 — Data model integrity

### 3. Control flow keyed off untyped JSON [Partially resolved 2026-06-26]
`paper_trade_authorized` is a real column (`src/db/models/trading/execution.py:78`), but the
control flow never switched to it:
- `paper_execution.py:345` still gates on `metadata_json.get("paper_trade_authorized")` — this is
  the live "orders not placed" path (#1).
- `strategy_lifecycle_status` is read from `metadata_json` in 5+ sites
  (`trading_decision.py:220,223,547,590`, `paper_execution_options.py:671,796`) despite the enum
  column existing → JSON and column can drift.
- `config_json.{required_signals, selection_policy, allowed_instruments, macro_blocked_regimes}`
  drives strategy matching/selection with no schema validation.

**Status:** `paper_trade_authorized` is fixed in PR 35: `TradingDecisionRecord` now carries the
typed field, repository persistence writes the real column from that field, and execution control
flow now reads the typed value instead of JSON. The `strategy_lifecycle_status` item was narrowed:
there is no execution-side column to cut over to here, so PR 35 added a catalog-backed fallback in
`paper_execution_options.py` instead of silently defaulting to `"active"` when metadata is absent.
Remaining follow-ups:
- add Pydantic validation for strategy `config_json`
- decide whether `strategy_lifecycle_status` needs a first-class persisted surface instead of the
  current metadata/catalog fallback

---

## P2 — Query performance

### 4. Whole-table load then Python-side filter [Resolved 2026-06-27]
**Where:** `src/trading/repositories/mixins/reflection.py` (`load_reflection_inputs`) plus ~56
`session.query(Model).all()` sites across `repositories/mixins/`, filtered in Python by
`.date() == trade_date`. Loads whole tables into memory (slow/timeout as data grows) and is
entangled with the timezone bug (#2). **Fix:** push the date filter into a timezone-aware `WHERE`,
together with #2.

**Status:** Fixed by PR 36 for the date-filtered hot paths. Reflection now filters timestamp
columns with UTC range predicates and `Date` columns with `trade_date` equality, and the sibling
single-day filters in `strategy`, `intraday`, `signals`, `risk`, `macro_calendar`, and
`runtime_misc` were moved into SQL. Deliberate non-date whole-table scans remain tracked in the
progress tracker rather than being expanded into this PR.

---

## P3 — Capability gaps

### 5. Today UI information design — spec exists, no implementation plan
`plan/design/14_today_ui_information_design.md` is a written spec (IP-1…IP-10: label-map/
machine-value rules, the "today health bar", "conclusion → why → evidence"), but no `pr_NN`
implementation plan derives from it, so it isn't an actionable handoff. Remaining code gaps it
catalogs:
- Empty label maps in `today_copy.py` (`event_type_label`, `risk_source_label`, `scope_label`, …)
  still fall back to snake_case enums.
- The single "today health bar" (orders submitted / skipped(reason) / reflection ran?) isn't built
  — it would also surface the #1/#2 skips.
- Trades detail lacks the "conclusion → why → evidence" hierarchy.

**Next:** write `plan/implementation/pr_NN_today_ui_information_design.md` translating design 14
into file-level tasks, then implement.

### 6. Historical replay not wired to production
`src/trading/replay/historical.py` is in-memory / smoke only — `save_historical_replay_run` and
`save_candidate_outcome_evaluations` exist only on `InMemoryTradingRepository`, not on the
production `SQLAlchemyTradingRepository`; nothing triggers it, so the table stays empty and the FK
NULL. The ORM/schema anchor (`historical_replay_runs`,
`candidate_outcome_evaluations.historical_replay_run_id`) is kept for this. **To wire up (feature
work):** implement the two `save_*` methods on the SQLAlchemy repo, add a trigger (scheduled or
on-demand), surface replay outcomes in the UI.

---

## Suggested order

1. **#1 + #3** — cut the stock gate over to the real column and replace every silent `return`
   (pre-open and intraday) with a persisted skipped(reason) record. Fixes the headline bug and the
   JSON/column drift in one pass.
2. **#2 + #4** — push date filters into a timezone-aware SQL `WHERE`; fixes reflection skipping and
   the whole-table loads together.
3. **#5** — write and execute the design-14 implementation plan.
4. **#6** — decide replay direction; build if the learning loop is near-term.
