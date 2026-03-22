"""Unit tests for SEC EDGAR Atom feed filtering helpers."""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from src.collectors.sec_edgar.feed import fetch_atom_page, fetch_form4_filings_for_date

ET = ZoneInfo("America/New_York")


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.calls: list[dict] = []

    def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        return _FakeResponse(self._content)


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>4 - Exact Form 4</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/100/0000000100-26-000001-index.htm"/>
    <updated>2026-03-20T21:55:13-04:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="4"/>
  </entry>
  <entry>
    <title>4/A - Amended Form 4</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/101/0000000101-26-000001-index.htm"/>
    <updated>2026-03-20T21:10:00-04:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="4/A"/>
  </entry>
  <entry>
    <title>4/A - Title Fallback</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/102/0000000102-26-000001-index.htm"/>
    <updated>2026-03-20T20:00:00-04:00</updated>
  </entry>
  <entry>
    <title>424B2 - Broad Match Noise</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/103/0000000103-26-000001-index.htm"/>
    <updated>2026-03-20T19:00:00-04:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="424B2"/>
  </entry>
  <entry>
    <title>425 - Broad Match Noise</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/104/0000000104-26-000001-index.htm"/>
    <updated>2026-03-19T19:00:00-04:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="425"/>
  </entry>
</feed>
"""


def _noop_rate_limit() -> None:
    return None


def test_fetch_atom_page_keeps_only_exact_ownership_forms():
    session = _FakeSession(ATOM_FEED)

    filings = fetch_atom_page(
        session,
        _noop_rate_limit,
        "https://www.sec.gov/cgi-bin/browse-edgar",
        start=0,
        count=100,
    )

    urls = [filing["url"] for filing in filings]
    assert urls == [
        "https://www.sec.gov/Archives/edgar/data/100/0000000100-26-000001-index.htm",
        "https://www.sec.gov/Archives/edgar/data/101/0000000101-26-000001-index.htm",
        "https://www.sec.gov/Archives/edgar/data/102/0000000102-26-000001-index.htm",
    ]
    assert session.calls[0]["params"]["type"] == "4"


def test_fetch_form4_filings_for_date_excludes_broad_match_noise():
    session = _FakeSession(ATOM_FEED)

    filings = fetch_form4_filings_for_date(
        session,
        _noop_rate_limit,
        "https://www.sec.gov/cgi-bin/browse-edgar",
        target_date=date(2026, 3, 20),
        timezone=ET,
        page_size=100,
    )

    urls = [filing["url"] for filing in filings]
    assert urls == [
        "https://www.sec.gov/Archives/edgar/data/100/0000000100-26-000001-index.htm",
        "https://www.sec.gov/Archives/edgar/data/101/0000000101-26-000001-index.htm",
        "https://www.sec.gov/Archives/edgar/data/102/0000000102-26-000001-index.htm",
    ]
    assert all(filing["filing_date"] == date(2026, 3, 20) for filing in filings)
