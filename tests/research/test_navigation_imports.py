"""Navigation tests for research import paths."""
from __future__ import annotations


def test_research_workflow_paths_export_legacy_entrypoints():
    from src.research.workflows.batch_research import ResearchPipeline
    from src.research.workflows.evaluation import EvalPipeline

    assert ResearchPipeline.__name__ == "ResearchPipeline"
    assert EvalPipeline.__name__ == "EvalPipeline"


def test_research_repository_path_describes_storage_scope():
    from src.research.repositories import research_repository

    assert callable(research_repository.get_active_tickers)

