# Repository Overview

This repository contains the research app and the staged V2 trading-agent refactor.

## Current Architecture

- `src/agents/` contains bounded agent code. Existing research behavior still uses `src/prompts/registry.py`; PR 1a adds `src/agents/prompt_registry.py` for trading-agent prompt metadata, template hashes, and rendered prompt hashes.
- `src/db/models/` contains SQLAlchemy ORM models using the shared `Base` and `ChoiceEnum` helpers. PR 1a adds trading foundation models for strategy definitions, LLM prompt templates, prompt runs, and usage telemetry.
- `src/trading/` contains data-only trading foundation helpers. PR 1a seeds the initial strategy catalog and portfolio-pool trade identity taxonomy without changing runtime trading behavior.
- `alembic/versions/` contains database migrations. PR 1a adds revision `005` for `strategy_definitions`, `llm_prompt_templates`, `llm_prompt_runs`, and `llm_usage_events`.
- `plan/research_app/trading_agent_refactor/` is the canonical modular plan for the V2 trading-agent work. Implementation proceeds one PR slice at a time and stops for review before the next slice.

## PR 1a Scope

PR 1a is a minimal durable foundation only:

- versioned strategy definition seed data
- trade identity taxonomy policies
- prompt registry metadata and deterministic rendering
- ORM models and Alembic schema for strategy/prompt telemetry

It intentionally does not add universe scanning, signal snapshots, strategy scoring runs, portfolio intents, relationship graph tables, scheduler jobs, paper trading, options execution, or UI changes.
