"""SEC EDGAR Atom feed helpers."""
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from lxml import etree

from src.core.config import SEC_ATOM_PAGE_SIZE

VALID_OWNERSHIP_FORM_TYPES = frozenset({"4", "4/A"})


def parse_atom_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def entry_date(entry_dt: datetime, timezone) -> date:
    if entry_dt.tzinfo:
        return entry_dt.astimezone(timezone).date()
    return entry_dt.date()


def extract_form_type(entry: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Extract the filing form type from an Atom entry."""
    for category in entry.findall("atom:category", ns):
        term = category.get("term")
        if term:
            return term.strip().upper()

    title = entry.findtext("atom:title", namespaces=ns)
    if not title:
        return None

    form_type, _, _ = title.partition(" - ")
    form_type = form_type.strip().upper()
    return form_type or None


def fetch_atom_page(
    session,
    rate_limit: Callable[[], None],
    api_url: str,
    start: int,
    count: int,
) -> List[Dict[str, Optional[datetime]]]:
    """Fetch a single page of exact Form 4 filings from the SEC EDGAR Atom feed."""
    rate_limit()

    params = {
        "action": "getcurrent",
        "type": "4",
        "count": count,
        "start": start,
        "output": "atom",
    }

    response = session.get(api_url, params=params)
    response.raise_for_status()

    root = etree.fromstring(response.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    filings = []
    for entry in root.findall(".//atom:entry", ns):
        # SEC's current-filings feed broad-matches ``type=4`` to other ``4*`` forms
        # such as 424B2, so we filter entries down to exact ownership filings here.
        form_type = extract_form_type(entry, ns)
        if form_type not in VALID_OWNERSHIP_FORM_TYPES:
            continue

        link = entry.find("atom:link[@rel='alternate']", ns)
        if link is None:
            continue
        url = link.get("href")
        if not url or "/Archives/edgar/data/" not in url:
            continue

        updated = entry.findtext("atom:updated", namespaces=ns)
        published = entry.findtext("atom:published", namespaces=ns)
        entry_dt = parse_atom_datetime(updated or published)
        filings.append({"url": url, "updated": entry_dt})

    return filings


def fetch_recent_form4_filings(
    session,
    rate_limit: Callable[[], None],
    api_url: str,
    count: int = 100,
    page_size: int = SEC_ATOM_PAGE_SIZE,
) -> List[Dict[str, str]]:
    """Fetch recent Form 4 filings using the SEC EDGAR Atom feed."""
    if count <= 0:
        return []

    filings: List[Dict[str, str]] = []
    seen_urls: set = set()
    start = 0

    while len(filings) < count:
        batch_size = max(1, min(page_size, 100, count - len(filings)))
        entries = fetch_atom_page(session, rate_limit, api_url, start, batch_size)
        if not entries:
            break

        for entry in entries:
            url = entry.get("url")
            if url and url not in seen_urls:
                filings.append({"url": url})
                seen_urls.add(url)

        if len(entries) < batch_size:
            break

        start += batch_size

    return filings


def fetch_form4_filings_for_date(
    session,
    rate_limit: Callable[[], None],
    api_url: str,
    target_date: date,
    timezone,
    page_size: int = SEC_ATOM_PAGE_SIZE,
) -> List[Dict[str, str]]:
    """Fetch all Form 4 filings for a specific date."""
    page_size = max(1, min(page_size, SEC_ATOM_PAGE_SIZE, 100))
    filings: List[Dict[str, str]] = []
    seen_urls: set = set()
    start = 0

    while True:
        entries = fetch_atom_page(session, rate_limit, api_url, start, page_size)
        if not entries:
            break

        for entry in entries:
            url = entry.get("url")
            entry_dt = entry.get("updated")
            if not url or not entry_dt:
                continue
            entry_dt_date = entry_date(entry_dt, timezone)
            if entry_dt_date == target_date and url not in seen_urls:
                filings.append(
                    {
                        "url": url,
                        "filing_date": entry_dt_date,
                        "filing_datetime": entry_dt,
                    }
                )
                seen_urls.add(url)

        last_dt = next(
            (item.get("updated") for item in reversed(entries) if item.get("updated")),
            None,
        )
        if last_dt:
            last_date = entry_date(last_dt, timezone)
            if last_date < target_date:
                break

        if len(entries) < page_size:
            break

        start += page_size

    return filings
