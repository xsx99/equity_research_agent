# PR 60: Cross-Sectional Relative-Strength Ranking Implementation Plan

Status: Approved after three independent plan-review passes on 2026-07-22

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy absolute one-day relative-strength formula with a persisted, point-in-time cross-sectional universe rank that narrows expensive pre-open research to configurable Top-N candidates plus forced tickers and remains reproducible in replay.

**Architecture:** Add a focused `src/trading/ranking/` domain package for pure metrics, cohort resolution, scoring, selection, and evaluation. A live ranking pipeline batch-loads 65 adjusted daily sessions for the eligible universe and SPY, persists the complete ranking cohort through new repository methods, then gives pre-open signal ingestion a narrowed research snapshot carrying ranking overlays. Strategy scoring consumes only the canonical ranking signal; replay loads stored ranking inputs/config and walk-forward reporting evaluates rank deciles without changing the frozen v1 model.

**Tech Stack:** Python 3.13, dataclasses, `statistics`, pytest, SQLAlchemy, PostgreSQL JSONB, Alembic, existing Alpaca batch-bars provider, existing pre-open/replay pipelines.

---

## Required Reading And Baseline

- `documents/general_instructions.md`
- `plan/design/2026-07-21-cross-sectional-relative-strength-ranking.md`
- `plan/implementation/README.md`
- `plan/design/04_signal_snapshots.md`
- `plan/design/07_replay_reflection_learning.md`
- `plan/design/08_data_model.md`
- `src/trading/data_sources/universe.py`
- `src/trading/data_sources/live_universe.py`
- `src/trading/phases/preopen/runner.py`
- `src/trading/phases/preopen/dependencies.py`
- `src/trading/signals/snapshots.py`
- `src/trading/strategies/matching.py`
- `src/trading/phases/replay/historical.py`

Accepted clean-branch baseline on 2026-07-22: `970 passed, 12 failed`. The 12 failures are pre-existing: three unavailable-local-Postgres integration cases, eight option/hedge execution cases, and one macro-event smoke case. New focused tests must pass, and final full-suite output must not add failures beyond that recorded baseline.

## File Map

### Pure ranking domain

- Create `src/trading/ranking/__init__.py`: public ranking records/config/pipeline exports.
- Create `src/trading/ranking/records.py`: immutable bar, raw-metric, cohort, row, run, and result records.
- Create `src/trading/ranking/config.py`: frozen `cross_sectional_rs_v1` weights, thresholds, windows, Top-N, confidence floor, and serializable config.
- Create `src/trading/ranking/metrics.py`: point-in-time adjusted-bar normalization and raw metric formulas.
- Create `src/trading/ranking/percentiles.py`: average-rank percentiles with ties and deterministic liquidity quartiles.
- Create `src/trading/ranking/scoring.py`: cohort fallback, optional-weight renormalization, penalties, confidence, contributors, ranking, and shortlist selection.
- Create `src/trading/ranking/forced.py`: reason-preserving forced-ticker resolution across manual requests, watchlist pins, open positions, and explicit manual includes.
- Test `tests/trading/ranking/test_metrics.py` and `tests/trading/ranking/test_scoring.py`.

### Persistence

- Modify `src/db/models/trading/universe.py`: add `UniverseRankingRun` and `UniverseRanking` ORM models/relationships.
- Modify `src/db/models/trading/enums.py`: add ranking run/row status enums following repository conventions.
- Modify `src/db/models/trading/strategy.py`: add nullable ranking run/row foreign keys on `CandidateScore`.
- Modify `src/db/models/__init__.py`: export new models.
- Create `alembic/versions/032_cross_sectional_relative_strength_ranking.py`: tables, constraints, indexes, and candidate traceability columns.
- Modify `src/trading/repositories/mixins/runtime_misc.py`: save/load ranking runs and rows atomically, load point-in-time peer/relationship membership, and load stored ranking cohorts for replay.
- Modify `src/trading/repositories/mixins/strategy.py`: persist candidate ranking references.
- Modify `src/trading/repositories/in_memory.py`: mirror ranking persistence for pipeline/replay tests.
- Test `tests/db/test_trading_models.py`, `tests/db/test_cross_sectional_ranking_migration.py`, and `tests/trading/test_sqlalchemy_repository.py`.

