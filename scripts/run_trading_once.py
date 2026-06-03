#!/usr/bin/env python3
"""Run one trading scheduler phase once from the command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.runtime import TRADING_JOB_PHASES, run_job_phase


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=TRADING_JOB_PHASES, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_job_phase(args.phase)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
