"""SEC EDGAR Form 4 fetcher and parser."""
import logging
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional
from lxml import etree
from src.config import SEC_USER_AGENT, SEC_RATE_LIMIT
from src.db.connection import get_session
from src.db.models import InsiderTrade

logger = logging.getLogger(__name__)


class SECEdgarCollector:
    """Fetches and parses SEC Form 4 filings using SEC EDGAR API."""

    BASE_URL = "https://www.sec.gov"
    API_URL = f"{BASE_URL}/cgi-bin/browse-edgar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce SEC rate limit (10 requests per second)."""
        elapsed = time.time() - self.last_request_time
        min_interval = 1.0 / SEC_RATE_LIMIT
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.3f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def fetch_recent_form4_filings(self, count: int = 100) -> List[Dict[str, str]]:
        """Fetch recent Form 4 filings using SEC EDGAR Atom feed."""
        logger.info(f"Fetching recent Form 4 filings (count={count})")
        self._rate_limit()

        params = {
            "action": "getcurrent",
            "type": "4",
            "count": count,
            "output": "atom",
        }

        logger.debug(f"Requesting {self.API_URL} with params: {params}")
        response = self.session.get(self.API_URL, params=params)
        response.raise_for_status()
        logger.debug(f"Received response: status={response.status_code}, size={len(response.content)} bytes")

        # Parse Atom feed
        root = etree.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        filings = []
        for entry in root.findall(".//atom:entry", ns):
            link = entry.find("atom:link[@rel='alternate']", ns)
            if link is not None:
                url = link.get("href")
                if "/Archives/edgar/data/" in url:
                    filings.append({"url": url})

        logger.info(f"Found {len(filings)} Form 4 filings")
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

    def fetch_and_parse_form4_xml(self, filing_url: str) -> Optional[List[Dict]]:
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
            root = etree.fromstring(response.content)
            transactions = self._extract_transactions(root, filing_url)
            logger.debug(f"Extracted {len(transactions)} transactions from {filing_url}")
            return transactions
        except Exception as e:
            logger.error(f"Error parsing XML from {filing_url}: {e}", exc_info=True)
            return None

    def _extract_transactions(self, root: etree.Element, filing_url: str) -> List[Dict]:
        """Extract transaction data from Form 4 XML."""
        transactions = []

        # Extract company info
        issuer = root.find(".//issuer")
        ticker = self._get_text(issuer, "issuerTradingSymbol")
        company_name = self._get_text(issuer, "issuerName")
        company_cik = self._get_text(issuer, "issuerCik")

        # Extract insider info
        reporting_owner = root.find(".//reportingOwner")
        owner_id = reporting_owner.find(".//reportingOwnerId")
        insider_name = self._get_text(owner_id, "rptOwnerName")
        insider_cik = self._get_text(owner_id, "rptOwnerCik")

        # Get relationship info
        relationship = reporting_owner.find(".//reportingOwnerRelationship")
        is_director = self._get_text(relationship, "isDirector") == "1" if relationship is not None else False
        is_officer = self._get_text(relationship, "isOfficer") == "1" if relationship is not None else False
        is_ten_percent_owner = self._get_text(relationship, "isTenPercentOwner") == "1" if relationship is not None else False
        insider_title = self._get_text(relationship, "officerTitle") if relationship is not None else None

        # Extract filing date
        period_of_report = self._get_text(root, ".//periodOfReport")
        filing_date = self._parse_date(period_of_report) if period_of_report else datetime.now().date()

        # Extract accession number from URL (format: .../0001225208-26-001015/...)
        accession_number = self._extract_accession_from_url(filing_url)

        # Extract non-derivative transactions
        for transaction in root.findall(".//nonDerivativeTransaction"):
            trans_data = self._parse_transaction(
                transaction, ticker, company_name, company_cik,
                insider_name, insider_title, insider_cik,
                is_director, is_officer, is_ten_percent_owner,
                filing_date, accession_number, filing_url
            )
            if trans_data:
                transactions.append(trans_data)

        return transactions

    def _parse_transaction(self, transaction, ticker, company_name, company_cik,
                          insider_name, insider_title, insider_cik,
                          is_director, is_officer, is_ten_percent_owner,
                          filing_date, accession_number, filing_url) -> Optional[Dict]:
        """Parse individual transaction element."""
        trans_date_str = self._get_text(transaction, ".//transactionDate/value")
        trans_date = self._parse_date(trans_date_str)

        if not trans_date:
            return None

        trans_code = self._get_text(transaction, ".//transactionCoding/transactionCode")
        shares_str = self._get_text(transaction, ".//transactionAmounts/transactionShares/value")
        price_str = self._get_text(transaction, ".//transactionAmounts/transactionPricePerShare/value")
        shares_owned_str = self._get_text(transaction, ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")

        shares = int(float(shares_str)) if shares_str else None
        price = float(price_str) if price_str else None
        shares_owned = int(float(shares_owned_str)) if shares_owned_str else None

        total_value = (shares * price) if shares and price else None

        return {
            "accession_number": accession_number,
            "ticker": ticker,
            "company_name": company_name,
            "company_cik": company_cik,
            "insider_name": insider_name,
            "insider_title": insider_title,
            "insider_cik": insider_cik,
            "is_director": is_director,
            "is_officer": is_officer,
            "is_ten_percent_owner": is_ten_percent_owner,
            "transaction_type": trans_code,
            "transaction_date": trans_date,
            "shares": shares,
            "price_per_share": price,
            "total_value": total_value,
            "shares_owned_after": shares_owned,
            "filing_date": filing_date,
            "filing_url": filing_url,
            "raw_data": None
        }

    def _get_text(self, element, xpath: str) -> Optional[str]:
        """Safely extract text from XML element."""
        if element is None:
            return None
        found = element.find(xpath)
        return found.text.strip() if found is not None and found.text else None

    def _parse_date(self, date_str: str) -> Optional[datetime.date]:
        """Parse date string to date object."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Failed to parse date string: {date_str}")
            return None

    def _extract_accession_from_url(self, url: str) -> Optional[str]:
        """Extract accession number from filing URL.
        
        URL format: .../Archives/edgar/data/CIK/ACCESSION/...
        Example: .../000122520826001015/0001225208-26-001015-index.htm
        """
        import re
        match = re.search(r'/(\d{10}-\d{2}-\d{6})[-/]', url)
        if match:
            return match.group(1)
        logger.warning(f"Could not extract accession number from URL: {url}")
        return None

    def collect_and_store(self):
        logger.info("Starting Form 4 collection")

        filings = self.fetch_recent_form4_filings(count=100)

        new_count = 0
        skipped_count = 0
        error_count = 0

        for i, filing in enumerate(filings, 1):
            filing_url = filing["url"]
            logger.debug(f"Processing filing {i}/{len(filings)}: {filing_url}")
            try:
                transactions = self.fetch_and_parse_form4_xml(filing_url)
                if transactions:
                    with get_session() as session:
                        for trans_data in transactions:
                            # Check if already exists
                            existing = session.query(InsiderTrade).filter_by(
                                accession_number=trans_data["accession_number"]
                            ).first()

                            if not existing:
                                trade = InsiderTrade(**trans_data)
                                session.add(trade)
                                new_count += 1
                                logger.debug(
                                    f"Stored new trade: {trans_data['ticker']} - "
                                    f"{trans_data['insider_name']} - {trans_data['transaction_type']} "
                                    f"{trans_data['shares']} shares"
                                )
                            else:
                                skipped_count += 1
                                logger.debug(f"Skipped duplicate: accession={trans_data['accession_number']}")
            except requests.RequestException as e:
                logger.error(f"Network error processing {filing_url}: {e}")
                error_count += 1
            except Exception as e:
                logger.error(f"Error processing {filing_url}: {e}", exc_info=True)
                error_count += 1

        logger.info(
            f"Collection complete. New: {new_count}, Skipped: {skipped_count}, Errors: {error_count}"
        )
