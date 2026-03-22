#!/usr/bin/env python3
"""Dry-run test for SEC collector — fetches and displays data without database storage."""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.collectors.sec_edgar.collector import SECEdgarCollector
from src.collectors.sec_edgar.feed import fetch_recent_form4_filings
from src.collectors.sec_edgar.fetcher import fetch_and_parse_form4_xml
from src.core.config import SEC_ATOM_PAGE_SIZE


@dataclass
class ProcessingResult:
    """Result of processing a single filing."""

    url: str
    transactions: List[dict]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.transactions) > 0


def process_filing(collector: SECEdgarCollector, filing_url: str) -> ProcessingResult:
    """Process a single filing and return the result."""
    try:
        transactions = fetch_and_parse_form4_xml(
            collector.session,
            collector._rate_limit,
            filing_url,
            filing_date=None,
            timezone=collector.timezone,
        ) or []
        return ProcessingResult(url=filing_url, transactions=transactions)
    except Exception as e:
        return ProcessingResult(url=filing_url, transactions=[], error=str(e))


def format_transaction(t: dict) -> str:
    ticker = t.get("ticker") or "N/A"
    name = (t.get("insider_name") or "Unknown")[:30]
    tx_type = t.get("transaction_type") or "?"
    shares = f"{t['shares']:,}" if t.get("shares") else "N/A"
    value = f"${t['total_value']:,.2f}" if t.get("total_value") else "N/A"
    return f"{ticker:6} | {name:30} | {tx_type:3} | {shares:>12} shares | {value:>16}"


def print_result(result: ProcessingResult, index: int, total: int) -> None:
    print(f"[{index}/{total}] {result.url}")
    if result.error:
        print(f"  Error: {result.error}")
        return
    if not result.transactions:
        print("  No transactions found")
        return
    for t in result.transactions:
        print(f"  -> {format_transaction(t)}")


def print_summary(results: List[ProcessingResult]) -> None:
    successful = sum(1 for r in results if r.success)
    total_tx = sum(len(r.transactions) for r in results)
    print()
    print(f"{'='*70}")
    print(f"Filings: {len(results)} ({successful} with transactions)")
    print(f"Total transactions: {total_tx}")


def run_test(num_filings: int) -> bool:
    collector = SECEdgarCollector()
    print(f"Fetching {num_filings} recent Form 4 filings from SEC EDGAR...\n")
    filings = fetch_recent_form4_filings(
        collector.session,
        collector._rate_limit,
        collector.API_URL,
        count=num_filings,
        page_size=SEC_ATOM_PAGE_SIZE,
    )
    results = [process_filing(collector, f["url"]) for f in filings]
    for i, result in enumerate(results, 1):
        print_result(result, i, len(results))
    print_summary(results)
    return any(r.success for r in results)


def run_detailed_test() -> bool:
    collector = SECEdgarCollector()
    print("Fetching 1 recent filing...\n")
    filings = fetch_recent_form4_filings(
        collector.session,
        collector._rate_limit,
        collector.API_URL,
        count=1,
        page_size=SEC_ATOM_PAGE_SIZE,
    )
    if not filings:
        print("No filings found")
        return False

    result = process_filing(collector, filings[0]["url"])
    print(f"URL: {result.url}\n")
    if result.error:
        print(f"Error: {result.error}")
        return False
    if not result.transactions:
        print("No transactions found")
        return False

    print(json.dumps(result.transactions, indent=2, default=str))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test SEC collector without database storage"
    )
    parser.add_argument("-n", "--num", type=int, default=5, help="Number of filings to fetch")
    parser.add_argument("-d", "--detailed", action="store_true", help="Show detailed JSON output")
    args = parser.parse_args()
    success = run_detailed_test() if args.detailed else run_test(args.num)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
