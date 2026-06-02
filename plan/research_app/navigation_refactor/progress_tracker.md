# Navigation Refactor Progress Tracker

## 2026-06-01

- Created design doc and implementation plan for a one-PR behavior-preserving navigation refactor.
- Scope: move provider implementations out of `src/tools`, move workflow orchestration into `workflows`, signal code into `signals`, strategy code into `strategies`, in-memory persistence into `repositories`, and delete old root-level compatibility files because this version has not been released.
- Added RED navigation import tests for the new provider, trading workflow/repository, and research workflow/repository paths. Initial run failed with missing-package import errors as expected:
  - `source ~/.venv/bin/activate && pytest tests/providers/test_navigation_imports.py tests/trading/test_navigation_imports.py tests/research/test_navigation_imports.py -q`
- Moved market/news/global-context provider implementations under `src/providers/` and kept agent-callable wrappers in `src/tools/`.
- Split trading workflow entrypoints into `src/trading/workflows/` and moved the in-memory trading artifact store to `src/trading/repositories/in_memory.py`.
- Completed the intended trading layout by moving signal modules into `src/trading/signals/` and strategy modules into `src/trading/strategies/`.
- Moved legacy research batch/evaluation workflows to `src/research/workflows/` and DB helpers to `src/research/repositories/research_repository.py`.
- Deleted old root-level compatibility files after confirming internal imports use the new paths:
  - trading files such as `src/trading/pipeline.py`, `src/trading/source_ingestion.py`, `src/trading/strategy_matching.py`, and `src/trading/trade_classifier.py`
  - research files `src/research/pipeline.py`, `src/research/eval_pipeline.py`, and `src/research/repository.py`
- Added tests that assert those old compatibility files do not exist.
- Completed the remaining trading module-contract navigation cleanup:
  - moved universe and provider resilience contracts into `src/trading/data_sources/`
  - moved manual ticker request state into `src/trading/manual_review/`
  - moved portfolio-intent helpers into `src/trading/portfolio/`
  - moved source-backed relationship graph helpers into `src/trading/relationships/`
  - moved historical replay and outcome evaluation into `src/trading/replay/`
  - deleted the corresponding old root files because this version has not been released
- Targeted verification passed:
  - `source ~/.venv/bin/activate && pytest tests/providers/test_navigation_imports.py tests/tools/test_market_data.py tests/tools/test_news_data.py tests/tools/test_global_context.py tests/tools/test_fred_provider.py tests/tools/test_tool_registry.py -q` passed with 42 tests.
  - `source ~/.venv/bin/activate && pytest tests/trading/test_navigation_imports.py tests/trading tests/test_run_trading_source_ingestion_smoke.py -q` passed with 51 tests.
  - After completing `signals/` and `strategies/`, `source ~/.venv/bin/activate && pytest tests/trading tests/test_run_trading_source_ingestion_smoke.py -q` passed with 53 tests.
  - After deleting old root compatibility files and fixing `src/trading/__init__.py`, `source ~/.venv/bin/activate && pytest tests/trading tests/test_run_trading_source_ingestion_smoke.py -q` passed with 54 tests.
  - After completing the remaining module-contract package moves, `source ~/.venv/bin/activate && pytest tests/trading tests/test_run_trading_source_ingestion_smoke.py -q` passed with 55 tests.
  - `source ~/.venv/bin/activate && pytest tests/research/test_navigation_imports.py tests/research tests/test_app.py tests/test_run_research_once.py tests/test_scheduler_jobs.py -q` passed with 97 tests.
- Full verification passed:
  - `source ~/.venv/bin/activate && pytest -q` passed with 308 tests after deleting old compatibility files and completing the remaining module-contract package moves.
  - `git diff --check` passed.
