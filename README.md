# Equity Research Agent

This repository is an LLM-based research system built around one idea: combine raw equity signals with market context, generate a structured thesis, and score that thesis quickly enough to learn from it. The current implementation includes a scheduled SEC Form 4 collector, a research pipeline that builds replayable model inputs, a same-day evaluation loop, a small FastAPI UI, and Raspberry Pi-oriented Docker deployment.


## What This Repo Demonstrates

- Backend architecture split into focused packages: `collectors`, `tools`, `agents`, `research`, `db`, `web`, and `scheduler`.
- Pragmatic AI integration: the LLM is used for structured reasoning, while Python owns data fetching, state transitions, error handling, and persistence.
- Replayable pipeline design: each research run stores the full input snapshot so runs can be inspected and evaluated later without reconstructing context.
- Operational realism: Docker Compose deployment, scheduler jobs, explicit persistent-disk requirements for Postgres, and dedicated runbook/deploy docs.
- Testing discipline: unit coverage across collectors, tools, pipelines, scheduler behavior, and web routes, plus standalone smoke scripts for external dependencies.
- Incremental product thinking: the repo contains both implemented functionality and explicit future work, instead of pretending the MVP is more complete than it is.

## System Overview

At a high level, the system has four moving parts:

1. SEC ingestion
   Pulls SEC EDGAR Form 4 filings, parses insider transactions, and upserts them into Postgres.
2. Research generation
   Builds a research input per ticker from technical signals, filtered news, insider activity, and global context, then calls the research agent once per ticker.
3. Same-day evaluation
   Scores completed runs against actual price movement using explicit same-day evaluation rules.
4. Operator-facing UI and scheduling
   Exposes watchlist/research pages in FastAPI and runs scheduled SEC, research, and eval jobs with scheduler.

Simplified flow:

```text
SEC EDGAR -> insider_trades
                    |
watchlist -> ResearchPipeline -> ResearchAgent -> research_runs + research_outputs
                    |                                        |
      technical/news/global context tools                       v
                                                     EvalPipeline -> eval_results
                                                                     |
                                                                  FastAPI UI
```

## Key Engineering Decisions

### 1. Thin LLM layer, deterministic Python orchestration

The repo intentionally does not rely on model-driven tool calling for the core workflow. `ResearchPipeline` gathers data, constructs `input_json`, manages run state, and persists outputs before and after a single model call. This keeps failure modes visible, makes testing easier, and preserves replayability.

### 2. Replayable research inputs

Each run stores a full structured input snapshot in `research_runs.input_json`. That means the thesis can be reviewed against the actual context the model saw, instead of depending on mutable external APIs after the fact.

### 3. Explicit evaluation semantics

The evaluation loop distinguishes between:

- pre-open runs, scored with `open_to_close`
- post-open manual runs, scored with `run_time_price_to_close`

That separation avoids look-ahead bias and makes the scoring logic inspectable rather than hand-wavy.

### 4. Provider abstraction at the tool layer

Technical signals, news, global context, and insider-query logic live behind tool/provider boundaries. That keeps the research pipeline focused on orchestration instead of vendor-specific code.

## How The System Works

### SEC collector

- `SECEdgarCollector` fetches Form 4 filings for a target date.
- Filing XML is parsed into normalized insider transactions.
- Transactions are upserted into Postgres so downstream research can summarize recent insider activity per ticker.

### Research pipeline

- Loads active watchlist tickers from Postgres.
- Fetches one batch-level `global_context` snapshot.
- Fetches per-ticker market data, filtered news, and insider activity summary.
- Persists a queued/running/succeeded/failed research run lifecycle.
- Calls `ResearchAgent` once per ticker and stores structured output.

### Evaluation pipeline

- Finds same-day successful runs eligible for evaluation.
- Computes realized ticker return and benchmark return.
- Applies the current `rule_v1` label matrix.
- Upserts `eval_results` for later review in the UI.

## Repo Map

- [`src/collectors/`](src/collectors) SEC ingestion, parsing, and storage logic
- [`src/tools/`](src/tools) market/news/global-context providers and insider query tools
- [`src/agents/`](src/agents) research agent and output schemas
- [`src/research/`](src/research) orchestration for research runs and eval runs
- [`src/db/`](src/db) SQLAlchemy models, sessions, and migrations bootstrap
- [`src/web/`](src/web) FastAPI app factory, routers, filters, and templates
- [`src/scheduler/`](src/scheduler) APScheduler service and job definitions
- [`scripts/`](scripts) one-off entrypoints and smoke tests
- [`documents/`](documents) deployment/runbook/general operational notes
- [`plan/`](plan) design docs, architecture notes, and progress tracking
- [`tests/`](tests) unit and integration-style test coverage

## Current Status

Implemented today:

- SEC Form 4 collection and database upsert flow
- research pipelines with structured output persistence
- same-day evaluation pipeline
- FastAPI watchlist/research UI
- APScheduler jobs for SEC, research, and eval
- Docker-based deployment path for Raspberry Pi
- unit tests and live smoke-test scripts

Still intentionally incomplete:

- richer frontend UX
- broader event/context sources such as economic calendar data
- deeper post-run critique / learning loops
- social/alternative data ingestion
- more sophisticated evaluation beyond the current MVP rule set
