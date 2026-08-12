# Strategy Learning Loop Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the production strategy-learning loop by maturing persisted
candidate scores into auditable outcomes, bounding strategy-evolution input, and
making System-tab strategy state understandable.

**Architecture:** A production `OutcomeEvaluationPipeline` evaluates the
`candidate_scores` that existed at each decision time; it does not invoke the
offline candidate-reconstruction replay runner. A small pure core owns horizons,
directional returns, and evidence caps; SQLAlchemy repositories supply persisted
candidate/context reads and idempotent writes; the runtime, scheduler, and UI
consume normalized reports and read models.

**Tech Stack:** Python 3, SQLAlchemy/PostgreSQL/Alembic, APScheduler, Jinja,
pytest, existing Alpaca market-data provider abstractions.

---

## File Map

- Create: `src/trading/outcomes/horizons.py` — canonical XNYS horizon policy and
  deterministic checkpoint calculation.
- Create: `src/trading/outcomes/evaluator.py` — pure directional return,
  excursion, comparator, and information-ratio calculations.
- Create: `src/trading/outcomes/prices.py` — injected-calendar, provider-backed
  price boundary and comparator-symbol loader.
- Create: `src/trading/outcomes/ledger.py` — pure stock/option execution-cycle
  reducer for actual traded-performance read models.
- Create: `src/trading/outcomes/pipeline.py` — persisted-candidate maturation
  orchestration and normalized run result.
- Create: `src/trading/outcomes/__init__.py` — stable public exports.
- Create: `src/trading/runtime/outcomes.py` — live dependency graph and
  post-close runtime entrypoint.
- Create: `src/scheduler/jobs/outcome_evaluation_job.py` — 16:10 ET scheduled
  post-close phase.
- Create: `scripts/run_outcome_backfill.py` — explicit date-range dry-run/resume
  operator command.
- Create: `alembic/versions/033_candidate_outcome_maturation_idempotency.py` —
  outcome uniqueness/index support and run metadata migration.
- Modify: `src/db/models/trading/reflection.py` — matching unique constraint and
  indexes for production checkpoint idempotency.
- Modify: `src/trading/repositories/mixins/strategy.py` and
  `src/trading/repositories/in_memory.py` — due candidate/context load plus
  idempotent outcome/replay-run persistence.
- Modify: `src/trading/phases/_shell/dispatch.py`, `src/scheduler/jobs/__init__.py`,
  and `src/scheduler/service.py` — register the outcome phase before reflection.
- Modify: `src/trading/phases/strategy_evolution/pipeline.py`,
  `src/trading/phases/strategy_evolution/evidence.py`, and repository loaders —
  deterministic bounded evidence builder and provider-call preflight.
- Modify: `src/web/routers/loaders/universe_learning.py`,
  `src/web/presenters/today_learning_strategies.py`, and
  `src/templates/today/_tab_system.html` — separate Current Strategies, Strategy
  Edge, Traded Performance, and proposal/runtime state.
- Modify: `plan/progress_tracker.md`, `documents/repo_overview.md`, and deployment
  documentation — tracking, architecture overview, explicit 60-day backfill, and
  `SHOW data_directory` disk-backed Postgres verification.
- Create/Modify tests under `tests/trading/`, `tests/db/`, `tests/web/`,
  `tests/scheduler/`, and `tests/scripts/` named below.

## Task 1: Define the pure outcome contract

**Files:**
- Create: `src/trading/outcomes/horizons.py`
- Create: `src/trading/outcomes/evaluator.py`
- Create: `tests/trading/test_outcome_horizons.py`
- Create: `tests/trading/test_persisted_candidate_outcomes.py`
- Create: `tests/trading/test_outcome_price_loader.py`

- [ ] **Step 1: Write failing horizon-policy tests** for every approved canonical
  horizon, an XNYS holiday/weekend transition, and `unsupported_horizon`.
- [ ] **Step 2: Run the focused tests** and verify they fail because the outcome
  modules do not exist.
- [ ] **Step 3: Implement `OutcomeHorizonPolicy`** using an injected XNYS calendar;
  map exactly the approved horizon table and reject unknown values without a
  fallback.
