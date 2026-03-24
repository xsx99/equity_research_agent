# Research App MVP Implementation Plan

## Summary
- This plan is aligned to the current repository state on 2026-03-22, with `plan/research_app/design_doc.md` as the product/design reference.
- The repo already contains all of PR1 and most of PR2: research ORM models, Alembic migration `004`, YAML prompt loading, market/news tools, `ResearchAgent`, and related dependencies/tests.
- The runtime is still SEC-only. There is no research orchestration module, eval runner, FastAPI app, or research/eval scheduler job in the current tree.
- Architecture choice for MVP: keep custom orchestration as the source of truth for batch execution, data fetching, persistence, and eval; keep `Phidata` as a thin single-turn LLM adapter inside `ResearchAgent`, not as the main tool-calling runtime.

## Status Snapshot
- Done: PR1 – Schema & ORM Foundation
- Done: PR2 – Data Sources & LLM Skeleton
- Done: PR3 – Research Pipeline Implementation
- Done: PR4 – Evaluation Pipeline
- Planned: PR5 – Web UI (Server-Rendered FastAPI)
- Planned: PR6 – Scheduler & Ops/Deploy

## Architecture Decision
- `run_research.py` should assemble the full replayable `input_json` in normal Python code before calling the model. That includes market snapshot, news, and any DB-backed research context.
- `ResearchAgent` should stay responsible for prompt rendering, one model invocation, JSON coercion, and schema validation.
- The `ToolRegistry` remains application-side plumbing for deterministic data access and testing. In the MVP production path, those tools are not passed into `phi.agent.Agent` for model-driven execution.
- Batch lifecycle, DB session ownership, status transitions, persistence, scheduler integration, and eval logic stay outside `Phidata`.
- If future work requires dynamic tool-calling, add explicit tool-call persistence and replay rules before moving that responsibility into `Phidata`.

## PR1 – Schema & ORM Foundation
- Implemented in `src/db/models/watch_list.py`, `src/db/models/research.py`, and `src/db/models/evaluation.py`, with exports in `src/db/models/__init__.py` and `src/db/__init__.py`. Existing `InsiderTrade` remains in place.
- Alembic revision `alembic/versions/004_research_app_tables.py` creates `watchlists`, `research_runs`, `research_outputs`, and `eval_results` with the expected constraints, defaults, indexes, and foreign keys.
- Enum helpers exist via `ChoiceEnum.choices()`, and `ResearchTimeHorizon.days_mapping()` exposes the horizon-to-days mapping needed by future eval logic.
- Current gap: there are no migration smoke tests or temp-Postgres model round-trip tests under `tests/` yet.

## PR2 – Data Sources & LLM Skeleton
- `src/tools/market_data.py` is implemented with Alpaca daily bars plus optional Finnhub sector / earnings enrichment. It returns `last_price`, `return_1d`, `return_5d`, `sector`, and `earnings_in_days`.
- `src/tools/news_data.py` is implemented with provider fallback in this order: Finnhub -> Marketaux -> Alpaca. It returns up to 5 `{title, summary}` items.
- The prompt now lives at `src/prompts/templates/research_v1.yaml`. `src/prompts/registry.py` lazily loads YAML definitions into `Prompt` objects with `id`, `version`, `template`, and `description`.
- `src/agents/research.py` is implemented. The default runner uses `Phidata` as a thin provider-aware model wrapper; `gemini*` model IDs use the Gemini-backed path and other model IDs fall back to `OpenAIChat`. It does not currently expose the repo `ToolRegistry` into `phi.agent.Agent` for model-driven tool-calling. The default model name is `RESEARCH_MODEL_NAME` or `gemini-2.5-flash-lite`, and Google auth is sourced from `GOOGLE_API_KEY`.
- `requirements.txt` includes `httpx`, `pydantic`, `PyYAML`, `phidata`, `openai`, `google-generativeai`, `alpaca-py`, and `finnhub-python`. Marketaux is used through direct HTTP calls instead of a separate SDK dependency.
- Current test coverage includes prompt loading/rendering, JSON coercion, Pydantic schema validation, `ToolRegistry`, and insider query tools. Added smoke tests for `market_data.py`, `news_data.py` and `insider_queries.py`.