### Live input and pre-open orchestration

- Create `src/trading/ranking/loader.py`: bounded batch input loader using `fetch_daily_bars_for_symbols`, exchange-calendar cutoff, explicit SPY validation, provider telemetry, provenance/availability mapping, and partial-chunk error metadata.
- Create `src/trading/ranking/calendar.py`: `exchange_calendars`-backed `XNYS` session adapter for expected completed-session and freshness decisions.
- Create `src/trading/ranking/pipeline.py`: run lifecycle, status policy, persistence-before-consumption, and research-set construction.
- Create `src/trading/ranking/peers.py`: point-in-time configured-peer/industry/sector membership resolution intersected with the frozen eligible universe.
- Modify `src/trading/phases/preopen/dependencies.py`: add ranking dependency protocol/configuration and wire the Alpaca batch loader.
- Modify `src/trading/phases/preopen/runner.py`: sync/load portfolio positions before ranking, persist universe first, resolve forced reasons, run/persist rank second, stop automatic scanning on ranking failure, and send the research set only to expensive signal ingestion.
- Modify `src/trading/data_sources/universe.py`: add a helper for deriving a research-set snapshot without mutating the full universe snapshot.
- Test `tests/trading/ranking/test_loader.py`, `tests/trading/ranking/test_pipeline.py`, and `tests/trading/test_runtime_live.py`.
- Modify `requirements.txt`: add a bounded `exchange-calendars` dependency used only through the ranking calendar adapter.

### Signal and strategy integration

- Modify `src/trading/signals/snapshots.py`: merge a validated rank overlay into `technical` and preserve ranking source refs/availability.
- Modify `src/trading/signals/pipeline.py`: accept ranking overlays while retaining forced-ticker selection source semantics.
- Modify `src/trading/strategies/matching.py`: replace every direct one-day SPY/QQQ score contribution with canonical relative-strength score; block ranking-required strategies when the overlay is missing.
- Modify `src/trading/strategies/catalog.py` only if required-signal names need to be made explicit.
- Modify `src/trading/strategies/scoring.py`: carry ranking IDs into candidate records/run metadata.
- Modify `src/trading/repositories/mixins/strategy.py`: write ranking FKs from candidate records.
- Test `tests/trading/test_technical_signals.py`, `tests/trading/test_pipeline.py`, and `tests/trading/test_strategy_matching.py`.

### Replay, validation, smoke, and docs

- Create `src/trading/ranking/evaluation.py`: chronological split policy, future 5/20/60-day rank outcomes, decile summaries, monotonicity, turnover/stability, drawdown/volatility, penalty ablations, and offline legacy benchmark.
- Modify `src/trading/phases/replay/historical.py`: load the persisted ranking cohort/model config and bind reconstructed candidates to original ranking IDs without future membership.
- Modify `src/trading/phases/replay/outcomes.py`: attach rank/decile and peer/sector attribution metadata.
- Create `scripts/run_trading_universe_ranking_smoke.py`: explicit ticker list, rate-limited batch input, JSON/human output, no expensive research, and opt-in persistence only.
- Create `scripts/run_trading_universe_ranking_validation.py`: executable offline walk-forward report from persisted ranking/outcome history with non-overlapping windows and a saved JSON artifact.
- Create `tests/test_run_trading_universe_ranking_smoke.py` and `tests/trading/ranking/test_evaluation.py`.
- Create `.env.example`: document ranking Top-N, cohort minimum, confidence floor, and smoke behavior.
- Modify `src/core/config.py`: own validated environment-backed ranking defaults.
- Modify `tests/test_config.py`: lock ranking defaults and invalid-range rejection.
- Modify `documents/repo_overview.md`: describe the new ranking boundary and persisted tables.
- Modify `plan/progress_tracker.md`: add completion evidence.
- Update this plan's progress table and checkboxes after each task.

