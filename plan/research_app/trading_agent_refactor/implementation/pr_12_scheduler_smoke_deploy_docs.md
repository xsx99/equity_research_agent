# Implementation Module PR 12: Scheduler, Smoke Tests, and Deploy Docs

## PR 12: Scheduler, Smoke Tests, Deploy Docs

**Goal:** Wire the daily workflow into scheduler and operational docs.

**Files:**
- Create: `src/scheduler/jobs/trading_preopen_job.py`
- Create: `src/scheduler/jobs/manual_ticker_review_job.py`
- Create: `src/scheduler/jobs/intraday_signal_refresh_job.py`
- Create: `src/scheduler/jobs/trading_reflection_job.py`
- Create: `src/scheduler/jobs/strategy_evolution_job.py`
- Modify: `src/scheduler/service.py` or `scripts/run_scheduler_service.py`
- Create: `scripts/run_trading_once.py`
- Create: `scripts/run_trading_smoke_test.py`
- Modify: `documents/research_app/runbook.md`
- Modify: `documents/research_app/deploy.md`
- Modify: `documents/repo_overview.md`
- Test: `tests/test_scheduler_jobs.py`
- Test: `tests/scripts/test_run_trading_smoke_test.py`

Implementation notes:

- Keep schedule in `America/New_York`.
- Add standalone smoke modes for provider guardrail fixture mode, universe/signal DB writes, historical replay fixture run, and paper-trade dry run.
- Add standalone smoke mode for active universe filter loading plus a fixture-backed manual ticker request in `review_only` mode that remains active until dismissed.
- Add standalone smoke mode for paper option decisions, option legs, option-risk snapshots, and assignment-risk snapshots using fixture data.
- Add standalone smoke mode for hourly intraday signal/news refresh using a fixed tiny ticker set or fixture mode.
- Add standalone smoke mode for strategy proposal creation from a fixed reflection fixture.
- Keep live provider/API smoke tests opt-in with tiny ticker sets and request budgets; ordinary CI should use fake providers and recorded cassettes only.
- Document Postgres persistent disk verification with `SHOW data_directory;`.
- Keep Docker Compose infrastructure.

Stop after PR 12 for review/merge.