## PR3 – Research Pipeline Implementation
- Not started. There is no `src/research/` package or `run_research.py` stub in the repo today, so this PR needs to create the orchestration layer from scratch.
- Build the pipeline to load active `Watchlist` rows, create/update `ResearchRun` status timestamps, fetch market/news/DB inputs in Python, persist the replayable `input_json`, call `ResearchAgent`, validate outputs, and persist `ResearchOutput`.
- A direct agent smoke entrypoint now exists at `scripts/run_research_agent_once.py`; the full batch research pipeline CLI (`run_research.py` / `scripts/run_research_once.py`) still does not exist today.
- Add repository/helpers for watchlist CRUD and run persistence to keep orchestration code out of route handlers / scripts.
- Tests still needed: pipeline happy path with mocked providers/LLM plus failure-state transitions that end in `failed` + `error_message` without breaking the batch.

## PR4 – Evaluation Pipeline
- Not started. There is no `eval_runs.py` or evaluation service module in the current tree.
- Implement selection of succeeded runs whose `time_horizon` window has elapsed, then compute `realized_return` / `benchmark_return` and persist `EvalResult`.
- Define `rule_v1` outcome:
  - bullish → correct if realized_return > 0 and ≥ benchmark_return; wrong_direction if realized_return < 0; partially_correct otherwise.
  - bearish → correct if realized_return < 0 and ≤ benchmark_return; wrong_direction if realized_return > 0; partially_correct otherwise.
  - neutral/abstain → uninformative unless move exceeds ±X% (config, default 1%) then wrong_direction.
- Reuse `ResearchTimeHorizon.days_mapping()` for horizon conversion and persist `eval_results`; mark runs needing manual review when `time_horizon` is missing or invalid.
- Tests still needed: horizon eligibility logic, the `rule_v1` label matrix, and idempotent writes.

## PR5 – Web UI (Server-Rendered FastAPI)
- Not started. There is no `src/app.py`, `templates/`, or `static/` directory in the current repo.
- Planned routes remain `GET/POST /watchlist`, `GET /research`, `GET /research/{run_id}`, and internal `POST /admin/run-now` / `POST /admin/eval-now`.
- Reuse the existing DB session helpers and the repository layer introduced in PR3; keep it server-rendered HTML rather than a SPA.
- Tests still needed: FastAPI `TestClient` coverage for watchlist CRUD, list/detail pages, and admin triggers.

## PR6 – Scheduler & Ops/Deploy
- `src/core/config.py` currently contains only database, SEC EDGAR, and scheduler settings. Research/eval env vars, prompt defaults, and API-key documentation still need to be added there.
- `src/scheduler/` currently registers only `SECEdgarJob`; there are no research/eval job classes or job registration hooks yet.
- Docker Compose / deploy docs for the research app are not in the repository yet. When added, Postgres must remain on a persistent disk-backed path such as `/data/postgres_data:/var/lib/postgresql/data`.
- `documents/research_app_deploy.md` and `documents/research_app_runbook.md` now cover env-based key management and manual agent triggering. Postgres `SHOW data_directory;` verification and Raspberry Pi-specific persistence checks still need to be expanded there.
- Tests still needed: research/eval scheduler registration smoke plus any deploy-config linting that gets introduced.

## Parallelization Guide
- PR1 is done and PR2 is mostly done, so the next blocking work is PR3.
- PR4 can be built in parallel once PR3 is writing stable `research_runs` / `research_outputs`.
- PR5 should wait until PR3 defines repository helpers and run/output persistence shapes.
- PR6 should land last, after the research pipeline, eval pipeline, and web entrypoints are concrete enough to schedule and deploy.

## Test Plan (aggregate)
- Existing automated coverage: collector/parser helpers, prompt registry + schema validation, `ToolRegistry`, and insider query tools.
- Missing automated coverage: migration smoke tests, market/news provider tests, research pipeline state transitions, evaluation rule matrix, FastAPI routes, and research/eval scheduler registration.
- Future manual smoke once PR3/PR4 land: run `scripts/run_research_once.py` and `scripts/run_eval_once.py`, verify rows are written to `research_runs` / `research_outputs` / `eval_results`, then confirm Postgres `SHOW data_directory;` points to a disk-backed path.

## Assumptions
- `RESEARCH_MODEL_NAME` defaults to `gemini-2.5-flash-lite` when unset in the current code path.
- Alpaca credentials are required for market bars and optional Alpaca news fallback. Finnhub and Marketaux API keys are optional enhancements.
- Network egress for the external market/news providers is allowed.
- Single-user, single-tenant app; no auth required per design doc.
- Running on same Postgres instance as existing insider data; coexistence is acceptable.