## Progress Tracker

| Task | Status | Evidence |
| --- | --- | --- |
| 1. Pure metric and percentile primitives | Complete | `pytest tests/trading/ranking/test_metrics.py -q` → 48 passed |
| 2. Cohort scoring, forced reasons, confidence, rank, shortlist | Pending | — |
| 3. ORM, migration, repository persistence | Pending | — |
| 4. Bounded input loader and ranking pipeline | Pending | — |
| 5. Pre-open narrowing and signal overlay | Pending | — |
| 6. Strategy cutover and traceability | Pending | — |
| 7. Replay and walk-forward evaluation | Pending | — |
| 8. Standalone smoke and operations docs | Pending | — |
| 9. Full verification and completion docs | Pending | — |

## Task 1: Pure Metric And Percentile Primitives

**Files:**

- Create `src/trading/ranking/records.py`
- Create `src/trading/ranking/config.py`
- Create `src/trading/ranking/metrics.py`
- Create `src/trading/ranking/percentiles.py`
- Create `src/trading/ranking/__init__.py`
- Create `tests/trading/ranking/test_metrics.py`

- [x] **Step 1: Write failing metric tests**

  Cover 1/5/20/60-session simple returns, SPY alpha, latest-volume versus previous-20 mean, sample 20-return annualized volatility, 60-close drawdown, positive-return concentration, invalid zero baselines, insufficient history, duplicate dates, bars after `decision_time`, and provenance fields.

- [x] **Step 2: Run RED metric tests**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_metrics.py -q`

  Expected: collection/import failure because `src.trading.ranking` does not exist.

- [x] **Step 3: Implement immutable inputs and formulas**

  Normalize bars ascending by session date, discard rows not available by the decision cutoff, reject duplicate session dates deterministically, require 61 closes and 21 volumes, and use `statistics.stdev(...)*sqrt(252)` for realized volatility.

- [x] **Step 4: Add failing percentile tests**

  Test zero-based average rank divided by `n-1`, tied values, missing values excluded from cohorts, single-value behavior, deterministic output independent of input order, and average-rank liquidity quartiles with `[0,.25)`, `[.25,.50)`, `[.50,.75)`, `[.75,1]` boundaries.

- [x] **Step 5: Implement percentile and quartile helpers**

- [x] **Step 6: Run GREEN metric tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_metrics.py -q`

## Task 2: Cohort Scoring, Confidence, Rank, And Shortlist

**Files:**

- Create `src/trading/ranking/scoring.py`
- Create `src/trading/ranking/forced.py`
- Create `src/trading/ranking/peers.py`
- Create `tests/trading/ranking/test_scoring.py`

- [ ] **Step 1: Write failing cohort-resolution tests**

  Test peer basket → industry → unavailable, sector → unavailable, market cohorts, liquidity quartile → market fallback, configurable minimum cohort size, and the rule that missing peer/sector does not fall back to market. Also test point-in-time `PeerBasket`/`TickerRelationship` validity windows, intersection with the frozen universe, exact membership/source refs, and raw sector/industry/peer relative-return metrics.

- [ ] **Step 2: Run RED scoring tests**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_scoring.py -q`

- [ ] **Step 3: Write failing formula and missing-component tests**

  Lock configured weights `0.30/0.20/0.15/0.15/0.10/0.10`, optional-only renormalization, each required-component missing state, one-day concentration thresholds/max, both volatility/drawdown sub-penalties, combined penalty max, final score clamp, and peer/sector relative-return persistence.

- [ ] **Step 4: Implement cohort resolution, component normalization, and v1 scoring**

- [ ] **Step 5: Add failing confidence/contributor tests**

  Lock component coverage, freshness `1/.5/0`, primary cohort specificity/size, benchmark coverage, structured positive/negative contributors, and missing input details.

- [ ] **Step 6: Implement confidence and explanations**

- [ ] **Step 7: Add failing rank/selection/forced-reason tests**

  Lock score → confidence → average dollar volume → ticker ordering, overall percentile, confidence filtering before Top-N, independent `manual_request`/`watchlist_pin`/`open_position`/`manual_include` reasons, multi-reason aggregation, deduplication, insufficient forced tickers, and automatic shortlist smaller than N.

- [ ] **Step 8: Implement forced resolver, rank, and research-set selection**

- [ ] **Step 9: Run GREEN scoring tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_metrics.py tests/trading/ranking/test_scoring.py -q`