- [ ] **Step 4: Re-run focused horizon tests** and verify they pass.
- [ ] **Step 5: Write failing calculation tests** for bullish, bearish, neutral,
  and unsupported direction rows; assert alpha, sign-adjusted MFE/MAE, primary
  comparator behavior, and sample-standard-deviation information ratio.
- [ ] **Step 6: Run the calculation tests** and verify they fail because the
  evaluator is absent.
- [ ] **Step 7: Implement the pure evaluator** with exact direction mapping
  (`bullish|long`, `bearish|short|risk_off`, `neutral`, unsupported), raw-return
  audit metadata, terminal observational handling for unsupported directions, and
  no inference from free text.
- [ ] **Step 8: Re-run the focused outcome tests** and verify they pass.
- [ ] **Step 9: Commit** pure policy/evaluator/tests with
  `feat: add persisted candidate outcome primitives`.

## Task 2: Persist lineage, manual phase identity, and due-candidate context

**Files:**
- Create: `alembic/versions/033_candidate_outcome_maturation_idempotency.py`
- Modify: `src/db/models/trading/reflection.py`
- Modify: `src/db/models/trading/strategy.py`
- Modify: `src/trading/repositories/mixins/strategy.py`
- Modify: `src/trading/repositories/in_memory.py`
- Create: `tests/db/test_candidate_outcome_maturation_migration.py`
- Create: `tests/trading/test_outcome_candidate_repository.py`

- [ ] **Step 1: Write failing migration/model tests** for the exact production
  outcome unique key `(candidate_score_id, evaluation_status, horizon_end_at)`, a
  due-query index, and a `historical_replay_runs` lineage contract carrying
  `evaluation_as_of_session`.
- [ ] **Step 2: Add failing lineage tests** that assert UUIDv5 is derived from
  `(source_decision_time, snapshot_type, evaluation_as_of_session,
  persisted_candidate_maturation)`: same tuple retries reuse one run; a different
  evaluation session creates a separate run.
- [ ] **Step 3: Add failing manual-lineage tests** proving pre-open, manual, and
  intraday candidates remain distinct. Migrate `strategy_runs` and
  `historical_replay_runs` snapshot-type checks to accept the canonical `manual`
  value rather than folding manual decisions into pre-open/intraday.
- [ ] **Step 4: Add failing repository tests** asserting persisted decision-time
  candidate, classification/watch, comparator identity/member/weight, and selected
  order/fill lineage are loaded; due filtering omits an already-materialized
  checkpoint.
- [ ] **Step 5: Run these tests** and verify the expected missing API/schema
  failures.
- [ ] **Step 6: Implement the Alembic revision, ORM constraints/indexes, DTOs,
  UUIDv5 helper, repository reads, and idempotent upserts.** Offline reconstructed
  rows with null candidate ids remain compatible and are not subject to production
  maturation uniqueness.
- [ ] **Step 7: Run focused repository/migration tests** and verify they pass.
- [ ] **Step 8: Commit** with `feat: persist idempotent candidate outcomes`.

## Task 3: Build the production maturation pipeline and explicit backfill command

**Files:**
- Create: `src/trading/outcomes/pipeline.py`
- Create: `src/trading/outcomes/__init__.py`
- Create: `src/trading/runtime/outcomes.py`
- Create: `scripts/run_outcome_backfill.py`
- Create: `tests/trading/test_outcome_evaluation_pipeline.py`
- Create: `tests/trading/test_runtime_outcomes.py`
- Create: `tests/scripts/test_run_outcome_backfill.py`

- [ ] **Step 1: Write failing `OutcomePriceLoader` tests** with an injected XNYS
  calendar and fake provider. Cover pre-open session-open, intraday first-minute,
  and checkpoint-close boundaries; split-adjusted OHLC paths; one deterministic
  union of candidate/QQQ/SPY/persisted sector-theme/peer/opportunity symbols;
  persisted composite weights; structured missing-symbol/provider errors; and
  provider/feed/adjustment/resolution audit metadata.
- [ ] **Step 2: Run them** and verify the pipeline import/API is missing.
- [ ] **Step 3: Implement `OutcomePriceLoader`** and verify its tests pass before
  wiring it to the pipeline.
