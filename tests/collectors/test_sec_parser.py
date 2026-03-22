"""Unit tests for SEC Form 4 XML parser helpers."""
from __future__ import annotations

from datetime import date

import pytest
from lxml import etree
from zoneinfo import ZoneInfo

from src.collectors.sec_edgar.parser import (
    extract_accession_from_url,
    extract_transactions,
    get_text,
    parse_date,
    parse_form4_xml,
    parse_transaction,
)

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# get_text
# ---------------------------------------------------------------------------


def test_get_text_returns_stripped_value():
    el = etree.fromstring("<root><child>  hello  </child></root>")
    assert get_text(el, "child") == "hello"


def test_get_text_missing_path_returns_none():
    el = etree.fromstring("<root><child>hello</child></root>")
    assert get_text(el, "missing") is None


def test_get_text_empty_tag_returns_none():
    el = etree.fromstring("<root><child></child></root>")
    assert get_text(el, "child") is None


def test_get_text_none_element_returns_none():
    assert get_text(None, "anything") is None


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


def test_parse_date_valid():
    assert parse_date("2026-03-21") == date(2026, 3, 21)


def test_parse_date_empty_returns_none():
    assert parse_date("") is None


def test_parse_date_none_returns_none():
    assert parse_date(None) is None


def test_parse_date_invalid_format_returns_none():
    assert parse_date("21/03/2026") is None


def test_parse_date_garbage_returns_none():
    assert parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# extract_accession_from_url
# ---------------------------------------------------------------------------


def test_extract_accession_valid_url():
    url = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001-index.htm"
    result = extract_accession_from_url(url)
    assert result == "0000320193-26-000001"


def test_extract_accession_slash_separator():
    url = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001/filing.xml"
    result = extract_accession_from_url(url)
    assert result == "0000320193-26-000001"


def test_extract_accession_no_match_returns_none():
    assert extract_accession_from_url("https://example.com/no-accession") is None


def test_extract_accession_empty_string_returns_none():
    assert extract_accession_from_url("") is None


# ---------------------------------------------------------------------------
# Minimal valid Form 4 XML fixture
# ---------------------------------------------------------------------------

_MINIMAL_FORM4 = b"""<?xml version="1.0" encoding="UTF-8"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>Tim Cook</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <periodOfReport>2026-03-01</periodOfReport>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-03-01</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>1000</value></transactionShares>
      <transactionPricePerShare><value>210.50</value></transactionPricePerShare>
    </transactionAmounts>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>50000</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>
"""

_FILING_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/"
    "0000320193-26-000001/0000320193-26-000001-index.htm"
)


# ---------------------------------------------------------------------------
# parse_form4_xml / extract_transactions
# ---------------------------------------------------------------------------


def test_parse_form4_xml_returns_one_transaction():
    transactions = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)
    assert len(transactions) == 1


def test_parse_form4_xml_extracts_issuer_fields():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["ticker"] == "AAPL"
    assert txn["company_name"] == "Apple Inc."
    assert txn["company_cik"] == "0000320193"


def test_parse_form4_xml_extracts_insider_fields():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["insider_name"] == "Tim Cook"
    assert txn["insider_title"] == "CEO"
    assert txn["is_officer"] is True
    assert txn["is_director"] is False
    assert txn["is_ten_percent_owner"] is False


def test_parse_form4_xml_extracts_transaction_fields():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["transaction_type"] == "P"
    assert txn["transaction_date"] == date(2026, 3, 1)
    assert txn["shares"] == 1000
    assert txn["price_per_share"] == pytest.approx(210.50)
    assert txn["total_value"] == pytest.approx(210500.0)
    assert txn["shares_owned_after"] == 50000


def test_parse_form4_xml_uses_provided_filing_date():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["filing_date"] == date(2026, 3, 2)


def test_parse_form4_xml_falls_back_to_period_of_report_when_no_filing_date():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, None, ET)[0]
    # Should fall back to periodOfReport = 2026-03-01
    assert txn["filing_date"] == date(2026, 3, 1)


def test_parse_form4_xml_extracts_accession_number():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["accession_number"] == "0000320193-26-000001"