## Task 3: ORM, Migration, And Repository Persistence

**Files:**

- Modify `src/db/models/trading/universe.py`
- Modify `src/db/models/trading/enums.py`
- Modify `src/db/models/trading/strategy.py`
- Modify `src/db/models/__init__.py`
- Create `alembic/versions/032_cross_sectional_relative_strength_ranking.py`
- Modify `src/trading/repositories/mixins/runtime_misc.py`
- Modify `src/trading/repositories/mixins/strategy.py`
- Modify `src/trading/repositories/in_memory.py`
- Modify `tests/db/test_trading_models.py`
- Create `tests/db/test_cross_sectional_ranking_migration.py`
- Modify `tests/trading/test_sqlalchemy_repository.py`

- [ ] **Step 1: Write failing ORM contract tests**

  Assert table names, one `(ranking_run_id,ticker)` row, row `decision_time`, score/confidence/percentile checks, exact run input/eligible/shortlist count invariants, run/rank + `(ticker,decision_time)` + shortlist indexes, universe snapshot FK, enum-backed run/row status constraints, JSON defaults, candidate ranking FKs, and ORM relationships.

- [ ] **Step 2: Run RED ORM tests**

  Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py -k universe_ranking -q`

- [ ] **Step 3: Implement ORM models and exports**

- [ ] **Step 4: Write failing migration tests**

  Inspect migration operations for both tables, constraints/indexes, candidate columns, `032 -> 031`, and complete downgrade behavior.

- [ ] **Step 5: Implement migration**

- [ ] **Step 6: Write failing repository round-trip/upsert tests**

  Test run-first persistence, complete cohort rows, idempotent update, duplicate prevention, JSON payloads, load-by-run, load-latest-at-decision-time, and candidate ranking references.

- [ ] **Step 7: Implement SQLAlchemy and in-memory repository methods**

- [ ] **Step 8: Run migration SQL/upgrade verification**

  Run `source ~/.venv/bin/activate && alembic upgrade head` against the configured test database when available, then downgrade to `031` and re-upgrade to `032`; when the database is unavailable, run Alembic offline SQL generation for upgrade/downgrade and record the environment limitation.

- [ ] **Step 9: Run GREEN persistence tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/db/test_trading_models.py tests/db/test_cross_sectional_ranking_migration.py tests/trading/test_sqlalchemy_repository.py -k 'universe_ranking or ranking_reference' -q`

## Task 4: Bounded Input Loader And Ranking Pipeline

**Files:**

- Create `src/trading/ranking/loader.py`
- Create `src/trading/ranking/calendar.py`
- Create `src/trading/ranking/pipeline.py`
- Create `tests/trading/ranking/test_loader.py`
- Create `tests/trading/ranking/test_calendar.py`
- Create `tests/trading/ranking/test_pipeline.py`
- Modify `requirements.txt`

- [ ] **Step 1: Write failing exchange-calendar tests**

  Lock `XNYS` session selection on ordinary weekdays, weekends, US market holidays, early-close sessions, and decision times immediately before and after the scheduled close. The adapter must return the latest fully completed session and expose its scheduled close in UTC.

- [ ] **Step 2: Implement the calendar adapter and bounded dependency**

  Add `exchange-calendars>=4.5,<5` to `requirements.txt`, isolate its API behind `RankingSessionCalendar`, and inject the adapter into the loader so tests and replay can use a deterministic fake.