- [ ] **Step 4: Write failing pipeline tests** for per-source-date transaction
  isolation, complete versus pending prices, degraded provider results,
  interim/final rows, stable reruns, and complete selected-trade closing lineage.
  Assert partial reductions do not finalize; a fully closed selected position ends
  at actual close fill/timestamp with `finalization_reason=trade_closed`; an open
  selected position ends at canonical horizon with `horizon_expired`; non-traded,
  rejected, watch, manual-review, and shadow rows always end at horizon.
- [ ] **Step 5: Run pipeline tests** and verify the expected missing behavior.
- [ ] **Step 6: Implement `OutcomeEvaluationPipeline`** over repository-loaded
  persisted candidates. Require primary comparator coverage for directional final
  outcomes, report optional comparator coverage without silent reweighting, and
  use the persisted selected order/fill lineage to apply early finalization only
  after a complete close.
- [ ] **Step 7: Add the live runtime entrypoint** returning `passed`, `skipped`,
  `failed`, or metadata-backed `degraded` reports; test injected dependencies
  without a database/provider.
- [ ] **Step 8: Add `run_outcome_backfill.py`** with required explicit date range,
  `--dry-run`, and `--resume`; write standalone smoke tests proving dry-run has no
  mutation and a small fixture range is resumable.
- [ ] **Step 9: Run focused pipeline/runtime/script tests** and verify they pass.
- [ ] **Step 10: Commit** with `feat: mature persisted candidate outcomes`.

## Task 4: Schedule outcomes before reflection/evolution

**Files:**
- Create: `src/scheduler/jobs/outcome_evaluation_job.py`
- Modify: `src/trading/phases/_shell/dispatch.py`
- Modify: `src/scheduler/jobs/__init__.py`
- Modify: `src/scheduler/service.py`
- Create: `tests/scheduler/test_outcome_evaluation_job.py`
- Modify: `tests/test_scheduler_jobs.py`
- Modify: `tests/trading/test_runtime_dispatch.py`

- [ ] **Step 1: Write failing tests** asserting the `outcome_evaluation` phase
  dispatches to the live runtime, the job is registered, and its 16:10 ET schedule
  precedes reflection at 16:20 and evolution at 16:50.
- [ ] **Step 2: Run the tests** and verify expected missing job/handler failures.
- [ ] **Step 3: Implement the scheduled job and dispatch registration** with the
  same safe status logging as the existing post-close jobs.
- [ ] **Step 4: Re-run scheduler/runtime-dispatch tests** and verify they pass.
- [ ] **Step 5: Commit** with `feat: schedule outcome evaluation before learning`.

## Task 5: Bound strategy-evolution evidence before any LLM call

**Files:**
- Create: `src/trading/phases/strategy_evolution/evidence_builder.py`
- Modify: `src/trading/phases/strategy_evolution/pipeline.py`
- Modify: `src/trading/repositories/mixins/strategy.py`
- Modify: `src/trading/phases/strategy_evolution/__init__.py`
- Create: `tests/trading/test_strategy_evolution_evidence_builder.py`
- Modify: `tests/trading/test_strategy_evolution_evidence.py`
- Modify: `tests/trading/test_runtime_strategy_evolution_live.py`

- [ ] **Step 1: Write failing evidence-builder tests** for all deterministic caps
  (20 evidence groups, 5 representatives per group, 50 rejected groups, 20
  rejected groups with 2 examples each/40 total, 20 hints, 30 learning factors),
  ranking ties, representative diversity, and 120 KiB rendered-input preflight.
- [ ] **Step 2: Run them** and verify the builder is missing.
- [ ] **Step 3: Implement `StrategyEvolutionEvidenceBuilder`** with the approved
  60-day reflection/rejection and 270-day final-outcome windows, deterministic
  aggregation/ranking, exact evidence gates, and compact existing-strategy
  payloads.
- [ ] **Step 4: Integrate the builder before `StrategyEvolutionAgent.run`.** If
  evidence is insufficient or the rendered structured input exceeds 120 KiB,
  persist a skipped runtime reason and do not call the LLM/provider.
