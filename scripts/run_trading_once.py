#!/usr/bin/env python3
"""Run one trading scheduler phase once from the command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.runtime import TRADING_JOB_PHASES, run_job_phase
from src.trading.runtime.manual_review import run_live_manual_review_once
from src.trading.runtime.preopen import run_live_preopen_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=TRADING_JOB_PHASES, required=True)
    parser.add_argument(
        "--mode",
        choices=("job-phase", "live-preopen", "live-manual-review"),
        default="job-phase",
        help="Use 'live-preopen' or 'live-manual-review' to run explicit live operator paths directly.",
    )
    parser.add_argument(
        "--execute-paper-orders",
        action="store_true",
        help="Only applies to --mode live-preopen or --mode live-manual-review; otherwise paper execution stays disabled.",
    )
    parser.add_argument(
        "--execute-paper-option-orders",
        action="store_true",
        help="Only applies to --mode live-preopen and requires --execute-paper-orders.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "live-preopen":
        if args.phase != "preopen":
            parser.error("--mode live-preopen only supports --phase preopen")
        if args.execute_paper_option_orders and not args.execute_paper_orders:
            parser.error("--execute-paper-option-orders requires --execute-paper-orders")
        result = run_live_preopen_once(
            execute_paper_orders=args.execute_paper_orders,
            execute_paper_option_orders=args.execute_paper_option_orders,
        )
    elif args.mode == "live-manual-review":
        if args.phase != "manual_review":
            parser.error("--mode live-manual-review only supports --phase manual_review")
        if args.execute_paper_option_orders:
            parser.error("--execute-paper-option-orders is not supported for --mode live-manual-review")
        result = run_live_manual_review_once(
            execute_paper_orders=args.execute_paper_orders,
        )
    else:
        if args.execute_paper_orders or args.execute_paper_option_orders:
            parser.error(
                "--execute-paper-orders and --execute-paper-option-orders require a live operator mode"
            )
        result = run_job_phase(args.phase)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 1 if result.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
