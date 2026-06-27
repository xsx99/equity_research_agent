# Trading Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V2 relative-strength catalyst trading workflow in reviewable PR slices, starting with a verifiable MVP of universe -> point-in-time signal snapshots -> strategy scoring -> historical replay/outcome evaluation before adding paper trading, options, intraday refresh, reflection, learning adaptation, strategy evolution, and UI.

**Architecture:** Keep Python orchestration as the source of truth. LLM calls are bounded, Pydantic-validated, retried on schema failure, and downgraded to safe fallbacks when validation still fails. Each pipeline persists point-in-time snapshots with `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at` so candidate selection, trade identity, confidence calibration, replay outcomes, risk decisions, paper stock/options orders, worst-case assignment exposure, portfolio state, prompt versions, LLM calls, reflection, and learning factors can be audited without lookahead.

**Tech Stack:** Python, SQLAlchemy, Alembic, Postgres JSONB, FastAPI/Jinja, APScheduler, pytest, existing market/news/global-context providers.

---

## Reading Discipline

The original 14-PR plan is built. Work now arrives as additional `pr_XX_*.md` / dated `*-design.md` slices. Read the **smallest** context for the slice in front of you — do not load every design and implementation module by default.

**Startup reading (every implementation session):**

1. `documents/general_instructions.md`
2. [Module Contracts](../module_contracts.md) — the durable interface contracts; check these before changing any producer/consumer.
3. This README.
4. The current slice's module file under `plan/implementation/`.

Then, **on demand** (not a full read): skim the **Recent** section of the [progress tracker](../progress_tracker.md) for the latest status and any design decision that superseded the module text. Older history is summarized there; full detail is archived under `plan/archive/`.

Then read only the design modules relevant to the slice (see key below).

**Read more only when:**

- The slice changes a producer/consumer listed in [Module Contracts](../module_contracts.md).
- A test or implementation touches an upstream table/service/schema not covered by the modules already read.
- The tracker says a design decision superseded the module text.
- Existing code diverges from the plan in a way that affects the current contract.

**Do not** load all design modules or all PR modules at session start. The directory is the source of truth — there is no hand-maintained PR index to keep in sync.

## Design Modules

Foundational architecture (`plan/design/`):

| ID | Module |
| --- | --- |
| D01 | [Context, Goals, and Approach](../design/01_context_goals_approach.md) |
| D02 | [Target Architecture](../design/02_target_architecture.md) |
| D03 | [Strategy Architecture](../design/03_strategy_architecture.md) |
| D04 | [Signal Snapshots and Point-in-Time Data](../design/04_signal_snapshots.md) |
| D05 | [Workflows and Decision Contracts](../design/05_workflows_and_decision_contracts.md) |
| D06 | [Paper Trading and Risk](../design/06_paper_trading_and_risk.md) |
| D07 | [Replay, Reflection, and Learning](../design/07_replay_reflection_learning.md) |
| D08 | [Data Model](../design/08_data_model.md) |
| D09 | [UI, Error Handling, Testing, and Delivery](../design/09_ui_error_testing_delivery.md) |

Follow-up slices live alongside these as `design/10_…`–`14_…` (live wiring, `/today` UI passes) and dated `design/YYYY-MM-DD-*.md` files (option execution, risk/macro contracts, manual-review audit, signal expansion, etc.). Read a follow-up doc only when the current slice touches its area; pick by filename.

## Execution Rules

- Each PR slice stops after verification. Do not begin the next slice until the user has reviewed and merged.
- Use TDD for implementation code: write failing tests, run targeted tests, implement, rerun targeted tests, then run the broader relevant suite.
- After every completed implementation slice, prepend a dated entry to the **Recent** section of `plan/progress_tracker.md`.
- For major refactor slices, update `documents/repo_overview.md`. If the file is absent, create it with the current architecture summary.
- For Python commands, run `source ~/.venv/bin/activate` first.
- Any DB/API smoke test must be standalone and rate-limit conscious.
- Unit tests must use fake providers. Integration tests that touch external-provider behavior should use recorded `vcrpy` cassettes or equivalent fixtures. Live provider smoke tests are opt-in and must not block ordinary CI.
- Deployment changes must preserve Docker Compose and persistent disk Postgres requirements.

## PR Modules

PR modules are **not** enumerated here — the list rots. The source of truth is the directory: `plan/implementation/` holds self-named `pr_XX_*.md` and dated `*-design.md` files, and the tracker's **Recent** section shows the latest slice and status.
