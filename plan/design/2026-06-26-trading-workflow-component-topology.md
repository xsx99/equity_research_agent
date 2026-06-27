# Trading Workflow / Component Topology

## Context

PR 32–34 cut the largest god files down and split residual helper hubs into sibling modules.
Those passes lowered *per-file* reasoning cost but were deliberately bottom-up: they reorganized
the inside of files without changing how `src/trading/` is laid out as a whole. Two structural
smells remain, and they are the ones a reader hits first when navigating the subsystem top-down:

1. **Flat dumping-ground folders.** `src/trading/runtime/` holds 21 loose `.py` files and
   `src/trading/workflows/` holds 13. Neither folder name tells you *which workflow* a file
   belongs to or *what stage* it implements. The `option_strategy_builder*` family (5 files from
   the PR 34 split) is the canonical example: a coherent cluster sitting flat next to unrelated
   execution and decision files.
2. **No top-down entry surface per workflow.** The system runs six workflows, but their
   orchestration is scattered across `runtime/` (the scheduler shells) and feature folders
   (`intraday/`, `post_close/`, `replay/`, `manual_review/`). To answer "what does pre-open do, in
   order?" you must already know which files belong together.

This doc takes the **top-down view**: start from the workflows, trace what each one actually uses,
and let the target folder structure fall out of the call graph rather than out of file size.

## Method

For each scheduler/runtime entry point, the import closure was traced down into `src/trading/*`
leaf modules. The question for every component: **is it used by one workflow or many?** That single
fact decides where it belongs.

- Used by **one** workflow → it is phase-specific and should live *inside* that workflow's
  orchestration subpackage.
- Used by **many** workflows → it is a shared capability and must *not* live under any one
  workflow.

This is the placement rule for the entire refactor. It is objective: callers decide placement, not
taste.

## Findings: the six workflows

| Workflow | Entry point | Production-wired? | Phase-specific orchestration today |
|---|---|---|---|
| **pre-open** | `scheduler/jobs/trading_preopen_job.py` → `runtime/preopen.py` | yes | `runtime/preopen*.py` |
| **manual review** | `scheduler/jobs/manual_ticker_review_job.py` → `runtime/manual_review.py` | yes | `runtime/manual_review.py`, `manual_review/` |
| **intraday refresh** | `scheduler/jobs/intraday_signal_refresh_job.py` → `runtime/intraday_refresh.py` | yes | `runtime/intraday_refresh*.py`, `intraday/` |
| **daily reflection** | `scheduler/jobs/trading_reflection_job.py` → `runtime/reflection.py` | yes | `runtime/reflection.py`, `post_close/reflection.py` |
| **strategy evolution** | `scheduler/jobs/strategy_evolution_job.py` → `runtime/strategy_evolution.py` | yes | `runtime/strategy_evolution.py`, `post_close/strategy_evolution.py`, `post_close/strategy_policy.py` |
| **historical replay** | *(none — smoke only)* `runtime/smoke_fixture_modes.py::_run_historical_replay_fixture` | **no** | `replay/historical.py`, `replay/outcomes.py` |

Key structural facts the trace established:

- **Manual review *is* pre-open with a scoped universe.** `build_live_manual_review_dependencies()`
  calls `build_live_preopen_dependencies()` and reuses the *same* universe → signal → strategy →
  portfolio-sync → risk → decision → execution chain by reference. It adds only a manual-request
  loader and an audit-count helper. These two workflows share one pipeline backbone.
- **Intraday reuses the decision/risk/execution components** (`trading_decision` record types,
  `RiskManager`, `PaperExecutionWorkflow`, `paper_option`/`paper_stock` brokers, the hedge planner)
  but wraps them in its own bounded-rebalance orchestration (`intraday/rebalance.py`,
  `intraday/news_alerts.py`, `intraday/signals.py`).
- **Replay reuses the strategy matcher/selector/classifier directly**, then adds a replay-only
  `OutcomeEvaluator`. It is **not wired to the scheduler** — no job, no `JOB_PHASE_HANDLERS` entry,
  only a `SMOKE_MODE_HANDLERS` fixture on `InMemoryTradingRepository`. (This matches review backlog
  #6; the `historical_replay_runs` table is intentionally retained as the anchor for future
  wiring.)
- **Reflection → evolution is a one-way data dependency.** Reflection produces
  `DailyReflectionRecord` / `LearningFactorRecord`; evolution consumes them. Neither touches the
  selector/classifier; learning is *applied* at pre-open/intraday time (`learning/apply.py`), not
  during the post-close phases.

## Workflow → component matrix

Rows are shared capability components; columns are the six workflows. `●` = uses directly,
`○` = uses indirectly (via a shared pipeline) or by record-type only.