- [ ] **Step 3: Write failing loader tests**

  Use a fake batch provider to assert one bounded request per configured chunk, 65-session lookback, SPY included without per-ticker calls, NYSE-calendar expected-last-completed-session cutoff, same cutoff/provenance/`available_for_decision_at`, existing provider-resilience request telemetry, partial chunk errors retained, and duplicate symbols removed.

- [ ] **Step 4: Run RED calendar/loader tests**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_calendar.py tests/trading/ranking/test_loader.py -q`

- [ ] **Step 5: Implement the bounded loader**

  Keep network I/O outside pure scoring, accept the provider/`RankingSessionCalendar`/telemetry recorder by dependency injection, map provider bar timestamps into auditable availability/provenance, and return explicit benchmark/failure metadata. Do not infer freshness from weekday arithmetic.

- [ ] **Step 6: Write failing pipeline status/persistence tests**

  Cover failed benchmark, fewer than `max(10, ceil(.20*input_count))` scored rows, degraded `<90%` or partial chunks, succeeded otherwise, insufficient rows persisted, persistence failure stops consumption, and full run/rows saved before result returned.

- [ ] **Step 7: Implement ranking pipeline lifecycle**

- [ ] **Step 8: Run GREEN calendar/loader/pipeline tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_calendar.py tests/trading/ranking/test_loader.py tests/trading/ranking/test_pipeline.py -q`

## Task 5: Pre-Open Narrowing And Signal Overlay

**Files:**

- Modify `src/trading/data_sources/universe.py`
- Modify `src/trading/phases/preopen/dependencies.py`
- Modify `src/trading/phases/preopen/runner.py`
- Modify `src/trading/signals/pipeline.py`
- Modify `src/trading/signals/snapshots.py`
- Modify `tests/trading/test_runtime_live.py`
- Modify `tests/trading/test_pipeline.py`
- Modify `tests/trading/test_technical_signals.py`

- [ ] **Step 1: Write failing runtime ordering/narrowing tests**

  Assert `universe scan → save full universe → portfolio sync/load positions → resolve forced reasons → rank/save full cohort → signal research set`, only Top-N plus forced tickers reach signal ingestion, every forced reason survives independently, and ranking failure prevents scanner research while allowing all forced tickers through non-ranking-dependent research/risk monitoring.

- [ ] **Step 2: Run RED runtime test**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py -k ranking -q`

- [ ] **Step 3: Implement dependency protocol and pre-open orchestration**

  Wire Top-N/min-cohort/confidence from validated settings in `src/core/config.py`. Keep watchlist pins separate from explicit manual includes, and load broker/repository positions before ranking rather than after strategy scoring. Do not alter the persisted full universe snapshot when deriving the research snapshot.

- [ ] **Step 4: Write failing overlay tests**

  Assert all canonical rank fields enter `technical`, raw one-day fields remain diagnostic, ranking refs/availability are auditable, insufficient rows do not masquerade as scores, and all forced-inclusion reasons remain preserved in ranking metadata. Candidate `selection_source` stays within the existing constraint: `manual_request` maps to `manual_request`, `watchlist_pin` maps to `watchlist_pin`, and `open_position`/`manual_include` use `scanner` while their true reasons remain in `forced_inclusion_reasons_json` and the technical ranking overlay.

- [ ] **Step 5: Implement overlay merge**

- [ ] **Step 6: Run GREEN runtime/signal tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/test_runtime_live.py tests/trading/test_pipeline.py tests/trading/test_technical_signals.py -q`

## Task 6: Strategy Cutover And Candidate Traceability

**Files:**

- Modify `src/trading/strategies/matching.py`
- Modify `src/trading/strategies/catalog.py`
- Modify `src/trading/strategies/scoring.py`
- Modify `src/trading/repositories/mixins/strategy.py`
- Modify `tests/trading/test_strategy_matching.py`
- Modify `tests/trading/test_pipeline.py`