- [ ] **Step 5: Re-run evidence/evolution runtime tests** and verify they pass.
- [ ] **Step 6: Commit** with `fix: bound strategy evolution evidence input`.

## Task 6: Repair the System-tab read model and semantic labels

**Files:**
- Modify: `src/web/routers/loaders/universe_learning.py`
- Modify: `src/web/presenters/today_learning_strategies.py`
- Modify: `src/templates/today/_tab_system.html`
- Create: `src/trading/outcomes/ledger.py`
- Modify: `tests/web/test_today_learning_strategies.py`
- Modify: `tests/web/test_today.py`
- Create: `tests/web/test_today_system_strategy_state.py`

- [ ] **Step 1: Write failing `ExecutionLedgerReducer` tests** for chronological
  stock partial fills, reductions, complete exits, multiple cycles, open cycles,
  and unpairable legacy fills; test option cycles grouped by option-strategy
  decision/order lineage. Assert completed-cycle realized P&L is the sum of fill
  cash effects and return is P&L divided by opening cash at risk.
- [ ] **Step 2: Run reducer tests** and verify the reducer is missing.
- [ ] **Step 3: Implement the pure `ExecutionLedgerReducer`** with a documented
  input DTO and completed/open/unpairable output counts; it must never infer P&L
  for unpairable cycles.
- [ ] **Step 4: Re-run reducer tests** and verify they pass.
- [ ] **Step 5: Write failing presenter/loader tests** showing seed/manual/current
  definitions appear without proposals or outcomes; Strategy Edge reports final
  outcomes in return/alpha units; Traded Performance uses completed execution
  cycles only; and an empty ten-day proposal region exposes latest retained date
  plus runtime reason.
- [ ] **Step 6: Run them** and verify current `total_pnl=sum(alpha)` and empty
  states fail the desired contract.
- [ ] **Step 7: Implement independent read-model loaders.** Current strategies
  load all definitions; edge loads only candidate outcome evaluations; performance
  uses the proven execution-ledger reducer with open/unpairable counts; proposal history
  remains ten-day primary with bounded historical/runtime context.
- [ ] **Step 8: Implement template changes** using existing System-tab styling:
  Current Strategies, Strategy Edge, Traded Performance, Proposal History & Runtime
  State. Do not label alpha as dollar P&L.
- [ ] **Step 9: Run web tests** and render-verify desktop and narrow System tabs
  using the `ui-development` checklist.
- [ ] **Step 10: Commit** with `fix: explain strategy state in system tab`.

## Task 7: Integration verification, operator documentation, and tracker

**Files:**
- Modify: `documents/repo_overview.md`
- Modify: deployment/operator documentation under `documents/`
- Modify: `plan/progress_tracker.md`
- Modify: `plan/review_backlog.md` if its replay/evolution item is now resolved
- Create: `tests/scripts/test_run_outcome_backfill_smoke.py` if a fixture smoke
  cannot live in the Task 3 test file.

- [ ] **Step 1: Write/update the standalone fixture smoke** for a small backfill
  range and assert no external API is required.
- [ ] **Step 2: Run targeted suites** for outcomes, repository/migrations,
  scheduler, evolution, and System UI.
- [ ] **Step 3: Run the project unit suite** and address regressions.
- [ ] **Step 4: Verify deployment safety.** Document and execute the read-only
  `SHOW data_directory;` check against the configured Postgres before any operator
  backfill; confirm the result is a persistent mounted disk path, not tmpfs or a
  container anonymous volume.
- [ ] **Step 5: Update overview, deployment runbook, progress tracker, and backlog**
  with exact verification evidence and the explicit production backfill command.
- [ ] **Step 6: Commit** with `docs: document outcome maturation operations`.

## Final Verification

- [ ] `git diff --check` is clean.
- [ ] Targeted outcome, migration/repository, scheduler, evolution, script, and
  web tests pass.
- [ ] Full unit suite passes, or any pre-existing failures are separately recorded.
- [ ] Fixture smoke proves a dry-run has no writes and a resumed explicit range is
  idempotent.
- [ ] UI render verification shows no raw machine values, no incorrect P&L label,
  and clear empty/runtime states.
- [ ] Production backfill is not executed automatically; it remains a documented
  operator action after database verification.
