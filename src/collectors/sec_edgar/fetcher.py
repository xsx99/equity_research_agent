"""SEC EDGAR HTTP fetching utilities."""
from datetime import date
from typing import Callable, Dict, List, Optional

from lxml import etree

from src.collectors.sec_edgar.parser import parse_form4_xml
from src.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.sec.gov"


def get_xml_url_from_filing(
    session,
    rate_limit: Callable[[], None],
    filing_url: str,
) -> Optional[str]:
    """Extract the XML file URL from a filing index page."""
    logger.debug(f"Extracting XML URL from filing: {filing_url}")
    rate_limit()

    response = session.get(filing_url)
    response.raise_for_status()

    html = etree.HTML(response.content)
    xml_links = html.xpath(
        "//a[contains(@href, '.xml') and not(contains(@href, 'xsl')) "
        "and not(contains(@href, '-index'))]/@href"
    )

    if xml_links:
        xml_path = xml_links[0]
        xml_url = BASE_URL + xml_path if xml_path.startswith("/") else xml_path
        logger.debug(f"Found XML URL: {xml_url}")
        return xml_url

    logger.warning(f"No XML file found for filing: {filing_url}")
    return None


def fetch_and_parse_form4_xml(
    session,
    rate_limit: Callable[[], None],
    filing_url: str,
    filing_date: Optional[date],
    timezone,
) -> Optional[List[Dict]]:
    """Fetch and parse a Form 4 XML file."""
    logger.debug(f"Fetching and parsing Form 4 XML for: {filing_url}")
    xml_url = get_xml_url_from_filing(session, rate_limit, filing_url)
    if not xml_url:
        logger.warning(f"Could not find XML URL for filing: {filing_url}")
        return None

    rate_limit()
    response = session.get(xml_url)
    response.raise_for_status()

    try:
        transactions = parse_form4_xml(
            response.content,
            filing_url,
            filing_date,
            timezone,
        )
        logger.debug(f"Extracted {len(transactions)} transactions from {filing_url}")
        return transactions
    except Exception as e:
        logger.error(f"Error parsing XML from {filing_url}: {e}", exc_info=True)
        return None
