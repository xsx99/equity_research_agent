# PR 38 Wire Historical Replay To Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **Direction gate (read first):** Backlog #6 frames this as a decision — *"decide replay direction; build if the learning loop is near-term."* This is **feature work**, not a reliability fix; do NOT start it ahead of PR 35/36 unless the user has confirmed the learning loop is near-term. The schema anchor is deliberately retained (memory: keep `historical_replay_runs`; replay wired up later as A3-ii). If the user has confirmed: proceed. If not: this doc stays a ready-to-execute spec.

**Goal:** Make historical replay actually persist and surface. Today `HistoricalReplayRunner` (`src/trading/replay/historical.py`) calls `repository.save_historical_replay_run(...)` and `repository.save_candidate_outcome_evaluations(...)`, but those methods exist **only** on `InMemoryTradingRepository` — not on the production `SqlAlchemyTradingRepository`. Nothing triggers a replay run, so `historical_replay_runs` stays empty and `candidate_outcome_evaluations.historical_replay_run_id` stays NULL. This PR: (1) implements the two missing `save_*` methods on the SQLAlchemy repo, (2) adds a trigger (scheduled or on-demand), (3) surfaces replay outcomes in the `/today` UI by reusing existing candidate-evaluation components.

**Architecture:** The ORM tables already exist (`src/db/models/trading/reflection.py:28 HistoricalReplayRun`, `:57 CandidateOutcomeEvaluation`). The runner is provider-agnostic (it takes a `repository`). The gap is purely the SQLAlchemy persistence methods + a runtime entrypoint + a presenter. Replay outcomes are the *same shape* as live post-decision evaluations (`candidate_outcome_evaluations`, FK `historical_replay_run_id`), so the UI half reuses the Candidates-tab evaluation components (design 14 §9 confirms this).

