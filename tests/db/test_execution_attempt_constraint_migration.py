from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_execution_attempt_reason_constraint_has_forward_fix_migration():
    result = subprocess.run(
        ["alembic", "upgrade", "029:head", "--sql"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    sql = result.stdout

    assert "ck_execution_attempts_reason_code" in sql
    assert "no_action_required" in sql
    assert "DROP CONSTRAINT" in sql.upper()