- [ ] **Step 1: Write failing canonical-score tests**

  Assert relative-strength rotation/base breakout use `relative_strength_score`, catalyst/insider/valuation confirmation uses the same bounded signal, changing one-day SPY/QQQ values alone cannot change a candidate score, and no evidence key treats one-day RS as a weighted input.

- [ ] **Step 2: Run RED matcher tests**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py -k relative_strength -q`

- [ ] **Step 3: Replace legacy scoring paths**

  Keep strategy-specific candidate semantics, require a valid overlay for rotation/base breakout, use optional bounded confirmation elsewhere, and remove `_score_relative_strength`'s legacy formula entirely.

- [ ] **Step 4: Write failing missing-overlay/traceability tests**

  Assert ranking-required strategies emit explicit `technical.relative_strength_score` missing state and are non-actionable; candidate records/ORM rows reference ranking run/row IDs and source refs; and no forced reason is written into `CandidateScore.selection_source` outside its existing `scanner`/`manual_request`/`watchlist_pin`/`risk_manager` constraint.

- [ ] **Step 5: Implement candidate traceability**

- [ ] **Step 6: Prove no runtime legacy use remains**

  Run: `rg -n "max\(.*rs_vs_spy_1d|rs_vs_qqq_1d.*candidate|0\.35 \*.*rs_spy|0\.25 \*.*rs_qqq" src/trading`

  Expected: no weighted candidate-scoring matches.

- [ ] **Step 7: Run GREEN strategy tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/test_strategy_matching.py tests/trading/test_pipeline.py -q`

## Task 7: Replay And Walk-Forward Evaluation

**Files:**

- Create `src/trading/ranking/evaluation.py`
- Modify `src/trading/phases/replay/historical.py`
- Modify `src/trading/phases/replay/outcomes.py`
- Create `tests/trading/ranking/test_evaluation.py`
- Modify `tests/trading/test_historical_replay.py`
- Modify `tests/trading/test_outcome_evaluator.py`
- Create `scripts/run_trading_universe_ranking_validation.py`
- Create `tests/test_run_trading_universe_ranking_validation.py`

- [ ] **Step 1: Write failing replay PIT/reproduction tests**

  Assert replay loads the exact stored model/config/raw metrics/cohort membership, excludes later bars and revised peer membership, reproduces score/order, and carries original ranking IDs to candidates/outcomes.

- [ ] **Step 2: Run RED replay tests**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/test_historical_replay.py -k ranking -q`

- [ ] **Step 3: Implement persisted-ranking replay integration**

- [ ] **Step 4: Write failing walk-forward evaluator tests**

  Cover chronological calibration/evaluation split, 5/20/60-day returns and SPY/sector/peer alpha, decile hit rate/mean alpha, monotonicity, turnover/cohort stability, selected-cohort drawdown/volatility, both penalty ablations, and offline legacy benchmark. Reject overlapping or non-chronological windows.

- [ ] **Step 5: Implement deterministic evaluation report**

  The evaluator may compute the legacy formula only in the explicit offline benchmark function; production rank/scoring modules must not import it.

- [ ] **Step 6: Write failing executable validation tests**

  Assert the command loads persisted ranking/outcome rows from an explicit database/input source, rejects overlapping or reversed calibration/evaluation windows, emits all required 5/20/60-day/decile/ablation/turnover/legacy sections, and writes a caller-selected JSON report path without changing production model configuration.

- [ ] **Step 7: Implement validation command**

  Require explicit calibration/evaluation dates and output path. The command is offline/read-only, and the report records input query bounds, model version/config hash, cohort/run IDs, and sample sizes.

- [ ] **Step 8: Run GREEN replay/evaluation tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking/test_evaluation.py tests/trading/test_historical_replay.py tests/trading/test_outcome_evaluator.py tests/test_run_trading_universe_ranking_validation.py -q`

## Task 8: Standalone Smoke And Operations Documentation

**Files:**

- Create `scripts/run_trading_universe_ranking_smoke.py`
- Create `tests/test_run_trading_universe_ranking_smoke.py`
- Create `.env.example`
- Modify `src/core/config.py`
- Modify `tests/test_config.py`
- Modify `documents/repo_overview.md`

