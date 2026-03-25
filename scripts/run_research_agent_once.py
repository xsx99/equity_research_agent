#!/usr/bin/env python3
"""Run one direct ResearchAgent call for manual smoke testing."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.research import DEFAULT_MODEL_NAME, ResearchAgent
from src.prompts.registry import PromptRegistry
from src.tools import ToolContext, build_research_tool_registry


def _build_sample_payload(ticker: str) -> dict:
    return {
        "ticker": ticker.upper(),
        "as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "price_snapshot": {
            "last_price": 712.0,
            "return_1d": 0.07,
            "return_5d": 0.03,
            "return_since_market_open": 0.012,
        },
        "context": {
            "sector": "Technology",
            "earnings_in_days": 50,
        },
        "news": [
            {
                "title": f"Samsung has doubled NAND price in Q2.",
                "summary": "Samsung has doubled NAND price in Q2.",
            }
        ],
        "global_context": {
            "as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "indicators": {
                "vix": {
                    "label": "CBOE Volatility Index",
                    "source": "FRED:VIXCLS",
                    "unit": "index",
                    "value": 21.4,
                    "observed_on": datetime.now(timezone.utc).date().isoformat(),
                },
                "us_treasury_10y": {
                    "label": "US Treasury 10Y",
                    "source": "FRED:DGS10",
                    "unit": "pct",
                    "value": 4.21,
                    "observed_on": datetime.now(timezone.utc).date().isoformat(),
                },
            },
            "official_updates": [
            ],
            "trump_updates": [
                {
                    "source": "whitehouse.gov",
                    "title": "President Donald J. Trump delivers remarks on Iran and oil markets",
                    "summary": "The President commented on Iran, sanctions, and oil market conditions.",
                    "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "url": "https://www.whitehouse.gov/remarks/example",
                }
            ],
            "geopolitical_news": [
                {
                    "source": "AP News",
                    "title": "Airstrikes hit Iran as diplomatic efforts accelerate",
                    "summary": "Regional tensions remain elevated and oil markets stay volatile.",
                    "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "url": "https://apnews.com/article/example",
                }
            ],
        },
    }


def _load_payload(payload_file: Path | None, ticker: str) -> dict:
    if payload_file is None:
        return _build_sample_payload(ticker)
    return json.loads(payload_file.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", type=Path, help="Path to a JSON payload file.")
    parser.add_argument("--ticker", default="SNDK", help="Ticker for the built-in sample payload.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Override the model name.")
    args = parser.parse_args()

    payload = _load_payload(args.payload_file, args.ticker)
    agent = ResearchAgent(
        tool_registry=build_research_tool_registry(),
        prompt_registry=PromptRegistry.get_default(),
        model_name=args.model_name,
    )
    result = agent.run(payload, ToolContext())

    print(
        json.dumps(
            {
                "success": result.success,
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "error": result.error,
                "output": result.output_data,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
