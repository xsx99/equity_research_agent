#!/usr/bin/env python3
"""Run the research pipeline once — for all active watchlist tickers or a single ticker.

Usage examples
--------------
# Run for all active watchlist tickers:
python scripts/run_research_once.py

# Run for a single ticker only:
python scripts/run_research_once.py --ticker AAPL

# Override the model:
python scripts/run_research_once.py --model-name gemini-2.5-flash-lite
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.research import DEFAULT_MODEL_NAME, ResearchAgent
from src.core.logging import get_logger
from src.db.connection import get_session
from src.prompts.registry import PromptRegistry
from src.research.pipeline import PipelineResult, ResearchPipeline
from src.tools import build_research_tool_registry

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        default=None,
        help="Run only for this ticker instead of all active watchlist tickers.",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"LLM model name (default: {DEFAULT_MODEL_NAME}).",
    )
    parser.add_argument(
        "--refresh-global-context",
        action="store_true",
        help=(
            "For single-ticker runs, fetch a fresh macro/global context instead "
            "of reusing the latest same-day snapshot when one exists."
        ),
    )
    args = parser.parse_args()

    agent = ResearchAgent(
        tool_registry=build_research_tool_registry(),
        prompt_registry=PromptRegistry.get_default(),
        model_name=args.model_name,
    )

    with get_session() as session:
        pipeline = ResearchPipeline(session=session, agent=agent)

        if args.ticker:
            ticker = args.ticker.upper()
            logger.info("run_research_once_single_ticker", ticker=ticker)
            result = pipeline.run_ticker(
                ticker,
                reuse_latest_global_context=not args.refresh_global_context,
            )
            pipeline_result = PipelineResult(
                succeeded=1 if result.success else 0,
                failed=0 if result.success else 1,
                ticker_results=[result],
            )
        else:
            logger.info("run_research_once_all_tickers")
            pipeline_result = pipeline.run_all()

    summary = {
        "succeeded": pipeline_result.succeeded,
        "failed": pipeline_result.failed,
        "tickers": [
            {
                "ticker": r.ticker,
                "run_id": str(r.run_id) if r.run_id else None,
                "success": r.success,
                "error": r.error,
            }
            for r in pipeline_result.ticker_results
        ],
    }
    print(json.dumps(summary, indent=2))

    return 0 if pipeline_result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