def test_parse_form4_xml_transaction_index_starts_at_zero():
    txn = parse_form4_xml(_MINIMAL_FORM4, _FILING_URL, date(2026, 3, 2), ET)[0]
    assert txn["transaction_index"] == 0


def test_parse_form4_xml_no_accession_returns_empty():
    transactions = parse_form4_xml(_MINIMAL_FORM4, "https://no-accession.example.com/", None, ET)
    assert transactions == []


def test_parse_form4_xml_multiple_transactions():
    xml = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>Tim Cook</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>1</isOfficer>
    </reportingOwnerRelationship>
  </reportingOwner>
  <periodOfReport>2026-03-01</periodOfReport>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-03-01</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>500</value></transactionShares>
      <transactionPricePerShare><value>200.00</value></transactionPricePerShare>
    </transactionAmounts>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>1500</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
  </nonDerivativeTransaction>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-03-02</value></transactionDate>
    <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>200</value></transactionShares>
      <transactionPricePerShare><value>205.00</value></transactionPricePerShare>
    </transactionAmounts>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>1300</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>
"""
    transactions = parse_form4_xml(xml, _FILING_URL, date(2026, 3, 3), ET)
    assert len(transactions) == 2
    assert transactions[0]["transaction_index"] == 0
    assert transactions[1]["transaction_index"] == 1
    assert transactions[0]["transaction_type"] == "P"
    assert transactions[1]["transaction_type"] == "S"


# ---------------------------------------------------------------------------
# parse_transaction
# ---------------------------------------------------------------------------


def _make_transaction_el(
    date_str="2026-03-01",
    code="P",
    shares="1000",
    price="210.50",
    shares_after="50000",
) -> etree._Element:
    xml = f"""<nonDerivativeTransaction>
    <transactionDate><value>{date_str}</value></transactionDate>
    <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>{shares}</value></transactionShares>
      <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
    </transactionAmounts>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>{shares_after}</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
  </nonDerivativeTransaction>"""
    return etree.fromstring(xml)


def test_parse_transaction_happy_path():
    el = _make_transaction_el()
    result = parse_transaction(
        el, "AAPL", "Apple Inc.", "0000320193",
        "Tim Cook", "CEO", "0001234567",
        False, True, False,
        date(2026, 3, 2), "0000320193-26-000001", _FILING_URL, 0,
    )
    assert result is not None
    assert result["transaction_date"] == date(2026, 3, 1)
    assert result["transaction_type"] == "P"
    assert result["shares"] == 1000
    assert result["price_per_share"] == pytest.approx(210.50)
    assert result["total_value"] == pytest.approx(210500.0)
    assert result["shares_owned_after"] == 50000


def test_parse_transaction_missing_date_returns_none():
    el = _make_transaction_el(date_str="")
    # Empty date value element — parse_transaction should return None
    xml = b"""<nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>200.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>"""
    el = etree.fromstring(xml)
    result = parse_transaction(
        el, "AAPL", "Apple Inc.", "0000320193",
        "Tim Cook", "CEO", "0001234567",
        False, True, False,
        date(2026, 3, 2), "0000320193-26-000001", _FILING_URL, 0,
    )
    assert result is None


def test_parse_transaction_missing_price_sets_none():
    xml = b"""<nonDerivativeTransaction>
      <transactionDate><value>2026-03-01</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
      </transactionAmounts>
    </nonDerivativeTransaction>"""
    el = etree.fromstring(xml)
    result = parse_transaction(
        el, "AAPL", "Apple Inc.", "0000320193",
        "Tim Cook", "CEO", "0001234567",
        False, True, False,
        date(2026, 3, 2), "0000320193-26-000001", _FILING_URL, 0,
    )
    assert result is not None
    assert result["price_per_share"] is None
    assert result["total_value"] is None


def test_parse_transaction_fractional_shares_truncated():
    el = _make_transaction_el(shares="1500.75")
    result = parse_transaction(
        el, "AAPL", "Apple Inc.", "0000320193",
        "Tim Cook", "CEO", "0001234567",
        False, True, False,
        date(2026, 3, 2), "0000320193-26-000001", _FILING_URL, 0,
    )
    assert result["shares"] == 1500  # int(float("1500.75"))
