#!/usr/bin/env python3
"""Fetch one normalized FMP economic-calendar window."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import config as app_config
from src.providers.market_data.fmp_economic_calendar import FMPEconomicCalendar


def run_smoke(*, as_of: date, horizon_days: int) -> dict[str, Any]:
    api_key = app_config.FMP_API_KEY
    if not api_key:
        return {
            "status": "skipped",
            "reason": "FMP_API_KEY not set",
            "as_of": as_of.isoformat(),
            "horizon_days": horizon_days,
            "events": [],
        }
    provider = FMPEconomicCalendar(api_key=api_key, horizon_days=horizon_days)
    events = tuple(provider.macro_events(as_of))
    return {
        "status": "ok",
        "as_of": as_of.isoformat(),
        "horizon_days": horizon_days,
        "event_count": len(events),
        "events": [
            {
                **event,
                "event_time": event["event_time"].isoformat(),
            }
            for event in events
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=date.today().isoformat(), help="Window start date, YYYY-MM-DD.")
    parser.add_argument("--horizon-days", type=int, default=14, help="Number of calendar days to fetch.")
    args = parser.parse_args(argv)

    payload = run_smoke(as_of=date.fromisoformat(args.as_of), horizon_days=args.horizon_days)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
