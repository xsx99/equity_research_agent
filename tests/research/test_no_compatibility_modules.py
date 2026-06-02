"""Navigation tests for removed research compatibility modules."""
from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_research_root_no_longer_contains_compatibility_modules():
    removed_paths = [
        "src/research/eval_pipeline.py",
        "src/research/pipeline.py",
        "src/research/repository.py",
    ]

    assert [path for path in removed_paths if (_REPO_ROOT / path).exists()] == []
