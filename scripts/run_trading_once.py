#!/usr/bin/env python3
"""Run one trading scheduler phase once from the command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.runtime import TRADING_JOB_PHASES, run_job_phase
from src.trading.runtime_live import run_live_preopen_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=TRADING_JOB_PHASES, required=True)
    parser.add_argument(
        "--mode",
        choices=("job-phase", "live-preopen"),
        default="job-phase",
        help="Use 'live-preopen' to run the live morning pipeline directly.",
    )
    parser.add_argument(
        "--execute-paper-orders",
        action="store_true",
        help="Only applies to --mode live-preopen; otherwise paper execution stays disabled.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "live-preopen":
        if args.phase != "preopen":
            parser.error("--mode live-preopen only supports --phase preopen")
        result = run_live_preopen_once(execute_paper_orders=args.execute_paper_orders)
    else:
        if args.execute_paper_orders:
            parser.error("--execute-paper-orders requires --mode live-preopen")
        result = run_job_phase(args.phase)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
