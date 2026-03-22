"""SEC Form 4 XML parsing helpers."""
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from lxml import etree

from src.core.logging import get_logger

logger = get_logger(__name__)


def get_text(element, xpath: str) -> Optional[str]:
    """Safely extract text from an XML element."""
    if element is None:
        return None
    found = element.find(xpath)
    return found.text.strip() if found is not None and found.text else None


def parse_date(date_str: str) -> Optional[date]:
    """Parse a date string to a :class:`date` object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("failed_to_parse_date_string", date_str=date_str)
        return None


def extract_accession_from_url(url: str) -> Optional[str]:
    """Extract the accession number from a filing URL."""
    match = re.search(r"/(\d{10}-\d{2}-\d{6})[-/]", url)
    if match:
        return match.group(1)
    logger.warning("could_not_extract_accession_number", url=url)
    return None


def parse_form4_xml(
    xml_content: bytes,
    filing_url: str,
    filing_date: Optional[date],
    timezone,
) -> List[Dict]:
    root = etree.fromstring(xml_content)
    return extract_transactions(root, filing_url, filing_date, timezone)


def extract_transactions(
    root: etree._Element,
    filing_url: str,
    filing_date: Optional[date],
    timezone,
) -> List[Dict]:
    """Extract transaction data from a Form 4 XML element tree."""
    transactions = []

    issuer = root.find(".//issuer")
    ticker = get_text(issuer, "issuerTradingSymbol")
    company_name = get_text(issuer, "issuerName")
    company_cik = get_text(issuer, "issuerCik")

    reporting_owner = root.find(".//reportingOwner")
    owner_id = reporting_owner.find(".//reportingOwnerId") if reporting_owner is not None else None
    insider_name = get_text(owner_id, "rptOwnerName")
    insider_cik = get_text(owner_id, "rptOwnerCik")

    relationship = (
        reporting_owner.find(".//reportingOwnerRelationship")
        if reporting_owner is not None
        else None
    )
    is_director = get_text(relationship, "isDirector") == "1" if relationship is not None else False
    is_officer = get_text(relationship, "isOfficer") == "1" if relationship is not None else False
    is_ten_percent_owner = (
        get_text(relationship, "isTenPercentOwner") == "1" if relationship is not None else False
    )
    insider_title = get_text(relationship, "officerTitle") if relationship is not None else None

    period_of_report = get_text(root, ".//periodOfReport")
    period_of_report_date = parse_date(period_of_report) if period_of_report else None
    effective_filing_date = (
        filing_date or period_of_report_date or datetime.now(timezone).date()
    )

    accession_number = extract_accession_from_url(filing_url)
    if not accession_number:
        logger.warning("missing_accession_number_for_filing", filing_url=filing_url)
        return transactions

    for idx, transaction in enumerate(root.findall(".//nonDerivativeTransaction")):
        trans_data = parse_transaction(
            transaction,
            ticker,
            company_name,
            company_cik,
            insider_name,
            insider_title,
            insider_cik,
            is_director,
            is_officer,
            is_ten_percent_owner,
            effective_filing_date,
            accession_number,
            filing_url,
            idx,
        )
        if trans_data:
            transactions.append(trans_data)

    return transactions


def parse_transaction(
    transaction,
    ticker,
    company_name,
    company_cik,
    insider_name,
    insider_title,
    insider_cik,
    is_director,
    is_officer,
    is_ten_percent_owner,
    filing_date,
    accession_number,
    filing_url,
    transaction_index: int,
) -> Optional[Dict]:
    """Parse a single nonDerivativeTransaction element."""
    trans_date_str = get_text(transaction, ".//transactionDate/value")
    trans_date = parse_date(trans_date_str)

    if not trans_date:
        return None

    trans_code = get_text(transaction, ".//transactionCoding/transactionCode")
    shares_str = get_text(transaction, ".//transactionAmounts/transactionShares/value")
    price_str = get_text(transaction, ".//transactionAmounts/transactionPricePerShare/value")
    shares_owned_str = get_text(
        transaction,
        ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value",
    )

    shares = int(float(shares_str)) if shares_str else None
    price = float(price_str) if price_str else None
    shares_owned = int(float(shares_owned_str)) if shares_owned_str else None
    total_value = (shares * price) if shares and price else None

    return {
        "accession_number": accession_number,
        "transaction_index": transaction_index,
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
        "raw_data": None,
    }