**Tech Stack:** Python, SQLAlchemy, APScheduler (existing scheduler), Jinja/presenter, pytest.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md` — replay / outcome-evaluation contract
3. `plan/design/07_replay_reflection_learning.md`
4. `plan/implementation/pr_03_strategy_matching_replay.md`, `pr_09_reflection_learning_factors.md`
5. `plan/progress_tracker.md` — **Recent** section only
6. `plan/review_backlog.md` — item #6

## Context: what exists vs what is missing (verified)

- Runner: `src/trading/replay/historical.py` — fully implemented, deterministic. At lines 132 and 137 it calls `save_historical_replay_run(completed_run)` and `save_candidate_outcome_evaluations(outcomes)`.
- In-memory repo HAS both: `src/trading/repositories/in_memory.py:334` (`save_historical_replay_run`) and `:337` (`save_candidate_outcome_evaluations`).
- SQLAlchemy repo MISSING both: `src/trading/repositories/mixins/strategy.py` defines `save_strategy_run` (:69), `save_candidate_scores` (:125), `save_watch_candidates` (:159), `save_trade_classifications` (:183) — but neither replay method. So calling the runner with the production repo raises `AttributeError`.
- ORM models present and indexed: `historical_replay_runs` (run metadata, status check `running|succeeded|failed`, snapshot_type check `pre_open|intraday`) and `candidate_outcome_evaluations` (FK to the run, `ondelete="SET NULL"`, plus FKs to `candidate_scores`, `trade_classifications`, `peer_baskets`).
- Record dataclasses: `HistoricalReplayRunRecord` (`historical.py:24`) and `CandidateOutcomeEvaluationRecord` (`src/trading/replay/outcomes.py`).

## Guardrails

- Mirror the existing `save_*` patterns in `mixins/strategy.py` (upsert-by-PK, set columns from the record, `self.session.flush()`). Do not invent a new persistence style.
- Keep the in-memory repo and the SQLAlchemy repo behaviorally interchangeable for the runner — a replay run that works on in-memory must work identically on SQLAlchemy (same record in → same rows out).
- Respect the model `CheckConstraint`s (status, snapshot_type, trade_identity, evaluation_status). Map record values to allowed enum strings; fail loudly on unknown values rather than writing a row that violates the constraint.
- The trigger must be opt-in / rate-limited and must not interfere with the live pre-open / intraday / reflection phases (it reconstructs from stored PIT snapshots — read-only against signal data).
- Do not drop or alter the replay tables (memory).
- UI: observation/audit surface only — replay outcomes are read-only (memory: `ui-is-observation-surface`).

## File Map

- Modify: `src/trading/repositories/mixins/strategy.py` (or the most appropriate mixin — confirm where outcome/replay persistence belongs; `strategy.py` holds the sibling `save_candidate_scores`) — add `save_historical_replay_run` + `save_candidate_outcome_evaluations`
- Modify: `src/trading/repositories/_base_payloads.py` (if a load/read payload for outcomes is needed for the UI)
- Create: `src/trading/runtime/replay.py` — `run_historical_replay_once(...)` runtime entrypoint mirroring `run_reflection_once` (`src/trading/runtime/reflection.py:141`)
- Modify: the scheduler wiring (locate via `grep -rn "run_reflection_once\|add_job\|APScheduler\|scheduler" src/trading/runtime/ src/`) — register the replay job (or expose an on-demand CLI/endpoint)
- Modify/Create: `src/web/presenters/today_candidates.py` (or a replay presenter) — load replay outcomes for display
- Modify: `src/templates/today/_tab_candidates.html` (or wherever evaluation components live) — render replay outcomes via the existing evaluation-timeline / history components
- Create: `tests/trading/test_pr38_replay_wiring.py`
- Modify: `plan/progress_tracker.md`, `plan/review_backlog.md`

## Task 1: Implement the two SQLAlchemy `save_*` methods

**Files:** `src/trading/repositories/mixins/strategy.py`.

- [ ] Step 1: Write a failing test (`test_pr38_replay_wiring.py`) that runs `HistoricalReplayRunner.run(...)` with a `SqlAlchemyTradingRepository` over a fixture session and asserts a `historical_replay_runs` row + N `candidate_outcome_evaluations` rows with the FK set. It should currently raise `AttributeError`.
- [ ] Step 2: Implement `save_historical_replay_run(self, run: HistoricalReplayRunRecord) -> None`: upsert the `HistoricalReplayRun` row by `historical_replay_run_id` (`_to_uuid`), set `decision_time`, `snapshot_type`, `status`, `started_at`, `completed_at`, `decision_filter_json`, `outcome_horizon_policy_json`, `metadata_json`, then `self.session.flush()`. Use the same `_to_uuid` / dict-copy helpers the sibling methods use.
- [ ] Step 3: Implement `save_candidate_outcome_evaluations(self, outcomes) -> None`: for each `CandidateOutcomeEvaluationRecord`, upsert by `candidate_outcome_evaluation_id`, set every column (including `historical_replay_run_id`, `candidate_score_id`, `trade_classification_id`, `peer_basket_id` via `_to_uuid_or_none`, the Numeric returns via `Decimal(str(...))`-style coercion matching siblings, and the JSONB fields). `flush()` once at the end. Match the `save_candidate_scores` batching style (`strategy.py:125`).
- [ ] Step 4: Confirm enum/constraint safety — map `status`/`snapshot_type`/`evaluation_status`/`trade_identity` to allowed values; raise on unknown rather than writing a constraint-violating row.
- [ ] Step 5: Make the test pass. Add a parity assertion: same runner + same fixture against the in-memory repo yields the same logical rows.

## Task 2: Runtime entrypoint

**Files:** `src/trading/runtime/replay.py`.

- [ ] Step 1: Add `build_historical_replay_dependencies(session)` + `run_historical_replay_once(*, decision_time, horizon_end_at, snapshot_type="pre_open", dependencies=None)` mirroring the structure of `run_reflection_once` (`reflection.py:129-156`) — open a session if none injected, build the runner with `SqlAlchemyTradingRepository` + a real `OutcomeEvaluator`, run, and return a `build_runtime_report(phase="historical_replay", ...)` summary (`run_id`, `candidate_count`, `outcome_count`, `status`).
- [ ] Step 2: Decide the default replay window: `decision_time` = a past trading day's pre-open instant; `horizon_end_at` = decision_time + the outcome horizon (reuse the horizon policy from `pr_03`/design 07 — do not hardcode a new one). Surface these as parameters so the trigger can backfill a range.
- [ ] Step 3: Unit-test the entrypoint with injected fake dependencies (no DB), asserting the report shape.

## Task 3: Trigger (scheduled or on-demand)

**Files:** scheduler wiring (locate first).

- [ ] Step 1: Locate the scheduler registration (where `run_reflection_once` / pre-open / intraday jobs are registered — `grep -rn "run_reflection_once\|add_job\|CronTrigger\|scheduler\." src/`).
- [ ] Step 2: Choose ONE trigger mode for v1 and implement it (state the choice in the PR description):
  - **(a) Scheduled** — a daily/after-close job that replays the just-closed day (or a rolling backfill). Must run AFTER reflection, be rate-limit conscious, and not contend with live phases.
  - **(b) On-demand** — a CLI command / internal endpoint that takes a date (range) and runs replay. Lower risk; good first step.
  - Recommended v1: **on-demand** (b) first to validate persistence + UI with real data, then add the scheduled job (a) once proven. Note the deferral of (a) in the tracker if you stop at (b).
- [ ] Step 3: Guard against duplicate runs for the same `(decision_time, snapshot_type)` — either idempotent upsert keyed on that pair or a pre-check; document the choice.
- [ ] Step 4: Smoke-style test that the trigger calls the entrypoint with the right window (standalone, no live providers — per repo rules).

## Task 4: Surface replay outcomes in `/today`

**Files:** presenter + candidates template.

- [ ] Step 1: Add a repository read for replay outcomes (by `historical_replay_run_id` or recent runs) — a `load_*` method returning `candidate_outcome_evaluations` rows joined to their run, shaped for the presenter. Follow `_base_payloads.py` payload-shaping conventions.
- [ ] Step 2: In the Candidates presenter (`today_candidates.py`), expose replay outcomes. Per design 14 §9, replay outcomes are the same shape as live post-decision evaluations, so reuse the existing evaluation-timeline / history-card / claim↔evidence components rather than building a new screen. Clearly label them as **replay** (backtest) vs live so an auditor isn't misled.
- [ ] Step 3: Render through the existing components; respect the `ui-development` skill (machine values filtered, no new unstyled classes, focus styles). Render-verify (handoff screenshot — no local app env).
- [ ] Step 4: Presenter unit test for the outcome payload shaping + the replay-vs-live labeling.

## Task 5: Tests, tracker, backlog

- [ ] Step 1: `tests/trading/test_pr38_replay_wiring.py` — SQLAlchemy save round-trip, in-memory parity, entrypoint report shape, trigger window, presenter payload.
- [ ] Step 2: Run targeted tests, then the broader replay/repository/web suites. Record results in the PR.
- [ ] Step 3: Prepend a dated `plan/progress_tracker.md` **Recent** entry; note which trigger mode shipped and what was deferred.
- [ ] Step 4: In `plan/review_backlog.md`, mark #6 resolved (or partially, if only on-demand shipped).

## Done when

- `HistoricalReplayRunner.run(...)` against the production `SqlAlchemyTradingRepository` persists a `historical_replay_runs` row and `candidate_outcome_evaluations` rows with `historical_replay_run_id` set (not NULL).
- A trigger (on-demand and/or scheduled) produces replay runs over real stored PIT snapshots without contending with live phases.
- Replay outcomes are visible in `/today` via the existing evaluation components, labeled as replay vs live.
- In-memory and SQLAlchemy repos remain interchangeable for the runner; tests pass; tracker + backlog updated.
