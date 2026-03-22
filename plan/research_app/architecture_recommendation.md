# Research App Agent Architecture Recommendation

## Date
- 2026-03-22

## Decision
- Use a hybrid architecture for the research app MVP.
- Keep custom Python orchestration as the source of truth for run lifecycle, data collection, persistence, and evaluation.
- Use `Phidata` only as a thin single-turn LLM adapter inside `ResearchAgent`.
- Do not use `Phidata` tool-calling in the MVP production path.

## Boundary

### What stays in custom orchestration
- Load active watchlist tickers and control batch execution order.
- Create `research_runs` rows, manage `queued` / `running` / `succeeded` / `failed`, and write timestamps and error messages.
- Build the replayable `input_json` snapshot before the LLM call by fetching market data, news, and any DB-backed context in normal Python code.
- Own DB session lifecycle, repository helpers, and transaction boundaries.
- Validate structured outputs and persist `research_outputs`.
- Keep batch failure isolation so one ticker failure does not stop the rest of the run.
- Run `eval_runs.py`, compute realized returns and labels, and persist `eval_results`.
- Own scheduler integration, admin/manual triggers, config loading, retry policy, logging, and deployment wiring.

### What Phidata should own
- Instantiate the configured chat model for one research run.
- Submit the fully assembled prompt for one ticker/run.
- Return the raw model response to application code.
- Remain swappable behind the `ResearchAgent` runner boundary so we can replace it with a direct API client later if needed.

### What Phidata should not own in MVP
- Tool selection and tool execution during the research run.
- Direct database access or session management.
- Batch orchestration across multiple tickers.
- Run status persistence or retry semantics.
- Evaluation logic, replayability, or audit-trail construction.
- Cross-run memory or long-lived conversation state.

## Why this boundary fits the MVP
- The MVP requires a replayable `input_json`, which is easier to guarantee when all external data is fetched before the model call.
- The current product scope is single-user, serial, and deterministic enough that autonomous tool-calling adds more failure modes than product value.
- DB-backed tools in this repo depend on per-run context such as SQLAlchemy sessions, which is cleaner to manage in application code than through model-driven tool loops.
- The evaluation pipeline depends on stable stored inputs and outputs, not on hidden intermediate tool-call traces.
- This keeps the agent layer replaceable while still letting us use `Phidata` where it is genuinely convenient.

## Future upgrade path
- Keep the MVP boundary above until the system needs dynamic tool selection or multi-skill routing.
- If future work requires model-driven tool-calling, add:
  - persisted tool-call logs per run,
  - deterministic replay rules,
  - explicit timeout / retry / idempotency policy for tool execution,
  - tests for malformed tool arguments and partial tool failures.
- At that point, `Phidata` can expand from "LLM adapter" to "per-run tool-calling runtime" for selected workflows, while batch orchestration and persistence should still stay in project code.
