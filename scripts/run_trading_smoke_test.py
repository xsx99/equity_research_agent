#!/usr/bin/env python3
"""Run standalone trading smoke modes using fixture-first runtime helpers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.runtime import run_smoke_mode
from src.trading.runtime_smoke import AVAILABLE_SMOKE_MODES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=AVAILABLE_SMOKE_MODES)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list-modes", action="store_true")
    args = parser.parse_args(argv)

    if args.list_modes:
        for mode in AVAILABLE_SMOKE_MODES:
            print(mode)
        return 0
    if args.mode is None:
        parser.error("--mode is required unless --list-modes is set")
    result = run_smoke_mode(args.mode)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
