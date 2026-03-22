# Research App MVP Implementation Plan

## Summary
- Implement the research app per `plan/research_app.md`, reusing existing logging, config, Alembic, and scheduler scaffolding.
- Deliver work as 6 PRs, each independently reviewable; only PR1 is a hard prerequisite for the rest. Parallelization guidance is noted per PR.

## PR1 – Schema & ORM Foundation
- Add SQLAlchemy models for `watchlists`, `research_runs`, `research_outputs`, `eval_results` into `src/db/models.py`, keeping existing `InsiderTrade`.
- Create Alembic revision `004_research_app_tables` matching the design doc (enums, defaults, indexes, FK constraints, created_at, status fields).
- Ensure models expose enum/choice helpers for reuse in UI/validation.
- Tests: migration upgrade/downgrade smoke; model round-trip using a temp Postgres.

## PR2 – Data Sources & LLM Skeleton
- Implement `src/research/tool/get_market_data.py` (Alpaca-based snapshot + returns; optional sector/earnings distance) and `src/research/tool/get_news_data.py` (Finnhub/Marketaux NewsAPI if key present else Alpaca/news fallback).
- Add prompt file `prompts/research_v1.txt`; implement `src/research/llm_client.py` using Phidata Agent + OpenAI model with structured output validation (Pydantic) and pluggable `prompt_version`/`model_name`.
- Extend `requirements.txt` with `Finnhub`, `Marketaux`, `Alpaca`, `phidata`, `pydantic`, `httpx` (if needed by phidata).
- Tests: unit tests with stubbed providers ensuring schema compliance and failure logging.

## PR3 – Research Pipeline Implementation
- Replace `src/research/run_research.py` stub with full pipeline: load active `watchlists`, create `research_runs` rows (status→running/succeeded/failed, timestamps), fetch market/news input snapshot, call LLM, validate structured output, write `research_outputs`.
- Add CLI/script entrypoint (e.g., `scripts/run_research_once.py`) supporting optional ticker override for manual triggers.
- Add lightweight repository/helpers for watchlist CRUD and run insertion/retrieval to avoid inline SQL.
- Tests: pipeline happy-path with mocked collectors/LLM; failure path sets `failed` and `error_message` without crashing the batch.

## PR4 – Evaluation Pipeline
- Implement `src/research/eval_runs.py`: select succeeded runs whose `time_horizon` window has elapsed; pull price/benchmark snapshots; compute `realized_return`, `benchmark_return`.
- Define `rule_v1` outcome:
  - bullish → correct if realized_return > 0 and ≥ benchmark_return; wrong_direction if realized_return < 0; partially_correct otherwise.
  - bearish → correct if realized_return < 0 and ≤ benchmark_return; wrong_direction if realized_return > 0; partially_correct otherwise.
  - neutral/abstain → uninformative unless move exceeds ±X% (config, default 1%) then wrong_direction.
- Persist `eval_results`; mark runs needing manual review when `time_horizon` missing.
- Tests: horizon eligibility logic; rule_v1 label matrix; ensures idempotent writes.

## PR5 – Web UI (Server-Rendered FastAPI)
- Build `src/app.py` FastAPI with Jinja templates in `templates/` and CSS in `static/style.css`.
- Routes: `GET/POST /watchlist` (add/delete/deactivate tickers), `GET /research` (table of recent runs + aggregate eval stats), `GET /research/{run_id}` (input/output JSON, eval result history), `POST /admin/run-now` and `POST /admin/eval-now` for manual triggers (internal use).
- Reuse DB session helpers and repository functions; keep responses minimal HTML (no SPA).
- Tests: FastAPI `TestClient` coverage for watchlist CRUD, list/detail pages, and admin triggers (with mocked pipelines).

## PR6 – Scheduler & Ops/Deploy
- Extend `src/config.py` with research/eval schedule env vars (`RESEARCH_SCHEDULE_HOUR/MINUTE`, `EVAL_*`, `RESEARCH_RUN_ON_STARTUP`, `EVAL_RUN_ON_STARTUP`, model/prompt defaults, API keys).
- Update `src/research/jobs.py` to stay, and modify `src/scheduler.py` to register both SEC and research/eval jobs; ensure job IDs/logging consistent.
- Add Docker Compose service for the web app; ensure Postgres volume remains `/data/postgres_data:/var/lib/postgresql/data` (hard disk path) and add env examples in `.env.sample`.
- Author `documents/research_app_deploy.md` and `documents/research_app_runbook.md` detailing cron usage, manual triggers, verifying Postgres `data_directory` is not tmpfs, and Raspberry Pi notes.
- Tests: scheduler registration smoke (unit) and docker-compose config lint (if available).

## Parallelization Guide
- Start PR1 first (schema). After PR1: PR2 (collectors/LLM) and PR4 (eval rule logic) can proceed in parallel; PR3 (pipeline) depends on PR1+PR2; PR5 (UI) depends on PR1 and benefits from PR3 stubs but can start layout earlier; PR6 should land after PR3–PR5 to wire real jobs and docs.

## Test Plan (aggregate)
- Unit: collectors/LLM schema validation, pipeline state transitions, evaluation rule matrix, FastAPI routes.
- Integration: Alembic migrations on fresh DB; end-to-end dry run with mocked providers writing runs/outputs/evals.
- Manual: run `scripts/run_research_once.py` and `scripts/run_eval_once.py` against dev DB; verify UI pages load; confirm Postgres `SHOW data_directory;` matches mounted disk.

## Assumptions
- Gemini API key: AIzaSyDmIeAH5u6BzlYpgNnqtmvbplZWuTUSZc
- Marketaux, Finnhub or Alpaca NewsAPI access are acceptable; network egress allowed.
- Alpaca for real time market data.
- Single-user, single-tenant app; no auth required per design doc.
- Running on same Postgres instance as existing insider data; coexistence is acceptable.
