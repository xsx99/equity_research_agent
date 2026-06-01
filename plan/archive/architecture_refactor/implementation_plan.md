---
name: project_architecture
description: Refactored architecture for insider_trading_tracker — packages, abstractions, and key design decisions
type: project
---

The codebase is currently organised into these top-level packages under `src/`:

- **collectors/** — `BaseCollector` ABC + `CollectionResult` dataclass. `SECEdgarCollector` extends `BaseCollector`, implements `collect(target_date) -> CollectionResult`, and delegates SEC-specific feed/fetch/parse/storage helpers to `collectors/sec_edgar/`.
- **tools/** — `ToolContext` (optional `session`, runtime `config`), `BaseTool` ABC, and `ToolRegistry`. `build_research_tool_registry()` explicitly registers 8 tools: market snapshot, recent news, and 6 insider-trade query tools.
- **prompts/** — `Prompt` (frozen dataclass with `id`, `version`, `template`, `description`) plus `PromptRegistry`. Prompt definitions are YAML files in `src/prompts/templates/`, loaded lazily and cached on first access.
- **agents/** — `BaseAgent` + `AgentResult`, with `ResearchAgent` providing structured research generation. The default runner uses Phidata, and the default model name is `RESEARCH_MODEL_NAME` or `gemini-2.5-flash-lite`.
- **db/** — `connection.py` owns engine/session/Alembic bootstrap. Models are split across `models/base.py`, `insider_trades.py`, `watch_list.py`, `research.py`, and `evaluation.py`; the research app tables are backed by Alembic revision `004_research_app_tables.py`.
- **scheduler/** — `BaseJob`, `JobConfig`, and `SchedulerService` wrap APScheduler. `scheduler/jobs/` currently contains only `SECEdgarJob`.
- **core/** — `src/core/config.py` and `src/core/logging.py` replace the old flat `config.py` / `logging.py` layout.

**Compatibility status:** There are no legacy compatibility packages in the current tree; `src/collector/`, `src/tools/queries.py`, and `src/research/` do not exist.
**Runtime entrypoint:** `scripts/run_scheduler_service.py` is the checked-in bootstrap script and is intended to initialise migrations, then start `SchedulerService(jobs=[SECEdgarJob()])`.
**Runtime scope today:** The SEC collector is fully wired into the scheduler. Research DB models, prompt loading, tool scaffolding, and `ResearchAgent` exist, but there is still no research pipeline module, evaluation runner, web UI, or research/eval scheduled jobs.

**Why:** Tool context is injected per invocation instead of at construction time, tool registration is explicit rather than auto-discovered, and prompt loading stays lazy and file-backed.