| Capability component (today's path) | pre-open | manual | intraday | reflection | evolution | replay |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `data_sources/` + `workflows/universe_scan.py` (universe) | ● | ● | | | | |
| `signals/*` (builders, `source_ingestion`, `snapshots`) + `workflows/signal_snapshot.py` | ● | ● | ● | | | |
| `strategies/matching.py` | ● | ○ | ○ | | ○ | ● |
| `strategies/selector.py`, `classifier.py` | ● | ○ | | | | ● |
| `strategies/catalog,calibration,taxonomy,definitions` | ● | ● | | ○ | ○ | ○ |
| `workflows/trading_decision.py` + `option_strategy_builder*` | ● | ● | ○ | | | ○ |
| `risk/*` + `runtime/lookahead_risk.py` | ● | ● | ● | | | ○ |
| `workflows/paper_execution*.py` + `brokers/*` (execution) | ● | ● | ● | | | |
| `portfolio/*` + `workflows/portfolio_sync.py` | ● | ● | ● | | | |
| `macro/*` | ● | ● | ● | | | |
| `events/*` | ● | ● | ● | | | |
| `learning/apply.py` | ● | ● | ● | | | |
| `post_close/reflection.py` | | | | ● | ○ | |
| `replay/outcomes.py` | | | | | ○ | ● |
| `repositories/*` | ● | ● | ● | ● | ● | ● |

The matrix is the audit: every component shared across ≥2 columns belongs in the capability layer;
every single-column orchestration file belongs in a phase subpackage.

## Design decision: two layers

A literal "one folder per workflow" fails here — the matrix shows the heavy components are shared
by 2–6 workflows, so per-workflow folders would force duplication or a `shared/` bucket that just
becomes the next `runtime/`. Instead:

### Layer 1 — Phases (orchestration; the top-down entry surface)

One thin subpackage per workflow. Opening it answers "what does this workflow do, in order, and
what does it own?" Today this is the `runtime/*` shells **plus** the phase-specific feature folders
that are currently separate (`intraday/`, `post_close/`, `replay/`, `manual_review/`). The refactor
brings each workflow's orchestration and phase-only logic into one place.

### Layer 2 — Capabilities (shared components, grouped by domain)

The reusable building blocks, grouped by what they do, not by which workflow calls them. Most of
these already exist as reasonable packages (`signals/`, `risk/`, `portfolio/`, `macro/`, `events/`,
`repositories/`); the work is to (a) dissolve the `workflows/` and `runtime/` dumping grounds into
the right capability/phase homes and (b) make the `option_strategy_builder` family a subpackage.

## Target structure (recommended)

```
src/trading/
  phases/                       # Layer 1 — one subpackage per workflow
    _shell/                     # ← runtime/{facade,dispatch,support,smoke*}.py  (cross-phase scheduler shell)
    preopen/                    # ← runtime/{preopen,preopen_runner,preopen_dependencies,preopen_risk}.py
    manual_review/              # ← runtime/manual_review.py + manual_review/{requests,sqlalchemy}.py
    intraday/                   # ← runtime/intraday_refresh*.py + intraday/{rebalance,news_alerts,signals}.py
    reflection/                 # ← runtime/reflection.py + post_close/reflection.py
    strategy_evolution/         # ← runtime/strategy_evolution.py + post_close/{strategy_evolution,strategy_policy}.py
    replay/                     # ← replay/{historical,outcomes}.py   (smoke-only today — see backlog #6)

  universe/                     # ← data_sources/ + workflows/universe_scan.py
  signals/                      # signals/ (+ workflows/signal_snapshot.py adapter)
  strategy/                     # strategies/ (+ workflows/strategy_scoring.py adapter)
  decision/                     # ← workflows/trading_decision.py + workflows/option_strategy_builder/  (5-file family → subpackage)
  risk/                         # risk/ + runtime/lookahead_risk.py
  execution/                    # ← workflows/paper_execution*.py + brokers/
  portfolio/                    # portfolio/ + workflows/portfolio_sync.py
  macro/  events/  relationships/  learning/      # unchanged
  repositories/                 # unchanged (already split in PR 31/34)
```

The end state has **no `runtime/` and no `workflows/` folder** — both were grouping by mechanism
("this is a runtime shell" / "this is a workflow") rather than by workflow identity or capability.

## Open decisions (for sign-off before implementation)

These are genuine judgment calls, not mechanical. Flagged here rather than silently chosen:

1. **`phases/` + capability split, or keep capabilities flat at `src/trading/`?** The tree above
   keeps capabilities flat (only `phases/` is a new top-level dir), which is the smaller change.
   Alternative: also nest capabilities under `src/trading/capabilities/`. Recommendation: keep
   capabilities flat — they already read as domain packages; an extra wrapper dir adds depth
   without adding clarity.
2. **Where do the thin pipeline adapters in `workflows/` go** — `signal_snapshot.py`,
   `strategy_scoring.py`, `universe_scan.py`, `portfolio_sync.py`? They are stage wrappers that
   pre-open/manual/intraday compose. Recommendation: fold each into its capability package
   (`signals/`, `strategy/`, `universe/`, `portfolio/`) since they are reused, not pre-open-only.
3. **Does `replay/` belong under `phases/` while it is smoke-only?** Recommendation: yes — placing
   it there makes the "not yet production-wired" gap visible next to the wired phases, and is where
   backlog #6 wiring would land. State the smoke-only status in its `__init__` docstring.
4. **How aggressive per slice?** Recommendation: move-and-reexport only (see below); no behavior
   changes, no large-file splitting mixed in. File-size cleanup (the >400-line files) is tracked
   separately so a structural move is never entangled with a logic edit.

## Compatibility requirements

This is the same discipline PR 32–34 used; it is what keeps the refactor reviewable and reversible:

- **Preserve every public/semi-private import path via re-export hubs.** Each moved module leaves a
  thin shim at its old path that re-exports from the new location (e.g. `runtime/preopen.py` keeps
  re-exporting `run_preopen_once` from `phases/preopen/`). `runtime/__init__.py`'s stable surface
  (`TRADING_JOB_PHASES`, `run_job_phase`, `AVAILABLE_SMOKE_MODES`, `run_smoke_mode`) must not
  change.
- **`workflows/__init__.py` and `option_strategy_builder.py` stay as hubs** until all callers are
  migrated; tests assert on the private helper names they currently re-export.
- **No behavior, signature, or business-logic change in any slice.** Pure module moves plus shims.
- **Preserve one-directional dependencies:** phases may import capabilities; capabilities must not
  import phases; the `_shell` may import phases.

## Phased PR roadmap

This is move-and-reexport only — no behavior change, uniform low risk, verified identically every
slice (import smoke + `compileall` + a structural regression test). Because risk is flat across the
work, fine-grained slicing buys overhead (a test file, hub shims, a tracker entry, a verification
cycle per PR) without buying reviewability — there is nothing subtle to review in a module move.
So PR boundaries track the only two things that actually vary: **blast radius** (the `phases/`
moves touch the scheduler entry surface — `run_job_phase`, the job classes — while the capability
moves do not) and **de-risking the pattern** (prove the hub-shim mechanics on one small slice
first). That gives three PRs:

1. **PR 40 — pilot: `decision/` + `option_strategy_builder/` subpackage.** Smallest,
   highest-clarity win; directly addresses the example that motivated this doc, and validates the
   move-and-reexport mechanics end to end before the larger moves ride on them. Move
   `trading_decision.py` and the 5 builder files into `decision/`, with the builder family as a
   nested subpackage. Hubs preserve `src.trading.workflows.*` paths.
2. **PR 41 — rest of the capability layer.** `execution/` (`paper_execution*.py` + `brokers/`),
   `universe/` (`data_sources/` + `universe_scan.py`), and folding the thin pipeline adapters
   (`signal_snapshot`, `strategy_scoring`, `portfolio_sync`) into `signals/`/`strategy/`/
   `portfolio/`. Dissolves the `workflows/` folder.
3. **PR 42 — `phases/` + retire `runtime/`.** All six workflow orchestration moves
   (`preopen`, `manual_review`, `intraday`, `reflection`, `strategy_evolution`, `replay`) plus the
   cross-phase `_shell`, in one pass since they share the scheduler entry surface. Replay keeps its
   smoke-only status (noted in its `__init__` docstring). Retires the now-empty `runtime/` dir.

Stop after any slice and the tree is still coherent (hubs keep old paths working). PR 40 and 41 can
be merged into one if a larger capability-layer diff is acceptable to verify in a single go; keep
the PR 42 boundary regardless, so a broken scheduler import is never tangled with a capability move.

Deliberately **not** done as one mega-PR: dissolving `runtime/` and `workflows/` simultaneously
would put the scheduler surface and the capability moves in the same blast, making a single broken
import harder to locate.

## Non-goals

- **Not** a large-file split. The >400-line files (`paper_execution_options.py` 865,
  `smoke_fixture_modes.py` 791, `source_ingestion.py` 750, `matching.py` 672, `preopen_risk.py`
  630, `catalog.py` 609, …) are real logic, not helper tails. They may be split *opportunistically*
  once they live in their final home, tracked as separate follow-ups — never mixed into a move
  slice.
- **Not** a wiring change. Replay stays smoke-only here; production wiring is backlog #6.
- **Not** a behavior or schema change.

## Verification strategy

Per-slice (no app env access in the authoring environment — verification is handed off):

- A dedicated structural test per slice (e.g. `tests/trading/test_pr40_structural_splits.py`)
  asserting old import paths still resolve and the new module exposes the expected surface.
- Import smoke across the touched entry points (scheduler jobs, runtime facade, repositories).
- `python -m compileall -q src` and `git diff --check`.
- Re-run the existing `test_pr32/pr33/pr34_structural_splits.py` suites unchanged — they encode the
  contracts prior slices locked.

## Why this over the alternatives

- **vs. another bottom-up file split (PR 32–34 style):** those passes are done — the remaining cost
  is *navigational* (which files belong together), not *per-file*. Splitting files further would
  add churn without answering "what does pre-open do."
- **vs. one folder per workflow (the literal top-down reading):** the matrix shows the heavy
  components are shared by 2–6 workflows; per-workflow folders would duplicate them or recreate a
  `shared/` dumping ground.
- **vs. leaving it:** `runtime/` and `workflows/` keep absorbing new files with no naming pressure
  to put them anywhere in particular — the dumping grounds grow.
