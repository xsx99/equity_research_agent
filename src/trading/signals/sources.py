"""Point-in-time source rows and in-memory source adapters for PR02."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from src.db.models.insider_trades import InsiderTrade
from src.providers.market_data.helpers import MARKET_TIMEZONE, REGULAR_MARKET_CLOSE, REGULAR_MARKET_OPEN


@dataclass(frozen=True)
class SourceRecord:
    """Normalized point-in-time source row consumed by signal builders."""

    ticker: str
    source_family: str
    source: str
    source_table: str
    source_record_id: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())

    @property
    def source_ref(self) -> dict[str, str]:
        return {
            "source": self.source,
            "source_table": self.source_table,
            "source_record_id": self.source_record_id,
        }


@dataclass(frozen=True)
class SourceIngestionRunRecord:
    """Scheduled or targeted source refresh metadata."""

    source_ingestion_run_id: str
    source_family: str
    run_type: str
    scope_json: dict[str, Any]
    provider: str | None
    as_of: datetime | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    coverage_json: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FundamentalSnapshotRecord:
    """Repository-level shape matching the `fundamental_snapshots` table."""

    fundamental_snapshot_id: str
    ticker: str
    fiscal_period: str | None
    as_of_date: date | None
    provider: str
    source_refs_json: list[dict[str, str]]
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    raw_payload_ref: str | None
    normalized_metrics_json: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


@dataclass(frozen=True)
class EventNewsItemRecord:
    """Repository-level shape matching the `event_news_items` table."""

    event_news_item_id: str
    ticker: str
    source_ticker: str | None
    event_type: str
    direction: str | None
    sentiment: str | None
    importance: str | None
    headline: str | None
    summary: str | None
    provider: str
    source_refs_json: list[dict[str, str]]
    dedupe_key: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    raw_payload_ref: str | None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        if self.source_ticker is not None:
            object.__setattr__(self, "source_ticker", self.source_ticker.strip().upper())


@dataclass(frozen=True)
class SocialMacroItemRecord:
    """Repository-level shape matching the `social_macro_items` table."""

    social_macro_item_id: str
    ticker: str
    category: str
    source_type: str
    source_key: str
    provider: str
    title: str | None
    summary: str | None
    direction: str | None
    sentiment_direction: str | None
    importance_score: float | None
    importance_label: str | None
    policy_headwind_flag: bool
    policy_tailwind_flag: bool
    explicit_ticker_mention_flag: bool
    explicit_theme_mention_flag: bool
    theme_tags_json: list[str]
    company_name_mentions_json: list[str]
    source_refs_json: list[dict[str, str]]
    dedupe_key: str
    event_time: datetime
    published_at: datetime
    ingested_at: datetime
    available_for_decision_at: datetime
    raw_payload_ref: str | None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


def source_record_from_fundamental_snapshot(snapshot: FundamentalSnapshotRecord) -> SourceRecord:
    """Convert a normalized fundamental row into the SignalPipeline source contract."""
    return SourceRecord(
        ticker=snapshot.ticker,
        source_family="fundamental",
        source=snapshot.provider,
        source_table="fundamental_snapshots",
        source_record_id=snapshot.fundamental_snapshot_id,
        event_time=snapshot.event_time,
        published_at=snapshot.published_at,
        ingested_at=snapshot.ingested_at,
        available_for_decision_at=snapshot.available_for_decision_at,
        payload=dict(snapshot.normalized_metrics_json),
    )


def source_record_from_event_news_item(item: EventNewsItemRecord) -> SourceRecord:
    """Convert a normalized event/news row into the SignalPipeline source contract."""
    payload = dict(item.metadata_json)
    payload.update(
        {
            "event_type": item.event_type,
            "direction": item.direction,
            "sentiment": item.sentiment,
            "importance": item.importance,
            "headline": item.headline,
            "summary": item.summary,
            "source_ticker": item.source_ticker,
        }
    )
    return SourceRecord(
        ticker=item.ticker,
        source_family="events_news",
        source=item.provider,
        source_table="event_news_items",
        source_record_id=item.event_news_item_id,
        event_time=item.event_time,
        published_at=item.published_at,
        ingested_at=item.ingested_at,
        available_for_decision_at=item.available_for_decision_at,
        payload=payload,
    )


def source_record_from_social_macro_item(item: SocialMacroItemRecord) -> SourceRecord:
    """Convert a normalized social/policy row into the SignalPipeline source contract."""
    payload = dict(item.metadata_json)
    payload.update(
        {
            "category": item.category,
            "source_type": item.source_type,
            "source_key": item.source_key,
            "title": item.title,
            "summary": item.summary,
            "direction": item.direction,
            "sentiment_direction": item.sentiment_direction,
            "importance_score": item.importance_score,
            "importance_label": item.importance_label,
            "policy_headwind_flag": item.policy_headwind_flag,
            "policy_tailwind_flag": item.policy_tailwind_flag,
            "explicit_ticker_mention_flag": item.explicit_ticker_mention_flag,
            "explicit_theme_mention_flag": item.explicit_theme_mention_flag,
            "theme_tags": list(item.theme_tags_json),
            "company_name_mentions": list(item.company_name_mentions_json),
        }
    )
    return SourceRecord(
        ticker=item.ticker,
        source_family="social_macro",
        source=item.provider,
        source_table="social_macro_items",
        source_record_id=item.social_macro_item_id,
        event_time=item.event_time,
        published_at=item.published_at,
        ingested_at=item.ingested_at,
        available_for_decision_at=item.available_for_decision_at,
        payload=payload,
    )


def source_record_from_insider_trade(trade: InsiderTrade) -> SourceRecord:
    """Adapt one legacy insider trade row into a conservative trading-side PIT source row."""
    transaction_date = trade.transaction_date or trade.filing_date
    event_time = _market_datetime(transaction_date, REGULAR_MARKET_CLOSE)
    published_at = _market_datetime(trade.filing_date, REGULAR_MARKET_CLOSE)
    ingested_at = _normalize_datetime(getattr(trade, "created_at", None)) or published_at
    available_for_decision_at = insider_trade_available_for_decision_at(trade)
    payload = {
        "accession_number": trade.accession_number,
        "transaction_index": trade.transaction_index,
        "company_name": trade.company_name,
        "company_cik": trade.company_cik,
        "insider_name": trade.insider_name,
        "officer_title": trade.insider_title,
        "insider_cik": trade.insider_cik,
        "is_director": bool(trade.is_director),
        "is_officer": bool(trade.is_officer),
        "is_ten_percent_owner": bool(trade.is_ten_percent_owner),
        "transaction_type": trade.transaction_type,
        "transaction_date": transaction_date.isoformat() if transaction_date else None,
        "shares": trade.shares,
        "price_per_share": float(trade.price_per_share) if trade.price_per_share is not None else None,
        "total_value": float(trade.total_value) if trade.total_value is not None else None,
        "shares_owned_after": trade.shares_owned_after,
        "filing_date": trade.filing_date.isoformat() if trade.filing_date else None,
        "filing_url": trade.filing_url,
        "raw_data": dict(trade.raw_data or {}),
    }
    return SourceRecord(
        ticker=trade.ticker,
        source_family="insider",
        source="legacy_insider_trade",
        source_table="insider_trades",
        source_record_id=str(getattr(trade, "id", f"{trade.accession_number}:{trade.transaction_index}")),
        event_time=event_time,
        published_at=published_at,
        ingested_at=ingested_at,
        available_for_decision_at=available_for_decision_at,
        payload=payload,
    )


def insider_trade_available_for_decision_at(trade: InsiderTrade) -> datetime:
    """Conservative availability gate for legacy Form 4 rows with date-only filing fidelity."""
    filing_open = next_market_open_after_filing_date(trade.filing_date)
    ingested_at = _normalize_datetime(getattr(trade, "created_at", None))
    if ingested_at is None:
        return filing_open
    return max(ingested_at, filing_open)


def next_market_open_after_filing_date(filing_date: date) -> datetime:
    """Return the next regular market open after a filing date as UTC."""
    next_day = filing_date + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return _market_datetime(next_day, REGULAR_MARKET_OPEN)


def _market_datetime(value: date, clock_time: time) -> datetime:
    return datetime.combine(value, clock_time, tzinfo=MARKET_TIMEZONE).astimezone(timezone.utc)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InMemorySignalSourceRepository:
    """Fixture-backed signal source repository."""

    def __init__(self, records: Iterable[SourceRecord] = ()) -> None:
        self._records: list[SourceRecord] = list(records)

    def add(self, *records: SourceRecord) -> None:
        self._records.extend(records)

    def records_for_ticker(self, ticker: str) -> tuple[SourceRecord, ...]:
        symbol = ticker.strip().upper()
        return tuple(record for record in self._records if record.ticker == symbol)

    def available_records(
        self,
        ticker: str,
        decision_time: datetime,
        *,
        source_family: str | None = None,
    ) -> tuple[SourceRecord, ...]:
        records = [
            record
            for record in self.records_for_ticker(ticker)
            if record.available_for_decision_at <= decision_time
            and (source_family is None or record.source_family == source_family)
        ]
        return tuple(sorted(records, key=lambda record: record.available_for_decision_at))

    def latest_available_by_family(
        self,
        ticker: str,
        source_family: str,
        decision_time: datetime,
    ) -> tuple[SourceRecord, ...]:
        records = self.available_records(ticker, decision_time, source_family=source_family)
        if not records:
            return ()
        latest = max(record.available_for_decision_at for record in records)
        return tuple(record for record in records if record.available_for_decision_at == latest)

    def latest_insider_filing_at(self) -> datetime | None:
        insider_records = [
            record.published_at
            for record in self._records
            if record.source_family == "insider"
        ]
        if not insider_records:
            return None
        return max(insider_records)
