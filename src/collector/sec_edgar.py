"""SEC EDGAR Form 4 fetcher and parser."""
import logging
import time
from datetime import datetime, date
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from lxml import etree

from src.collector.sec_edgar_feed import (
    fetch_form4_filings_for_date as feed_fetch_form4_filings_for_date,
    fetch_recent_form4_filings as feed_fetch_recent_form4_filings,
)
from src.collector.sec_edgar_parser import parse_form4_xml
from src.collector.sec_edgar_storage import upsert_transactions
from src.config import (
    COLLECTOR_TIMEZONE,
    SEC_ATOM_PAGE_SIZE,
    SEC_RATE_LIMIT,
    SEC_USER_AGENT,
)
from src.db.connection import get_session

logger = logging.getLogger(__name__)


class SECEdgarCollector:
    """Fetches and parses SEC Form 4 filings using SEC EDGAR API."""

    BASE_URL = "https://www.sec.gov"
    API_URL = f"{BASE_URL}/cgi-bin/browse-edgar"

    def __init__(self, timezone: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})
        self.last_request_time = 0
        self.timezone = self._resolve_timezone(timezone or COLLECTOR_TIMEZONE)

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

    def fetch_recent_form4_filings(self, count: int = 100) -> List[Dict[str, str]]:
        """Fetch recent Form 4 filings using SEC EDGAR Atom feed."""
        logger.info(f"Fetching recent Form 4 filings (count={count})")
        filings = feed_fetch_recent_form4_filings(
            self.session,
            self._rate_limit,
            self.API_URL,
            count=count,
            page_size=SEC_ATOM_PAGE_SIZE,
        )
        logger.info(f"Found {len(filings)} Form 4 filings")
        return filings

    def fetch_form4_filings_for_date(
        self,
        target_date: date,
        page_size: int = SEC_ATOM_PAGE_SIZE,
    ) -> List[Dict[str, str]]:
        """Fetch all Form 4 filings for a specific date."""
        logger.info(f"Fetching Form 4 filings for date={target_date.isoformat()}")

        filings = feed_fetch_form4_filings_for_date(
            self.session,
            self._rate_limit,
            self.API_URL,
            target_date,
            self.timezone,
            page_size=page_size,
        )
        logger.info(f"Found {len(filings)} Form 4 filings for {target_date.isoformat()}")
        return filings

    def get_xml_url_from_filing(self, filing_url: str) -> Optional[str]:
        """Extract XML file URL from filing page."""
        logger.debug(f"Extracting XML URL from filing: {filing_url}")
        self._rate_limit()

        response = self.session.get(filing_url)
        response.raise_for_status()

        # Parse HTML to find XML link (exclude styled xsl versions)
        html = etree.HTML(response.content)
        xml_links = html.xpath("//a[contains(@href, '.xml') and not(contains(@href, 'xsl')) and not(contains(@href, '-index'))]/@href")

        if xml_links:
            xml_path = xml_links[0]
            xml_url = self.BASE_URL + xml_path if xml_path.startswith("/") else xml_path
            logger.debug(f"Found XML URL: {xml_url}")
            return xml_url

        logger.warning(f"No XML file found for filing: {filing_url}")
        return None

    def fetch_and_parse_form4_xml(
        self,
        filing_url: str,
        filing_date: Optional[date] = None,
    ) -> Optional[List[Dict]]:
        """Fetch and parse Form 4 XML file."""
        logger.debug(f"Fetching and parsing Form 4 XML for: {filing_url}")
        xml_url = self.get_xml_url_from_filing(filing_url)
        if not xml_url:
            logger.warning(f"Could not find XML URL for filing: {filing_url}")
            return None

        self._rate_limit()
        response = self.session.get(xml_url)
        response.raise_for_status()

        try:
            transactions = parse_form4_xml(
                response.content,
                filing_url,
                filing_date,
                self.timezone,
            )
            logger.debug(f"Extracted {len(transactions)} transactions from {filing_url}")
            return transactions
        except Exception as e:
            logger.error(f"Error parsing XML from {filing_url}: {e}", exc_info=True)
            return None

    def collect_and_store(self, target_date: Optional[date] = None):
        if target_date is None:
            target_date = datetime.now(self.timezone).date()

        logger.info(f"Starting Form 4 collection for date={target_date.isoformat()}")

        filings = self.fetch_form4_filings_for_date(target_date)

        upserted_count = 0
        empty_count = 0
        error_count = 0

        for i, filing in enumerate(filings, 1):
            filing_url = filing["url"]
            filing_date = filing.get("filing_date")
            logger.debug(f"Processing filing {i}/{len(filings)}: {filing_url}")
            try:
                transactions = self.fetch_and_parse_form4_xml(
                    filing_url,
                    filing_date=filing_date,
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
