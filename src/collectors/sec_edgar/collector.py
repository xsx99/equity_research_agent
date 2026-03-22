"""SEC EDGAR Form 4 collector."""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from src.collectors.base import BaseCollector, CollectionResult
from src.collectors.sec_edgar.feed import fetch_form4_filings_for_date
from src.collectors.sec_edgar.fetcher import fetch_and_parse_form4_xml
from src.collectors.sec_edgar.storage import upsert_transactions
from src.core.config import (
    SCHEDULER_TIMEZONE,
    SEC_ATOM_PAGE_SIZE,
    SEC_RATE_LIMIT,
    SEC_USER_AGENT,
)
from src.db.connection import get_session
from src.core.logging import get_logger

logger = get_logger(__name__)


class SECEdgarCollector(BaseCollector):
    """Collector for SEC EDGAR Form 4 (insider trading) filings."""

    API_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self, timezone: Optional[str] = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})
        self._last_request_time: float = 0.0
        self.timezone = self._resolve_timezone(timezone or SCHEDULER_TIMEZONE)

    @property
    def name(self) -> str:
        return "sec_edgar_form4"

    def _rate_limit(self) -> None:
        """Enforce SEC rate limit (10 requests per second)."""
        elapsed = time.time() - self._last_request_time
        min_interval = 1.0 / SEC_RATE_LIMIT
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _resolve_timezone(self, tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning(f"Invalid timezone '{tz_name}', defaulting to UTC")
            return ZoneInfo("UTC")

    def collect(self, target_date: Optional[date] = None) -> CollectionResult:
        """Collect Form 4 filings for *target_date* and store in the database."""
        if target_date is None:
            target_date = datetime.now(self.timezone).date()

        logger.info(f"Starting Form 4 collection for date={target_date.isoformat()}")

        filings = fetch_form4_filings_for_date(
            self.session,
            self._rate_limit,
            self.API_URL,
            target_date,
            self.timezone,
            page_size=SEC_ATOM_PAGE_SIZE,
        )

        result = CollectionResult()

        for i, filing in enumerate(filings, 1):
            filing_url = filing["url"]
            filing_date = filing.get("filing_date")
            logger.debug(f"Processing filing {i}/{len(filings)}: {filing_url}")

            try:
                transactions = fetch_and_parse_form4_xml(
                    self.session,
                    self._rate_limit,
                    filing_url,
                    filing_date=filing_date,
                    timezone=self.timezone,
                )
                if transactions:
                    with get_session() as session:
                        upserted = upsert_transactions(session, transactions)
                        result.upserted += upserted
                else:
                    result.skipped += 1
            except requests.RequestException as e:
                logger.error(f"Network error processing {filing_url}: {e}")
                result.errors += 1
            except Exception as e:
                logger.error(f"Error processing {filing_url}: {e}", exc_info=True)
                result.errors += 1

        logger.info(
            f"Collection complete. "
            f"Upserted: {result.upserted}, Skipped: {result.skipped}, Errors: {result.errors}"
        )
        return result
