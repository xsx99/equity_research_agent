"""SEC EDGAR Form 4 collector and workflow orchestration."""
import logging
import time
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from src.collector.sec_edgar_feed import (
    fetch_form4_filings_for_date,
)
from src.collector.sec_edgar_fetcher import fetch_and_parse_form4_xml
from src.collector.sec_edgar_storage import upsert_transactions
from src.config import (
    SCHEDULER_TIMEZONE,
    SEC_ATOM_PAGE_SIZE,
    SEC_RATE_LIMIT,
    SEC_USER_AGENT,
)
from src.db.connection import get_session

logger = logging.getLogger(__name__)


class SECEdgarCollector:
    """Thin wrapper providing HTTP session and rate limiting for SEC EDGAR API."""

    API_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self, timezone: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})
        self.last_request_time = 0
        self.timezone = self._resolve_timezone(timezone or SCHEDULER_TIMEZONE)

    def _rate_limit(self):
        """Enforce SEC rate limit (10 requests per second)."""
        elapsed = time.time() - self.last_request_time
        min_interval = 1.0 / SEC_RATE_LIMIT
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.3f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _resolve_timezone(self, tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning(f"Invalid timezone '{tz_name}', defaulting to UTC")
            return ZoneInfo("UTC")


def collect_and_store(
    target_date: Optional[date] = None,
    timezone: Optional[str] = None,
) -> dict:
    """
    Collect Form 4 filings for a date and store them in the database.

    Returns dict with counts: upserted, empty, errors.
    """
    collector = SECEdgarCollector(timezone=timezone)

    if target_date is None:
        target_date = datetime.now(collector.timezone).date()

    logger.info(f"Starting Form 4 collection for date={target_date.isoformat()}")

    # Fetch filings for the target date
    filings = fetch_form4_filings_for_date(
        collector.session,
        collector._rate_limit,
        collector.API_URL,
        target_date,
        collector.timezone,
        page_size=SEC_ATOM_PAGE_SIZE,
    )

    upserted_count = 0
    empty_count = 0
    error_count = 0

    for i, filing in enumerate(filings, 1):
        filing_url = filing["url"]
        filing_date = filing.get("filing_date")
        logger.debug(f"Processing filing {i}/{len(filings)}: {filing_url}")

        try:
            transactions = fetch_and_parse_form4_xml(
                collector.session,
                collector._rate_limit,
                filing_url,
                filing_date=filing_date,
                timezone=collector.timezone,
            )
            if transactions:
                with get_session() as session:
                    upserted = upsert_transactions(session, transactions)
                    upserted_count += upserted
            else:
                empty_count += 1
        except requests.RequestException as e:
            logger.error(f"Network error processing {filing_url}: {e}")
            error_count += 1
        except Exception as e:
            logger.error(f"Error processing {filing_url}: {e}", exc_info=True)
            error_count += 1

    logger.info(
        "Collection complete. "
        f"Upserted: {upserted_count}, Empty: {empty_count}, Errors: {error_count}"
    )

    return {
        "upserted": upserted_count,
        "empty": empty_count,
        "errors": error_count,
    }