- [ ] **Step 1: Write failing smoke contract tests**

  Assert explicit tickers are required, default mode performs no database writes and invokes no news/fundamental/options/LLM services, one batch market-data path is used, output includes raw/normalized metrics, score, confidence, missing inputs, order, and `--persist` is the only write path.

- [ ] **Step 2: Run RED smoke tests**

  Run: `source ~/.venv/bin/activate && pytest tests/test_run_trading_universe_ranking_smoke.py -q`

- [ ] **Step 3: Implement smoke CLI and documentation**

  Include request throttling, JSON output, a fake-injectable `run_smoke()` function, and explicit failure output for missing SPY/credentials/data.

- [ ] **Step 4: Add configuration RED/GREEN tests**

  Assert defaults Top-N `100`, cohort minimum `10`, confidence floor `0.60`, positive ranges, confidence within `[0,1]`, and that the exact effective settings serialize into `config_json` for score reproduction.

- [ ] **Step 5: Document configuration and storage verification**

  Document that no new storage service/volume is introduced, existing Postgres remains the system of record, deployment must keep the explicit disk-mounted Postgres volume, and operators verify `SHOW data_directory;` is not tmpfs/in-memory.

- [ ] **Step 6: Run GREEN smoke/config tests and update tracker**

  Run: `source ~/.venv/bin/activate && pytest tests/test_run_trading_universe_ranking_smoke.py tests/test_config.py -q`

## Task 9: Full Verification And Completion Documentation

**Files:**

- Modify `plan/implementation/pr_60_cross_sectional_relative_strength_ranking.md`
- Modify `plan/progress_tracker.md`

- [ ] **Step 1: Run focused ranking suite**

  Run: `source ~/.venv/bin/activate && pytest tests/trading/ranking tests/test_run_trading_universe_ranking_smoke.py tests/test_run_trading_universe_ranking_validation.py tests/test_config.py tests/trading/test_runtime_live.py tests/trading/test_pipeline.py tests/trading/test_strategy_matching.py tests/trading/test_historical_replay.py tests/trading/test_outcome_evaluator.py tests/db/test_trading_models.py tests/db/test_cross_sectional_ranking_migration.py -q`

- [ ] **Step 2: Run compile/import/schema checks**

  Run: `source ~/.venv/bin/activate && python -m compileall -q src scripts/run_trading_universe_ranking_smoke.py scripts/run_trading_universe_ranking_validation.py`

  Run: `source ~/.venv/bin/activate && python -c "from sqlalchemy.orm import configure_mappers; import src.db.models; configure_mappers(); print('mappers ok')"`

  Run: `source ~/.venv/bin/activate && alembic current`

- [ ] **Step 3: Run full unit suite against accepted baseline**

  Run: `source ~/.venv/bin/activate && pytest -q`

  Expected: no new failures beyond the accepted 12-failure baseline; document exact totals.

- [ ] **Step 4: Run offline walk-forward validation artifact**

  Run `scripts/run_trading_universe_ranking_validation.py` with explicit non-overlapping calibration/evaluation windows and an output under a durable operator-selected data/report directory (not `/tmp`); verify the report contains decile alpha, monotonicity, turnover/stability, penalty ablations, drawdown/volatility, and offline legacy comparison. If persisted historical cohorts are not yet available, record this as a production-cutover blocker rather than fabricating evidence.

- [ ] **Step 5: Run static diff checks**

  Run: `git diff --check`

  Run: `git status --short`

- [ ] **Step 6: Update tracker and repository overview**

  Mark every completed task, add exact RED/GREEN/full-suite evidence, list any environment-blocked DB/live smoke checks, and record the new architectural boundary in `documents/repo_overview.md` because this is a major pipeline refactor.

- [ ] **Step 7: Request code review and address findings**

  Use `superpowers:requesting-code-review`, verify every accepted change locally, then use `superpowers:finishing-a-development-branch` to present integration options without merging automatically.
