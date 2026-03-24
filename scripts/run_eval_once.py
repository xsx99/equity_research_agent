#!/usr/bin/env python3
"""Run the evaluation pipeline once — for all eligible runs or a single run.

Usage examples
--------------
# Evaluate all eligible runs:
python scripts/run_eval_once.py

# Force-evaluate a single run by UUID:
python scripts/run_eval_once.py --run-id <UUID>
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.logging import get_logger
from src.db.connection import get_session
from src.research.eval_pipeline import EvalPipeline, EvalPipelineResult

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Force-evaluate a single research run by UUID.",
    )
    args = parser.parse_args()

    with get_session() as session:
        pipeline = EvalPipeline(session=session)

        if args.run_id:
            try:
                run_id = uuid.UUID(args.run_id)
            except ValueError:
                print(f"Error: invalid UUID '{args.run_id}'", file=sys.stderr)
                return 1

            logger.info("run_eval_once_single_run", run_id=str(run_id))
            ticker_result = pipeline.run_single(run_id)
            pipeline_result = EvalPipelineResult(
                evaluated=1 if ticker_result.success else 0,
                failed=0 if ticker_result.success else 1,
                ticker_results=[ticker_result],
            )
        else:
            logger.info("run_eval_once_all_eligible")
            pipeline_result = pipeline.run_all()

    summary = {
        "evaluated": pipeline_result.evaluated,
        "failed": pipeline_result.failed,
        "skipped": pipeline_result.skipped,
        "runs": [
            {
                "run_id": str(r.run_id),
                "ticker": r.ticker,
                "success": r.success,
                "outcome_label": r.outcome_label,
                "error": r.error,
            }
            for r in pipeline_result.ticker_results
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0 if pipeline_result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
