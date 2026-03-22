---
name: project_architecture
description: Refactored architecture for insider_trading_tracker — packages, abstractions, and key design decisions
type: project
---

The codebase was refactored into these top-level packages under `src/`:

- **collectors/** — `BaseCollector` ABC + `CollectionResult` dataclass. `SECEdgarCollector` extends `BaseCollector`, implements `collect(target_date) -> CollectionResult`. Helper modules (feed, fetcher, parser, storage) live in `collectors/sec_edgar/`.
- **tools/** — `ToolContext` (holds `session`, `config`), `BaseTool` ABC, `ToolRegistry`. Concrete tools: `MarketDataTool`, `NewsDataTool`, and 6 insider query tools in `insider_queries.py`. `build_research_tool_registry()` factory in `__init__.py`.
- **prompts/** — `Prompt` (frozen dataclass with `id`, `version`, `template`), `PromptRegistry` (singleton via `get_default()`). Templates in `prompts/templates/*.txt` named `{id}_{version}.txt`. Current template: `research_v1.txt`.
- **agents/** — `BaseAgent` ABC (holds `tool_registry`, `prompt_registry`, `model_name`), `AgentResult` dataclass. `ResearchAgent` extends `BaseAgent`, uses Phidata/OpenAI runner, validates with `StructuredResearchOutput` Pydantic model.
- **scheduler/** — `BaseJob` ABC with `config -> JobConfig` + `run()`. `SchedulerService(jobs=[...]).start()` wraps APScheduler. `SECEdgarJob` lives in `scheduler/jobs/`.
- **db/**, **config.py**, **logging.py** — unchanged.

**Old files kept for backward compat:** `src/collector/` (old location), `src/tools/queries.py`, `src/research/` (providers still imported by tool wrappers).
**Entry point:** `scripts/run_scheduler_service.py` → `SchedulerService(jobs=[SECEdgarJob()]).start()`

**Why:** ToolContext injected into `run()` not constructor (tool lifetime ≠ session lifetime). Tools registered explicitly (not auto-discovered). PromptRegistry uses singleton + lazy file load.
